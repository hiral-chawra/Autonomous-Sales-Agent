import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from dispatch import notify_team_of_booking

load_dotenv(override=True)

app = FastAPI(
    title="Aanandi Automations & Cal.com Webhook Gateway",
    version="1.0.0",
    description="Webhook listener for Cal.com bookings with automated internal notifications via Google SMTP."
)

# Define standard internal team contacts
RECEPTIONIST_EMAIL = os.getenv("RECEPTIONIST_EMAIL", "reception@yourdomain.com")
TECH_TEAM_EMAIL = os.getenv("TECH_TEAM_EMAIL", "asmiupadhyay491@gmail.com")
SENIOR_ENGINEER_EMAIL = os.getenv("SENIOR_ENGINEER_EMAIL", "chawrahiral3@gmail.com")

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Cal.com Webhook & Email Notification Service",
        "endpoints": ["/health", "/webhooks/cal"]
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/webhooks/cal")
async def handle_cal_webhook(request: Request):
    """Handles Cal.com webhook events (e.g. BOOKING_CREATED) and dispatches

    internal team emails with attached .ics calendar invitations using Google SMTP.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    trigger_event = payload.get("triggerEvent")

    if trigger_event == "BOOKING_CREATED":
        data = payload.get("payload", {})
        
        attendees = data.get("attendees", [])
        lead_name = attendees[0].get("name", "Unknown") if attendees else "Unknown"
        lead_email = attendees[0].get("email", "unknown@email.com") if attendees else "unknown@email.com"
        start_time = data.get("startTime")
        end_time = data.get("endTime")
        meeting_url = data.get("videoCallUrl") or data.get("location") or "Location TBD"
        
        # 1. Parse the user's selection from Cal.com custom fields
        responses = data.get("responses", {})
        meeting_purpose_raw = responses.get("meeting_purpose", {})
        
        if isinstance(meeting_purpose_raw, dict):
            purpose_selection = str(meeting_purpose_raw.get("value", "")).lower()
        else:
            purpose_selection = str(meeting_purpose_raw).lower()

        # Fallback to booking title if responses field is empty
        booking_title = str(data.get("title", "")).lower()

        # 2. Determine Meeting Type, Amount, and Technical Assignment
        if "project" in purpose_selection or "project" in booking_title:
            meeting_type = "Project Discussion"
            amount_paid = "$500"
            assigned_tech = SENIOR_ENGINEER_EMAIL  # High-value goes to senior engineer
        else:
            meeting_type = "General Enquiry"
            amount_paid = "$100"
            assigned_tech = TECH_TEAM_EMAIL  # Standard goes to general tech team
            
        # 3. Build the recipient list: Always include the assigned tech AND receptionist
        recipients = [assigned_tech, RECEPTIONIST_EMAIL]
        
        # 4. Dispatch the calendar invites via Google SMTP
        dispatch_result = notify_team_of_booking(
            internal_emails=recipients,
            lead_name=lead_name,
            lead_email=lead_email,
            start_time=start_time,
            end_time=end_time,
            meeting_url=meeting_url,
            meeting_type=meeting_type,
            amount_paid=amount_paid
        )

        return {
            "status": "success",
            "event": trigger_event,
            "meeting_type": meeting_type,
            "assigned_tech": assigned_tech,
            "recipients": recipients,
            "dispatch_result": dispatch_result
        }

    return {"status": "ignored", "event": trigger_event}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting FastAPI Cal.com Webhook Server on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
