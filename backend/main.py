import os
import json
import asyncio
import datetime
import razorpay
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from pipecat.transports.websocket.server import WebsocketServerTransport, WebsocketServerParams
from bot import run_voice_agent
from agent import app as sales_agent
from db import leads_collection, conversations_collection
from dispatch import send_email_dispatch
from langchain_core.messages import HumanMessage

load_dotenv()

app = FastAPI(title="Aanandi Sales API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Razorpay Setup (Mandatory) ────────────────────────────────────────
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID", "rzp_test_dummy"), os.getenv("RAZORPAY_KEY_SECRET", "dummy_secret"))
)

class OrderRequest(BaseModel):
    amount: int

@app.post("/create-order")
async def create_order(order: OrderRequest):
    """Mandatory Razorpay order creation endpoint."""
    try:
        order_data = {
            "amount": order.amount * 100,  # Razorpay expects amount in paise (INR * 100)
            "currency": "INR",
            "payment_capture": 1
        }
        razorpay_order = razorpay_client.order.create(data=order_data)
        return {"order_id": razorpay_order["id"], "amount": order_data["amount"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
import random
from pydantic import EmailStr
from dispatch import send_email_dispatch

class OTPRequest(BaseModel):
    email: EmailStr

@app.post("/api/v1/auth/send-otp")
async def send_otp(req: OTPRequest):
    """Generates and emails an OTP for frontend verification."""
    otp_code = str(random.randint(100000, 999999))
    
    # In production, you would save `otp_code` to your database with an expiration timestamp
    # to verify it later. For now, we dispatch the email.
    
    email_body = f"Your Aanandi security code is {otp_code}. It is valid for 10 minutes."
    result = send_email_dispatch(req.email, "Your Aanandi Security Code", email_body)
    
    if result.get("success"):
        # Return the OTP to the frontend strictly for testing purposes during prototype phase
        return {"status": "success", "message": "OTP dispatched", "test_otp": otp_code}
    raise HTTPException(status_code=500, detail="Failed to dispatch OTP email")
class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    meeting_url: str = "Link pending generation"
    ics_link: str = "ICS pending generation"

@app.post("/verify-payment")
async def verify_payment(data: VerifyPaymentRequest):
    try:
        # 1. Cryptographically verify the payment signature
        razorpay_client.utility.verify_payment_signature({
    'razorpay_order_id': data.razorpay_order_id,
    'razorpay_payment_id': data.razorpay_payment_id,
    'razorpay_signature': data.razorpay_signature
})
        # 2. Securely fetch the order from Razorpay to check the amount
        order = razorpay_client.order.fetch(data.razorpay_order_id)
        amount_in_rupees = order['amount'] / 100

        # 3. Internal Team Routing
        subject = "New Booking via Voice Agent"
        body = (
            f"A new payment of ₹{amount_in_rupees} was successfully verified.\n\n"
            f"Order ID: {data.razorpay_order_id}\n"
            f"Payment ID: {data.razorpay_payment_id}\n"
            f"Google Meet Link: {data.meeting_url}\n"
            f"Calendar ICS: {data.ics_link}"
        )

        if amount_in_rupees == 100:
            send_email_dispatch("reception@aanandi.in", f"Enquiry: {subject}", body)
        elif amount_in_rupees == 500:
            send_email_dispatch("tech-leads@aanandi.in", f"Project: {subject}", body)

        return {"status": "success", "message": "Payment verified and internal teams notified."}
        
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ── 1. Form Interceptor Endpoint ──────────────────────────────────────
class LeadInterceptPayload(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    brief: str | None = None
    session_id: str

@app.post("/api/v1/lead/intercept")
async def intercept_lead(lead: LeadInterceptPayload):
    doc = lead.model_dump()
    doc["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        res = await leads_collection.update_one(
            {"session_id": lead.session_id},
            {"$set": doc},
            upsert=True
        )
        lead_id = str(res.upserted_id) if res.upserted_id else lead.session_id
    except Exception:
        lead_id = lead.session_id
    return {"status": "success", "lead_id": lead_id}

# ── 2. Real-Time Chat WebSocket (LangGraph Streaming) ────────────────
@app.websocket("/api/v1/chat/stream")
async def chat_stream_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    config = {"configurable": {"thread_id": session_id}}

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)

            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if data.get("type") == "message":
                user_text = data.get("content", "")

                lead_data = {}
                try:
                    lead_data = await leads_collection.find_one({"session_id": session_id}) or {}
                except Exception:
                    pass

                input_state = {
                    "messages": [HumanMessage(content=user_text)],
                    "lead_stage": lead_data.get("pipelineStage", "QUALIFYING"),
                    "bant_score": lead_data.get("qualificationScore", 3),
                    "user_email": lead_data.get("email", ""),
                    "user_name": lead_data.get("full_name", "Lead"),
                    "needs_human": False
                }

                # Run LangGraph Agent
                result = await sales_agent.ainvoke(input_state, config=config)
                last_message = result["messages"][-1]
                response_content = last_message.content

                tool_payload = None
                if result.get("lead_stage") in ["BOOKING_OFFERED", "CALL_BOOKED"]:
                    tool_payload = {"type": "calendar", "data": {}}

                # Stream response back to client
                await websocket.send_text(json.dumps({
                    "type": "message",
                    "content": response_content,
                    "tool_payload": tool_payload
                }))
                await websocket.send_text(json.dumps({"type": "message_end"}))

    except WebSocketDisconnect:
        pass

# ── 3. Real-Time Voice WebSocket (Pipecat Audio Stream) ─────────────
@app.websocket("/api/v1/voice/ws/{session_id}")
async def voice_websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    transport = WebsocketServerTransport(
        websocket=websocket,
        params=WebsocketServerParams()
    )
    await run_voice_agent(transport)

# ── 4. Calendar Scheduling Availability & Booking ─────────────────────
def _cal_scheduling_config() -> tuple[str, int, str]:
    api_key = os.getenv("CAL_API_KEY") or os.getenv("CAL_COM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Cal.com scheduling is not configured.")

    try:
        event_type_id = int(os.getenv("CAL_EVENT_TYPE_ID", "7297448"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="CAL_EVENT_TYPE_ID must be an integer.") from exc

    return api_key, event_type_id, os.getenv("CAL_TIME_ZONE", "Asia/Kolkata")


@app.get("/api/v1/scheduling/availability")
async def get_availability(session_id: str, week_offset: int = 0):
    api_key, event_type_id, time_zone = _cal_scheduling_config()
    start_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1 + week_offset * 7)
    end_date = start_date + datetime.timedelta(days=4)

    try:
        response = await asyncio.to_thread(
            requests.get,
            "https://api.cal.com/v2/slots",
            params={
                "eventTypeId": event_type_id,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "timeZone": time_zone,
                "format": "range",
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "cal-api-version": "2024-09-04",
            },
            timeout=15,
        )
        if not response.ok:
            print(f"[CAL.COM] Availability request failed with status {response.status_code}.", flush=True)
            raise HTTPException(status_code=502, detail="Cal.com could not load availability.")
        calendar_data = response.json().get("data")
    except requests.RequestException as exc:
        print(f"[CAL.COM] Availability request failed: {type(exc).__name__}.", flush=True)
        raise HTTPException(status_code=502, detail="Cal.com could not load availability.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cal.com returned an invalid availability response.") from exc

    if isinstance(calendar_data, dict) and "slots" in calendar_data:
        calendar_data = calendar_data["slots"]
    if not isinstance(calendar_data, dict):
        raise HTTPException(status_code=502, detail="Cal.com returned an invalid availability response.")

    slots = []
    for day_slots in calendar_data.values():
        if not isinstance(day_slots, list):
            raise HTTPException(status_code=502, detail="Cal.com returned an invalid availability response.")
        for slot in day_slots:
            if not isinstance(slot, dict) or not slot.get("start") or not slot.get("end"):
                raise HTTPException(status_code=502, detail="Cal.com returned an invalid availability response.")
            slots.append({"start": slot["start"], "end": slot["end"], "available": True})

    slots.sort(key=lambda slot: slot["start"])
    return {"slots": slots}

class BookingRequest(BaseModel):
    slot_start: str
    slot_end: str
    lead_id: str
    session_id: str
    tier: str | None = "enquiry"
    user_email: str | None = None

@app.post("/api/v1/scheduling/book")
async def book_slot(payload: BookingRequest):
    api_key, event_type_id, time_zone = _cal_scheduling_config()
    lead = {}
    try:
        lead = await leads_collection.find_one({"session_id": payload.session_id}) or {}
    except Exception as exc:
        print(f"[CAL.COM] Could not load lead details: {type(exc).__name__}.", flush=True)
        if not payload.user_email:
            raise HTTPException(status_code=503, detail="Could not retrieve the attendee email address.") from exc

    user_email = payload.user_email or lead.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="An attendee email address is required to book this meeting.")
    user_name = lead.get("full_name") or "Valued Client"

    try:
        dt_start = datetime.datetime.fromisoformat(payload.slot_start.replace("Z", "+00:00"))
        if dt_start.tzinfo is None:
            raise ValueError("slot_start must include a timezone")
        start_iso = dt_start.astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        start_fmt = dt_start.strftime("%A, %B %d, %Y at %I:%M %p %Z")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="slot_start must be a valid timezone-aware ISO date.") from exc

    try:
        response = await asyncio.to_thread(
            requests.post,
            "https://api.cal.com/v2/bookings",
            json={
                "eventTypeId": event_type_id,
                "start": start_iso,
                "attendee": {
                    "name": user_name,
                    "email": user_email,
                    "timeZone": time_zone,
                    "language": "en",
                },
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "cal-api-version": "2024-08-13",
            },
            timeout=15,
        )
        if response.status_code == 409:
            raise HTTPException(status_code=409, detail="That Cal.com slot is no longer available. Please choose another time.")
        if not response.ok:
            print(f"[CAL.COM] Booking request failed with status {response.status_code}.", flush=True)
            raise HTTPException(status_code=502, detail="Cal.com rejected the booking. Check the event type and attendee details.")
        booking_data = response.json().get("data")
    except requests.RequestException as exc:
        print(f"[CAL.COM] Booking request failed: {type(exc).__name__}.", flush=True)
        raise HTTPException(status_code=502, detail="Cal.com could not confirm the booking.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Cal.com returned an invalid booking response.") from exc

    if not isinstance(booking_data, dict) or not booking_data.get("id"):
        raise HTTPException(status_code=502, detail="Cal.com returned an invalid booking response.")

    meeting_url = booking_data.get("meetingUrl")
    client_body = (
        f"Hello {user_name},\n\n"
        f"Your call with Aanandi TechnoSoft ({payload.tier.upper() if payload.tier else 'ENQUIRY'} Tier) has been confirmed!\n\n"
        f"Scheduled Time: {start_fmt}\n"
        f"Meeting Link: {meeting_url or 'See the Cal.com calendar invitation'}\n\n"
        "We look forward to speaking with you!"
    )
    send_email_dispatch(user_email, "Booking Confirmed: Call Scheduled with Aanandi TechnoSoft", client_body)

    team_email = (
        os.getenv("TECH_TEAM_EMAIL", "asmiupadhyay491@gmail.com")
        if payload.tier == "project"
        else os.getenv("RECEPTIONIST_EMAIL", "pyashkumar0312@gmail.com")
    )
    team_body = (
        "New Booking Confirmed!\n\n"
        f"Lead Name: {user_name}\n"
        f"Lead Email: {user_email}\n"
        f"Session ID: {payload.session_id}\n"
        f"Tier: {payload.tier or 'enquiry'}\n"
        f"Scheduled Time: {start_fmt}\n"
        f"Cal.com Booking ID: {booking_data['id']}\n"
        f"Meeting Link: {meeting_url or 'See the Cal.com calendar invitation'}\n"
    )
    send_email_dispatch(team_email, f"New Confirmed Booking ({payload.tier or 'enquiry'})", team_body)

    return {
        "status": "confirmed",
        "booking_id": booking_data["id"],
        "meeting_url": meeting_url,
        "email_sent_to": user_email,
        "scheduled_time": start_fmt,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)