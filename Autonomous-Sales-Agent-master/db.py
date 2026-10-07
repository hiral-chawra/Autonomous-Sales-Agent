import os
from datetime import datetime, timezone
from typing import Optional, List
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/crm_db")

Base = declarative_base()

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(50), nullable=True)
    stage = Column(String(50), default="NEW_LEAD", nullable=False, index=True)
    bant_score = Column(Integer, default=1)
    pain_points = Column(Text, nullable=True)
    last_activity = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    follow_up_count = Column(Integer, default=0)

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(String(255), nullable=False, unique=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    title = Column(String(255), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    meeting_url = Column(String(500), nullable=True)
    user_present = Column(Boolean, default=False)
    telephony_triggered = Column(Boolean, default=False)

def get_engine():
    db_url = os.getenv("DATABASE_URL", "sqlite:///crm.db")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
    if db_url.startswith("sqlite"):
        return create_engine(db_url, connect_args={"check_same_thread": False})
    
    try:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        # Test connection
        with engine.connect() as conn:
            pass
        return engine
    except Exception:
        # Fallback to local SQLite if PostgreSQL server is not currently reachable
        return create_engine("sqlite:///crm.db", connect_args={"check_same_thread": False})

def get_db_session():
    engine = get_engine()
    session_factory = sessionmaker(bind=engine)
    return scoped_session(session_factory)()

def init_db():
    """Initializes the database schema."""
    engine = get_engine()
    Base.metadata.create_all(engine)


