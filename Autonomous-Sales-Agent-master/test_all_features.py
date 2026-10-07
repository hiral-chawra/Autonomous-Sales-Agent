import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load env variables
load_dotenv()

from agent import app as langgraph_app, AgentState
from langchain_core.messages import HumanMessage
from db import get_db_session, init_db, Lead, Meeting
from dispatch import send_email_via_resend, send_whatsapp_message, trigger_outbound_voice_telephony
from tasks import execute_follow_up_sweep, t_minus_2_minute_nudge

import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def run_tests():
    print("=" * 70)
    print("[*] STARTING COMPLETE SYSTEM INTEGRATION TESTS")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. Database Schema Initialization & Seeding
    # -------------------------------------------------------------
    print("\n[TEST 1] Initializing Database Schema & Seeding Test Data...")
    init_db()
    session = get_db_session()
    
    # Clean up old test data if exists
    session.query(Lead).filter(Lead.email == "test.lead@example.com").delete()
    session.query(Meeting).filter(Meeting.meeting_id == "test_meeting_999").delete()
    session.commit()

    # Create a test lead stalled for 50 hours in BOOKING_OFFERED stage
    stalled_time = datetime.now(timezone.utc) - timedelta(hours=50)
    test_lead = Lead(
        name="Sarah Jenkins",
        email="test.lead@example.com",
        phone="+15551234567",
        stage="BOOKING_OFFERED",
        bant_score=8,
        pain_points="High API latency and lack of SOC2 compliant automated follow-ups",
        last_activity=stalled_time,
        follow_up_count=0
    )
    session.add(test_lead)
    session.commit()
    print(f"[+] Created Lead #{test_lead.id}: {test_lead.name} ({test_lead.stage}) - Last active 50h ago.")

    # Create a test meeting
    test_meeting = Meeting(
        meeting_id="test_meeting_999",
        lead_id=test_lead.id,
        title="Enterprise Architecture Deep-Dive",
        start_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        meeting_url="https://meet.google.com/abc-defg-hij",
        user_present=False,
        telephony_triggered=False
    )
    session.add(test_meeting)
    session.commit()
    print(f"[+] Created Meeting #{test_meeting.meeting_id} for Lead #{test_lead.id}.")

    # -------------------------------------------------------------
    # 2. Test LangGraph Agent Workflow with Thread Checkpoint
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing LangGraph Multi-Turn Workflow with Checkpointer...")
    thread_config = {"configurable": {"thread_id": f"lead_{test_lead.id}"}}
    user_prompt = "What kind of custom integrations and SLAs do you offer for enterprise tier?"
    
    state_input: AgentState = {
        "messages": [HumanMessage(content=user_prompt)],
        "lead_stage": "QUALIFYING",
        "bant_score": 7,
        "user_email": test_lead.email,
        "user_name": test_lead.name,
        "needs_human": False
    }
    
    agent_output = langgraph_app.invoke(state_input, config=thread_config)
    last_response = agent_output["messages"][-1].content
    print(f"[+] Agent Response: {last_response[:150]}...")
    assert len(last_response) > 0, "LangGraph response should not be empty"

    # -------------------------------------------------------------
    # 3. Test Resend Email Dispatch
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing Resend Email API Dispatch...")
    email_res = send_email_via_resend(
        to_email="delivered@resend.dev",  # Resend verified test inbox
        subject="Integration Test: Discovery Session Follow-up",
        text_content="Hi Sarah, this is a test notification confirming the Resend API integration is fully operational."
    )
    print(f"[+] Resend API Result: {email_res}")

    # -------------------------------------------------------------
    # 4. Test Celery 30-Minute Follow-up Sweep Task
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing Celery Task: execute_follow_up_sweep (Direct Execution)...")
    sweep_result = execute_follow_up_sweep.apply().get()
    print(f"[+] Sweep Task Result: {sweep_result}")
    
    # Verify DB was updated
    session.expire_all()
    updated_lead = session.query(Lead).filter(Lead.id == test_lead.id).first()
    print(f"[+] Lead Follow-up Count: {updated_lead.follow_up_count}")
    print(f"[+] Lead Last Activity: {updated_lead.last_activity}")
    assert updated_lead.follow_up_count >= 1, "Follow-up count should have incremented"

    # -------------------------------------------------------------
    # 5. Test Celery T-minus 2 Minute Nudge Task
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Celery Task: t_minus_2_minute_nudge...")
    t2_result = t_minus_2_minute_nudge.apply(args=["test_meeting_999"]).get()
    print(f"[+] T-2 Nudge Result: {t2_result}")

    # Verify meeting update in DB
    session.expire_all()
    updated_meeting = session.query(Meeting).filter(Meeting.meeting_id == "test_meeting_999").first()
    print(f"[+] Telephony Triggered Flag: {updated_meeting.telephony_triggered}")
    assert updated_meeting.telephony_triggered is True, "Telephony triggered flag should be True"

    session.close()
    print("\n" + "=" * 70)
    print("[SUCCESS] ALL 5 INTEGRATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
