import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv
from celery import Celery
from celery.schedules import crontab
from langchain_core.messages import HumanMessage
import requests

from agent import app as langgraph_app
from db import get_db_session, Lead, Meeting
from dispatch import send_email_dispatch, send_email_via_resend, send_whatsapp_message, trigger_outbound_voice_telephony

# Load environment configurations
load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CAL_API_KEY = os.getenv("CAL_API_KEY", "cal_live_a8263dd042c39125c54147f2a0709333")

# Initialize Celery app
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

# Configure Celery Beat for 30-minute recurring execution
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "execute-follow-up-sweep-every-30-mins": {
            "task": "tasks.execute_follow_up_sweep",
            "schedule": crontab(minute="*/30"),  # Runs every 30 minutes
        },
    },
)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_follow_up_sweep(self):
    """Runs via Celery Beat every 30 minutes.

    1. Queries PostgreSQL for leads where stage='BOOKING_OFFERED'
       AND last_activity < (NOW() - INTERVAL '48 hours')
    2. For each lead, invokes LangGraph to draft a context-aware nudge.
    3. Dispatches the follow-up message via Resend Email and WhatsApp.
    4. Updates CRM last_activity and follow-up metrics.
    """
    session = get_db_session()
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=48)
    
    try:
        stalled_leads = (
            session.query(Lead)
            .filter(Lead.stage == "BOOKING_OFFERED")
            .filter(Lead.last_activity <= cutoff_time)
            .all()
        )
        
        results = []
        for lead in stalled_leads:
            thread_id = f"lead_{lead.id}"
            pain_points_desc = lead.pain_points or "enterprise scalability and workflow automation"
            
            # 1. Invoke LangGraph with context-aware system nudge prompt
            prompt_content = (
                f"SYSTEM NUDGE: User {lead.name} ({lead.email}) was offered a booking but has not scheduled a call after 48 hours. "
                f"Their primary pain points are: {pain_points_desc}. "
                f"Draft a warm, persuasive step 1 follow-up nudge addressing their specific needs and invite them to book their slot."
            )
            
            inputs = {
                "messages": [HumanMessage(content=prompt_content)],
                "lead_stage": lead.stage,
                "bant_score": lead.bant_score or 5,
                "user_email": lead.email,
                "user_name": lead.name,
                "needs_human": False,
            }
            
            final_state = langgraph_app.invoke(
                inputs,
                config={"configurable": {"thread_id": thread_id}}
            )
            
            last_message = final_state["messages"][-1]
            nudge_text = last_message.content if hasattr(last_message, "content") else str(last_message)
            
            # 2. Dispatch via Email (Free Gmail SMTP / Resend)
            email_result = send_email_dispatch(
                to_email=lead.email,
                subject=f"Checking in on your discovery session - {lead.name}",
                text_content=nudge_text,
            )
            
            # 3. Dispatch via WhatsApp if phone number is present
            whatsapp_result = None
            if lead.phone:
                whatsapp_result = send_whatsapp_message(
                    to_phone=lead.phone,
                    message=nudge_text,
                )
            
            # 4. Update lead tracking in CRM database
            lead.last_activity = datetime.now(timezone.utc)
            lead.follow_up_count = (lead.follow_up_count or 0) + 1
            session.commit()
            
            results.append({
                "lead_id": lead.id,
                "email": lead.email,
                "email_dispatched": email_result.get("success", False),
                "whatsapp_dispatched": whatsapp_result.get("success", False) if whatsapp_result else None,
            })
            
        return {"status": "success", "processed_leads_count": len(results), "details": results}

    except Exception as exc:
        session.rollback()
        raise self.retry(exc=exc)
    finally:
        session.close()

@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def t_minus_2_minute_nudge(self, meeting_id: str):
    """Triggered by Cal.com webhook to check Google Meet presence.

    1. Checks if the attendee has joined the room.
    2. If absent at T-minus 2 minutes:
       - Triggers outbound voice telephony prompt to the lead's phone.
       - Dispatches an urgent reminder email with direct 1-click meeting link via Resend.
    """
    session = get_db_session()
    
    try:
        # 1. Fetch meeting and attendee details from Cal.com API or local CRM
        headers = {
            "Authorization": f"Bearer {CAL_API_KEY}",
            "Content-Type": "application/json",
            "cal-api-version": "2024-08-13",
        }
        
        cal_response = requests.get(
            f"https://api.cal.com/v2/bookings/{meeting_id}",
            headers=headers,
            timeout=10,
        )
        
        meeting_data = {}
        if cal_response.status_code == 200:
            meeting_data = cal_response.json().get("data", {})
        
        # Look up corresponding record in DB
        db_meeting = session.query(Meeting).filter(Meeting.meeting_id == str(meeting_id)).first()
        db_lead = session.query(Lead).filter(Lead.id == db_meeting.lead_id).first() if db_meeting else None
        
        attendee_email = (
            (meeting_data.get("attendees", [{}])[0].get("email") if meeting_data.get("attendees") else None)
            or (db_lead.email if db_lead else None)
        )
        attendee_name = (
            (meeting_data.get("attendees", [{}])[0].get("name") if meeting_data.get("attendees") else None)
            or (db_lead.name if db_lead else "there")
        )
        attendee_phone = (
            (meeting_data.get("attendees", [{}])[0].get("phone") if meeting_data.get("attendees") else None)
            or (db_lead.phone if db_lead else None)
        )
        meeting_url = meeting_data.get("meetingUrl") or (db_meeting.meeting_url if db_meeting else "https://meet.google.com")
        meeting_title = meeting_data.get("title") or (db_meeting.title if db_meeting else "Discovery Call")
        
        # Check user presence flag (e.g. from Google Meet webhook/presence telemetry)
        is_user_present = db_meeting.user_present if db_meeting else False
        
        telephony_result = None
        email_result = None
        
        if not is_user_present:
            # 2. Trigger Outbound Voice Telephony
            if attendee_phone:
                telephony_result = trigger_outbound_voice_telephony(
                    phone_number=attendee_phone,
                    meeting_title=meeting_title,
                    meeting_url=meeting_url,
                )
            
            # 3. Trigger Urgent T-2 Email with direct Join Button via Resend
            if attendee_email:
                urgent_email_html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 25px; border: 1px solid #e0e0e0; border-radius: 8px;">
                    <h2 style="color: #1a73e8; margin-top: 0;">Your Meeting is Starting in 2 Minutes!</h2>
                    <p>Hi {attendee_name},</p>
                    <p>We're ready for our <strong>{meeting_title}</strong> session. Click the button below to join the room directly:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{meeting_url}" style="background-color: #1a73e8; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                            Join Meeting Room Now &rarr;
                        </a>
                    </div>
                    <p style="color: #666; font-size: 14px;">Meeting Link: <a href="{meeting_url}">{meeting_url}</a></p>
                </div>
                """
                email_result = send_email_dispatch(
                    to_email=attendee_email,
                    subject=f"🚨 Starting in 2 mins: {meeting_title}",
                    text_content=f"Hi {attendee_name}, your meeting '{meeting_title}' starts in 2 minutes! Join here: {meeting_url}",
                    html_content=urgent_email_html,
                )
            
            if db_meeting:
                db_meeting.telephony_triggered = True
                session.commit()
                
            return {
                "status": "nudge_triggered",
                "meeting_id": meeting_id,
                "telephony": telephony_result,
                "email": email_result,
            }
        else:
            return {"status": "user_already_present", "meeting_id": meeting_id}

    except Exception as exc:
        session.rollback()
        raise self.retry(exc=exc)
    finally:
        session.close()
