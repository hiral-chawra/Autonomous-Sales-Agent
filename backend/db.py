import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=2000)
db = client[os.getenv("MONGODB_DB_NAME", "aanandi_sales")]

# Database Collections
leads_collection = db["leads"]
conversations_collection = db["conversations"]
payment_transactions_collection = db["payment_transactions"]
booking_records_collection = db["booking_records"]

# In-memory fallback for when MongoDB is offline
_in_memory_otps: Dict[str, Any] = {}

# ── OTP & Lead Helpers ────────────────────────────────────────────────────────
async def store_lead_otp(email: str, otp_code: str, expiry_minutes: int = 10, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Stores a 6-digit OTP and its expiration timestamp in the leads document or in-memory fallback.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expiry_minutes)
    clean_email = email.strip().lower()
    
    update_data = {
        "email": clean_email,
        "otp_code": str(otp_code),
        "otp_expires_at": expires_at,
        "is_verified": False,
        "updated_at": now
    }
    if session_id:
        update_data["session_id"] = session_id

    _in_memory_otps[clean_email] = update_data

    try:
        result = await leads_collection.find_one_and_update(
            {"email": clean_email},
            {"$set": update_data},
            upsert=True,
            return_document=True
        )
        return result or update_data
    except Exception as e:
        print(f"[DB NOTICE] MongoDB unavailable ({e}), using in-memory OTP storage.")
        return update_data

async def verify_lead_otp(email: str, otp_code: str) -> bool:
    """
    Verifies the OTP code against MongoDB or in-memory storage.
    If valid and not expired, sets is_verified to True.
    """
    now = datetime.now(timezone.utc)
    clean_email = email.strip().lower()

    # 1. Try Mongo DB
    try:
        lead = await leads_collection.find_one({"email": clean_email})
        if lead:
            stored_otp = lead.get("otp_code")
            expires_at = lead.get("otp_expires_at")
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
                
            if stored_otp == str(otp_code) and expires_at and expires_at > now:
                await leads_collection.update_one(
                    {"_id": lead["_id"]},
                    {"$set": {"is_verified": True, "otp_code": None, "updated_at": now}}
                )
                return True
    except Exception:
        pass

    # 2. Try In-Memory Fallback
    memory_data = _in_memory_otps.get(clean_email)
    if memory_data:
        stored_otp = memory_data.get("otp_code")
        expires_at = memory_data.get("otp_expires_at")
        if stored_otp == str(otp_code) and expires_at and expires_at > now:
            memory_data["is_verified"] = True
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

