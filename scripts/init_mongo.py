"""
MongoDB Atlas Initialization & Index Management Script
Creates all required compound B-Tree indexes, unique constraints,
and seeds initial knowledge chunks for Vector Search.
"""

import os
import sys
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv, find_dotenv

# Ensure backend directory is in python path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

load_dotenv(find_dotenv(usecwd=True))

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from models import ALL_DOCUMENT_MODELS, KnowledgeChunk, Lead, Conversation, FollowUpQueue
from pymongo import ASCENDING, DESCENDING, IndexModel

ATLAS_VECTOR_SEARCH_INDEX_JSON = {
    "name": "vector_index",
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 1536,
                "similarity": "cosine"
            },
            {
                "type": "filter",
                "path": "category"
            }
        ]
    }
}

SEED_KNOWLEDGE = [
    {
        "title": "Aanandi TechnoSoft Overview & Core Capabilities",
        "category": "capabilities",
        "content": (
            "Aanandi TechnoSoft designs, engineers, and deploys high-availability Autonomous AI Agents, "
            "multimodal sales widgets, and workflow automation. Our stack features FastAPI, LangGraph, "
            "Pipecat AI, Web Audio/WebRTC, MongoDB Atlas Vector Search, and sub-100ms TTS/STT pipelines."
        )
    },
    {
        "title": "Healthcare & Telemedicine AI Solutions",
        "category": "case_studies",
        "content": (
            "Case Study: Automated patient intake and voice triage assistant integrated with EHR systems. "
            "Achieved 99.9% uptime, reduced appointment booking friction by 74%, and handled HIPAA-compliant "
            "pre-consultation symptoms collection with real-time human agent handoff."
        )
    },
    {
        "title": "FinTech Lead Qualification & KYC Automation",
        "category": "case_studies",
        "content": (
            "Case Study: Real-time fraud detection and KYC intake bot. Provided instant BANT qualification, "
            "verified identities with automated OTP SMS/email flows, and routed high-net-worth prospects "
            "directly to certified wealth management advisors within 90 seconds."
        )
    },
    {
        "title": "Enterprise CRM & Custom Workflow Orchestration",
        "category": "case_studies",
        "content": (
            "Case Study: Bi-directional synchronization agents connecting sales chats with Salesforce, "
            "HubSpot, and Zoho CRM. Features automated calendar scheduling via Cal.com API v2 and upfront "
            "escrow/deposit commitment payments via Razorpay QR codes."
        )
    }
]

async def init_mongodb():
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB_NAME", "aanandi_sales")
    
    print(f"[*] Connecting to MongoDB at {mongo_url} (Database: {db_name})...")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=4000)
    db = client[db_name]

    try:
        await init_beanie(database=db, document_models=ALL_DOCUMENT_MODELS)
        print("[+] Beanie ODM initialized successfully.")

        # 1. Compound B-Tree Index for Sub-Millisecond 90s Cron Sweeps
        print("[*] Creating compound index on follow_up_queue (status, scheduled_at)...")
        await db["follow_up_queue"].create_index(
            [("status", ASCENDING), ("scheduled_at", ASCENDING)],
            name="idx_status_scheduled_at"
        )

        # 2. Unique index on Lead emails
        print("[*] Creating unique index on leads (email)...")
        await db["leads"].create_index(
            [("email", ASCENDING)],
            unique=True,
            name="uniq_lead_email"
        )

        # 3. Unique index on Conversations session_id
        print("[*] Creating unique index on conversations (session_id)...")
        await db["conversations"].create_index(
            [("session_id", ASCENDING)],
            unique=True,
            name="uniq_conversation_session_id"
        )

        # 4. Unique index on Payment Transactions order_id
        print("[*] Creating unique index on payment_transactions (order_id)...")
        await db["payment_transactions"].create_index(
            [("order_id", ASCENDING)],
            unique=True,
            name="uniq_payment_order_id"
        )

        # 5. Indexes on Booking Records and Call Logs
        print("[*] Creating lookup indexes on booking_records and call_logs...")
        await db["booking_records"].create_index([("session_id", ASCENDING)], name="idx_booking_session_id")
        await db["call_logs"].create_index([("session_id", ASCENDING)], name="idx_call_session_id")

        # 6. Seed Knowledge Chunks for Vector Search if empty
        existing_chunks = await KnowledgeChunk.count()
        print(f"[*] Knowledge chunks in database: {existing_chunks}")
        if existing_chunks == 0:
            print("[*] Seeding initial knowledge chunks...")
            openai_key = os.getenv("OPENAI_API_KEY", "")
            embeddings_model = None
            if openai_key and not openai_key.startswith("sk-dummy"):
                try:
                    from langchain_openai import OpenAIEmbeddings
                    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_key)
                except Exception as e:
                    print(f"[!] Embeddings model initialization notice: {e}")

            for item in SEED_KNOWLEDGE:
                vec = [0.0] * 1536
                if embeddings_model:
                    try:
                        vec = await embeddings_model.aembed_query(item["content"])
                    except Exception:
                        vec = [0.0] * 1536
                
                chunk = KnowledgeChunk(
                    title=item["title"],
                    content=item["content"],
                    category=item["category"],
                    embedding=vec,
                    created_at=datetime.now(timezone.utc)
                )
                await chunk.insert()
            print(f"[+] Seeded {len(SEED_KNOWLEDGE)} knowledge chunks.")

        print("\n" + "=" * 60)
        print("MongoDB Atlas Vector Search Index Configuration:")
        print("=" * 60)
        import json
        print(json.dumps(ATLAS_VECTOR_SEARCH_INDEX_JSON, indent=2))
        print("=" * 60)
        print("[SUCCESS] MongoDB initialization and indexing completed successfully.\n")

    except Exception as e:
        print(f"\n[!] Note: Could not connect to MongoDB cluster at {mongo_url}: {e}")
        print("[!] When deploying to Atlas M10+, provide MONGODB_URL in your .env file.")
        print("\n" + "=" * 60)
        print("MongoDB Atlas Vector Search Index JSON (to paste into Atlas JSON editor):")
        print("=" * 60)
        import json
        print(json.dumps(ATLAS_VECTOR_SEARCH_INDEX_JSON, indent=2))
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(init_mongodb())
