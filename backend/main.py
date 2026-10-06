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

@app.post("/api/v1/scheduling/book")
async def book_slot(payload: BookingRequest):
    return {
        "status": "confirmed",
        "meeting_url": "https://meet.google.com/aan-andi-demo"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)