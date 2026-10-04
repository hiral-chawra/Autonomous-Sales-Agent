import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[os.getenv("MONGODB_DB_NAME", "aanandi_sales")]
leads_collection = db["leads"]
conversations_collection = db["conversations"]
