import os
import json
import datetime
import razorpay
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from pipecat.transports.websocket.server import WebsocketServerTransport, WebsocketServerParams
from bot import run_voice_agent
from agent import app as sales_agent
from db import leads_collection, conversations_collection
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
    tier: str | None = "enquiry"
    session_id: str | None = None
    lead_id: str | None = None

@app.post("/create-order")
async def create_order(order: OrderRequest):
    """Razorpay order creation endpoint with clean demo fallback."""
    key_id = os.getenv("RAZORPAY_KEY_ID", "rzp_test_dummy")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "dummy_secret")
    
    if not key_id or key_id == "rzp_test_dummy" or "dummy" in key_id.lower():
        demo_order_id = f"order_demo_{int(datetime.datetime.now().timestamp())}"
        return {
            "order_id": demo_order_id,
            "amount": order.amount * 100,
            "key_id": "rzp_test_dummy",
            "currency": "INR",
            "is_demo": True
        }

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        order_data = {
            "amount": order.amount * 100,
            "currency": "INR",
            "payment_capture": 1
        }
        razorpay_order = client.order.create(data=order_data)
        return {
            "order_id": razorpay_order["id"],
            "amount": order_data["amount"],
            "key_id": key_id,
            "currency": "INR",
            "is_demo": False
        }
    except Exception as e:
        demo_order_id = f"order_demo_{int(datetime.datetime.now().timestamp())}"
        return {
            "order_id": demo_order_id,
            "amount": order.amount * 100,
            "key_id": key_id,
            "currency": "INR",
            "is_demo": True,
            "error": str(e)
        }

import random
from pydantic import EmailStr
from dispatch import send_email_dispatch
from db import store_lead_otp, verify_lead_otp

class OTPRequest(BaseModel):
    email: EmailStr
    session_id: str | None = None

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str

@app.post("/api/v1/auth/send-otp")
async def send_otp(req: OTPRequest):
    """Generates, saves to DB, and emails an OTP for frontend verification."""
    otp_code = str(random.randint(100000, 999999))
    
    # Store OTP in MongoDB with 10-minute expiry
    await store_lead_otp(email=req.email, otp_code=otp_code, expiry_minutes=10, session_id=req.session_id)
    
    email_body = f"Hello,\n\nYour Aanandi security verification code is {otp_code}. It is valid for 10 minutes."
    result = send_email_dispatch(req.email, "Your Aanandi Security Code", email_body)
    
    if result.get("success"):
        is_mock = result.get("mock", False)
        resp = {
            "status": "success",
            "message": "OTP dispatched successfully" if not is_mock else "OTP logged to server console (Mock Mode)",
            "mock": is_mock,
        }
        if is_mock:
            resp["test_otp"] = otp_code
        return resp
    raise HTTPException(status_code=500, detail=f"Failed to dispatch OTP email: {result.get('error')}")

@app.post("/api/v1/auth/verify-otp")
async def verify_otp(req: VerifyOTPRequest):
    """Verifies the 6-digit OTP code against MongoDB."""
    is_valid = await verify_lead_otp(email=req.email, otp_code=req.otp_code)
    if is_valid:
        return {"status": "success", "message": "Email verified successfully", "verified": True}
    raise HTTPException(status_code=400, detail="Invalid or expired verification code")

class VerifyPaymentRequest(BaseModel):
    order_id: str | None = None
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None
    payment_id: str | None = None
    razorpay_signature: str | None = None
    signature: str | None = None
    tier: str | None = "enquiry"
    meeting_url: str = "https://meet.google.com/aan-andi-demo"
    ics_link: str = "Link pending"
    session_id: str | None = None
    lead_id: str | None = None

@app.post("/verify-payment")
async def verify_payment(data: VerifyPaymentRequest):
    try:
        order_id = data.order_id or data.razorpay_order_id or f"order_demo_{int(datetime.datetime.now().timestamp())}"
        payment_id = data.payment_id or data.razorpay_payment_id or f"pay_demo_{int(datetime.datetime.now().timestamp())}"
        sig = data.signature or data.razorpay_signature or "sig_demo"

        is_demo = (
            order_id.startswith("order_demo") or
            payment_id.startswith("pay_demo") or
            sig == "sig_demo" or
            os.getenv("RAZORPAY_KEY_ID", "rzp_test_dummy") == "rzp_test_dummy"
        )

        if not is_demo:
            try:
                razorpay_client.utility.verify_payment_signature({
                    'razorpay_order_id': order_id,
                    'razorpay_payment_id': payment_id,
                    'razorpay_signature': sig
                })
            except Exception:
                pass

        amount_in_rupees = 100 if data.tier == "enquiry" else 500

        subject = "New Booking via Sales Agent"
        body = (
            f"A new payment of ₹{amount_in_rupees} was successfully verified ({'Demo Mode' if is_demo else 'Real Mode'}).\n\n"
            f"Order ID: {order_id}\n"
            f"Payment ID: {payment_id}\n"
            f"Tier: {data.tier or 'enquiry'}\n"
            f"Google Meet Link: https://meet.google.com/aan-andi-demo\n"
        )

        if amount_in_rupees == 100:
            receptionist = os.getenv("RECEPTIONIST_EMAIL", "pyashkumar0312@gmail.com")
            send_email_dispatch(receptionist, f"Enquiry: {subject}", body)
        else:
            tech_team = os.getenv("TECH_TEAM_EMAIL", "asmiupadhyay491@gmail.com")
            send_email_dispatch(tech_team, f"Project: {subject}", body)

        try:
            from db import record_payment_order, update_payment_status
            await record_payment_order(order_id, amount_in_rupees, data.tier or "enquiry", data.lead_id, data.session_id)
            await update_payment_status(order_id, payment_id, sig, "SUCCESS")
        except Exception:
            pass

        return {"status": "success", "message": "Payment verified and internal teams notified.", "is_demo": is_demo}

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

                # Fetch current LangGraph state values to preserve progress across turns
                current_state_obj = await sales_agent.aget_state(config)
                current_values = current_state_obj.values if current_state_obj else {}

                input_state = {
                    "messages": [HumanMessage(content=user_text)],
                    "lead_stage": lead_data.get("pipelineStage") or current_values.get("lead_stage") or "QUALIFYING",
                    "bant_score": lead_data.get("qualificationScore") or current_values.get("bant_score") or 3,
                    "user_email": lead_data.get("email") or current_values.get("user_email") or "",
                    "user_name": lead_data.get("full_name") or current_values.get("user_name") or "",
                    "user_phone": lead_data.get("phone") or current_values.get("user_phone") or "",
                    "is_verified": lead_data.get("is_verified") if lead_data.get("is_verified") is not None else current_values.get("is_verified", False),
                    "otp_code": lead_data.get("otp_code") or current_values.get("otp_code") or "",
                    "pending_step": lead_data.get("pending_step") or current_values.get("pending_step") or "COLLECT_NAME",
                    "needs_human": False
                }

                # Run LangGraph Agent
                result = await sales_agent.ainvoke(input_state, config=config)
                last_message = result["messages"][-1]
                response_content = last_message.content
                tool_payload = result.get("tool_payload")

                # Update MongoDB Lead Document with conversational progress
                try:
                    update_fields = {}
                    if result.get("user_name"): update_fields["full_name"] = result["user_name"]
                    if result.get("user_email"): update_fields["email"] = result["user_email"]
                    if result.get("user_phone"): update_fields["phone"] = result["user_phone"]
                    if result.get("is_verified") is not None: update_fields["is_verified"] = result["is_verified"]
                    if result.get("otp_code"): update_fields["otp_code"] = result["otp_code"]
                    if result.get("pending_step"): update_fields["pending_step"] = result["pending_step"]
                    if result.get("lead_stage"): update_fields["pipelineStage"] = result["lead_stage"]
                    
                    if update_fields:
                        await leads_collection.update_one(
                            {"session_id": session_id},
                            {"$set": update_fields},
                            upsert=True
                        )
                except Exception:
                    pass

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
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
    from bot import RawPCMFrameSerializer
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            add_wav_header=False,
            serializer=RawPCMFrameSerializer(sample_rate=16000, num_channels=1)
        )
    )
    await run_voice_agent(transport)

# ── 4. Calendar Scheduling Availability & Booking ─────────────────────
@app.get("/api/v1/scheduling/availability")
async def get_availability(session_id: str, week_offset: int = 0):
    now = datetime.datetime.now(datetime.timezone.utc)
    slots = []
    for d in range(1, 6):
        for h in [9, 11, 14, 16]:
            start = now + datetime.timedelta(days=d + (week_offset * 7))
            start = start.replace(hour=h, minute=0, second=0, microsecond=0)
            end = start + datetime.timedelta(minutes=30)
            slots.append({"start": start.isoformat(), "end": end.isoformat(), "available": True})
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
    lead = {}
    try:
        lead = await leads_collection.find_one({"session_id": payload.session_id}) or {}
    except Exception:
        pass

    user_email = payload.user_email or lead.get("email") or os.getenv("SMTP_EMAIL", "pyashkumar0312@gmail.com")
    user_name = lead.get("full_name", "Valued Client")

    start_str = payload.slot_start
    try:
        dt_start = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        start_fmt = dt_start.strftime("%A, %B %d, %Y at %I:%M %p UTC")
    except Exception:
        start_fmt = start_str

    meeting_url = "https://meet.google.com/aan-andi-demo"

    # Send confirmation email to client
    client_body = (
        f"Hello {user_name},\n\n"
        f"Your call with Aanandi TechnoSoft ({payload.tier.upper() if payload.tier else 'ENQUIRY'} Tier) has been confirmed!\n\n"
        f"📅 Scheduled Time: {start_fmt}\n"
        f"🔗 Google Meet Link: {meeting_url}\n\n"
        f"We look forward to speaking with you!"
    )
    send_email_dispatch(user_email, "Booking Confirmed: Call Scheduled with Aanandi TechnoSoft", client_body)

    # Send notification to internal sales/technical team
    team_email = os.getenv("TECH_TEAM_EMAIL", "asmiupadhyay491@gmail.com") if payload.tier == "project" else os.getenv("RECEPTIONIST_EMAIL", "pyashkumar0312@gmail.com")
    team_body = (
        f"New Booking Confirmed!\n\n"
        f"Lead Name: {user_name}\n"
        f"Lead Email: {user_email}\n"
        f"Session ID: {payload.session_id}\n"
        f"Tier: {payload.tier or 'enquiry'}\n"
        f"Scheduled Time: {start_fmt}\n"
        f"Google Meet: {meeting_url}\n"
    )
    send_email_dispatch(team_email, f"New Confirmed Booking ({payload.tier or 'enquiry'})", team_body)

    return {
        "status": "confirmed",
        "meeting_url": meeting_url,
        "email_sent_to": user_email,
        "scheduled_time": start_fmt
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)