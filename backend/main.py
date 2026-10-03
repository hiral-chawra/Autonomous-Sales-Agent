import os
import razorpay
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Pipecat Imports
from pipecat.transports.websocket.server import WebsocketServerTransport, WebsocketServerParams
from bot import run_voice_agent
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Razorpay client using the keys from your .env file
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

# Define the expected data format from the frontend
class OrderRequest(BaseModel):
    amount: int

@app.post("/create-order")
async def create_order(order: OrderRequest):
    try:
        # Razorpay expects the amount in paise (multiply INR by 100)
        order_data = {
            "amount": order.amount * 100,
            "currency": "INR",
            "payment_capture": 1 # Auto-capture the payment
        }

        # Create the order on Razorpay's servers
        razorpay_order = razorpay_client.order.create(data=order_data)

        # Return the generated Order ID to the frontend
        return {"order_id": razorpay_order["id"], "amount": order_data["amount"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/verify-payment")
async def verify_payment(request: Request):
    # Retrieve the payment details sent by the frontend after checkout
    data = await request.json()

    try:
        # Verify the cryptographic signature to ensure the payment is authentic
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': data.get('razorpay_order_id'),
            'razorpay_payment_id': data.get('razorpay_payment_id'),
            'razorpay_signature': data.get('razorpay_signature')
        })

        return {"status": "success", "message": "Payment verified securely"}

    except razorpay.errors.SignatureVerificationError:
        # If the signature doesn't match, reject the request
        raise HTTPException(status_code=400, detail="Invalid payment signature")

# Your existing Pipecat Voice AI Endpoint
@app.websocket("/ws/call-ai")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    transport = WebsocketServerTransport(
        websocket=websocket,
        params=WebsocketServerParams()
    )
    await run_voice_agent(transport)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)