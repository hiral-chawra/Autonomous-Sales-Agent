import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[os.getenv("MONGODB_DB_NAME", "aanandi_sales")]

# Database Collections
leads_collection = db["leads"]
conversations_collection = db["conversations"]
payment_transactions_collection = db["payment_transactions"]
booking_records_collection = db["booking_records"]

# ── OTP & Lead Helpers ────────────────────────────────────────────────────────
async def store_lead_otp(email: str, otp_code: str, expiry_minutes: int = 10, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Stores a 6-digit OTP and its expiration timestamp in the leads document.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expiry_minutes)
    
    update_data = {
        "email": email.strip().lower(),
        "otp_code": str(otp_code),
        "otp_expires_at": expires_at,
        "is_verified": False,
        "updated_at": now
    }
    if session_id:
        update_data["session_id"] = session_id
        
    result = await leads_collection.find_one_and_update(
        {"email": email.strip().lower()},
        {"$set": update_data},
        upsert=True,
        return_document=True
    )
    return result

async def verify_lead_otp(email: str, otp_code: str) -> bool:
    """
    Verifies the OTP code against MongoDB for the given lead.
    If valid and not expired, sets is_verified to True.
    """
    now = datetime.now(timezone.utc)
    lead = await leads_collection.find_one({"email": email.strip().lower()})
    
    if not lead:
        return False
        
    stored_otp = lead.get("otp_code")
    expires_at = lead.get("otp_expires_at")
    
    # Ensure datetime object is timezone aware if needed
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
        
    if stored_otp == str(otp_code) and expires_at and expires_at > now:
        await leads_collection.update_one(
            {"_id": lead["_id"]},
            {"$set": {"is_verified": True, "otp_code": None, "updated_at": now}}
        )
        return True
        
    return False

# ── Payment Transactions Helpers ──────────────────────────────────────────────
async def record_payment_order(
    order_id: str,
    amount: int,
    tier: str,
    lead_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Records a new Razorpay payment order in the payment_transactions collection.
    """
    now = datetime.now(timezone.utc)
    doc = {
        "transaction_id": order_id,
        "order_id": order_id,
        "payment_id": None,
        "signature": None,
        "amount": amount, # 100 or 500
        "currency": "INR",
        "tier": tier, # 'enquiry' or 'project'
        "status": "PENDING",
        "lead_id": lead_id,
        "session_id": session_id,
        "created_at": now,
        "updated_at": now
    }
    await payment_transactions_collection.insert_one(doc)
    return doc

async def update_payment_status(
    order_id: str,
    payment_id: str,
    signature: str,
    status: str = "SUCCESS"
) -> bool:
    """
    Updates the transaction status (SUCCESS/FAILED) after Razorpay verification.
    """
    now = datetime.now(timezone.utc)
    result = await payment_transactions_collection.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "payment_id": payment_id,
                "signature": signature,
                "status": status,
                "updated_at": now
            }
        }
    )
    return result.modified_count > 0

# ── Booking Records Helpers ───────────────────────────────────────────────────
async def create_booking_record(
    meeting_type: str,
    assigned_team: str,
    lead_id: Optional[str] = None,
    session_id: Optional[str] = None,
    meeting_url: Optional[str] = None,
    start_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a record of a booked meeting in the booking_records collection.
    """
    now = datetime.now(timezone.utc)
    doc = {
        "lead_id": lead_id,
        "session_id": session_id,
        "meeting_type": meeting_type, # 'Enquiry' or 'Project'
        "assigned_team": assigned_team, # 'receptionist' or 'technical_team'
        "meeting_url": meeting_url,
        "start_time": start_time,
        "created_at": now
    }
    await booking_records_collection.insert_one(doc)
    return doc

