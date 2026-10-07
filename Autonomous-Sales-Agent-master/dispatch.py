import os
import json
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

SMTP_EMAIL = os.getenv("SMTP_EMAIL", "noreply@yourdomain.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

def generate_ics_attachment(
    start_time_iso: str,
    end_time_iso: str,
    lead_name: str,
    lead_email: str,
    meeting_url: str,
    meeting_type: str = "Discovery Call",
    amount_paid: str = "Free",
    organizer_email: Optional[str] = None
) -> str:
    """Generates the calendar payload (iCalendar / .ics format) including the meeting type and payment."""
    dt_start = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
    dt_end = datetime.fromisoformat(end_time_iso.replace('Z', '+00:00'))
    
    fmt_start = dt_start.strftime('%Y%m%dT%H%M%SZ')
    fmt_end = dt_end.strftime('%Y%m%dT%H%M%SZ')
    
    org_email = organizer_email or os.getenv("SMTP_EMAIL", "noreply@yourdomain.com")
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Aanandi Automations//CRM System//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
DTSTART:{fmt_start}
DTEND:{fmt_end}
SUMMARY:[{meeting_type}] Call: {lead_name}
DESCRIPTION:New {meeting_type} from {lead_name} ({lead_email}).\\n\\nAmount Paid: {amount_paid}\\n\\nJoin Link: {meeting_url}
ORGANIZER;CN=Enterprise Assistant:mailto:{org_email}
ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN={lead_name}:mailto:{lead_email}
LOCATION:{meeting_url}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
    
    return ics_content

from typing import Optional, Dict, Any, List, Union

def send_email_via_smtp(
    to_email: Union[str, List[str]],
    subject: str,
    text_content: str,
    html_content: Optional[str] = None,
    ics_content: Optional[str] = None,
    ics_filename: str = "invite.ics"
) -> Dict[str, Any]:
    """Sends emails with optional .ics calendar invites to ANY recipient(s) using Gmail SMTP."""
    sender_email = os.getenv("SMTP_EMAIL", SMTP_EMAIL)
    sender_password = os.getenv("SMTP_PASSWORD", SMTP_PASSWORD)

    if not sender_email or not sender_password:
        return {"success": False, "error": "SMTP_EMAIL or SMTP_PASSWORD not configured."}

    try:
        # If ICS invite is present, root is mixed, with an alternative text/html body and calendar attachment
        root_msg = MIMEMultipart("mixed") if ics_content else MIMEMultipart("alternative")
        root_msg["From"] = f"Aanandi Automations <{sender_email}>"
        
        # Handle single recipient or list of recipients
        if isinstance(to_email, list):
            root_msg["To"] = ", ".join(to_email)
            to_addrs = to_email
        else:
            root_msg["To"] = to_email
            to_addrs = [to_email]

        root_msg["Subject"] = subject

        if not html_content:
            formatted_body = "".join(f"<p>{p}</p>" for p in text_content.split("\n\n") if p)
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; line-height: 1.6; color: #333;">
                {formatted_body}
                <hr style="margin-top: 30px; border: 0; border-top: 1px solid #eaeaea;" />
                <p style="font-size: 12px; color: #888;">Enterprise AI Assistant &bull; Automated Follow-up</p>
            </div>
            """

        if ics_content:
            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(text_content, "plain"))
            body_part.attach(MIMEText(html_content, "html"))
            root_msg.attach(body_part)

            # Calendar attachment + invitation handler for Google Calendar / Outlook
            cal_part = MIMEBase("text", "calendar", method="REQUEST", name=ics_filename)
            cal_part.set_payload(ics_content.encode("utf-8"))
            cal_part.add_header("Content-Disposition", "attachment", filename=ics_filename)
            cal_part.add_header("Content-Class", "urn:content-classes:calendarmessage")
            root_msg.attach(cal_part)
        else:
            root_msg.attach(MIMEText(text_content, "plain"))
            root_msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(root_msg, to_addrs=to_addrs)

        return {"success": True, "to": to_email, "provider": "gmail_smtp", "has_calendar_invite": bool(ics_content)}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "gmail_smtp"}

def notify_team_of_booking(
    internal_emails: list,
    lead_name: str,
    lead_email: str,
    start_time: str,
    end_time: str,
    meeting_url: str,
    meeting_type: str,
    amount_paid: str = "Free"
) -> Dict[str, Any]:
    """Sends an internal team notification with calendar .ics attachment via Google SMTP (100% Free)."""
    # 1. Generate ICS with booking context
    ics_data = generate_ics_attachment(
        start_time_iso=start_time,
        end_time_iso=end_time,
        lead_name=lead_name,
        lead_email=lead_email,
        meeting_url=meeting_url,
        meeting_type=meeting_type,
        amount_paid=amount_paid
    )

    subject = f"🔔 NEW BOOKING: [{meeting_type}] with {lead_name}"
    
    text_content = f"""New {meeting_type} Booked

Lead Name: {lead_name}
Lead Email: {lead_email}
Amount Collected: {amount_paid}
Meeting Link: {meeting_url}

The discovery_call.ics calendar invite is attached to this email. Please accept it to sync to your schedule."""

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <div style="padding-bottom: 15px; border-bottom: 1px solid #edf2f7; margin-bottom: 20px;">
            <h3 style="color: #1a365d; margin: 0 0 5px 0;">🎉 New {meeting_type} Booked</h3>
            <p style="color: #718096; margin: 0; font-size: 14px;">Internal Team Notification &bull; Aanandi Automations</p>
        </div>
        <div style="background-color: #f7fafc; border-left: 4px solid #3182ce; padding: 15px 18px; border-radius: 6px; margin-bottom: 20px;">
            <p style="margin: 6px 0;"><strong>👤 Lead Name:</strong> {lead_name}</p>
            <p style="margin: 6px 0;"><strong>📧 Lead Email:</strong> <a href="mailto:{lead_email}">{lead_email}</a></p>
            <p style="margin: 6px 0;"><strong>💰 Amount Collected:</strong> <span style="color: #2b6cb0; font-weight: bold;">{amount_paid}</span></p>
            <p style="margin: 6px 0;"><strong>🌐 Meeting Link:</strong> <a href="{meeting_url}" style="color: #3182ce; font-weight: bold;">{meeting_url}</a></p>
        </div>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{meeting_url}" style="background-color: #3182ce; color: #ffffff; padding: 12px 26px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                Join Meeting Room
            </a>
        </div>
        <p style="font-size: 13px; color: #718096; line-height: 1.5;">
            📅 The <code>discovery_call.ics</code> calendar invite is attached. Click or accept it to add this event automatically to your Google Calendar / Outlook.
        </p>
    </div>
    """

    return send_email_via_smtp(
        to_email=internal_emails,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        ics_content=ics_data,
        ics_filename="discovery_call.ics"
    )

def send_email_via_resend(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: Optional[str] = None
) -> Dict[str, Any]:
    """Sends transactional and follow-up emails using the Resend REST API."""
    if not RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")

    if not html_content:
        # Convert plain text newlines to clean HTML paragraphs
        formatted_body = "".join(f"<p>{paragraph}</p>" for paragraph in text_content.split("\n\n") if paragraph)
        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; line-height: 1.6; color: #333;">
            {formatted_body}
            <hr style="margin-top: 30px; border: 0; border-top: 1px solid #eaeaea;" />
            <p style="font-size: 12px; color: #888;">Enterprise AI Assistant &bull; Automated Follow-up</p>
        </div>
        """

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "text": text_content,
        "html": html_content,
    }

    try:
        response = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=15)
        response_data = response.json()
        if response.status_code in (200, 201):
            return {"success": True, "data": response_data, "id": response_data.get("id"), "provider": "resend"}
        else:
            return {"success": False, "error": response_data, "status_code": response.status_code, "provider": "resend"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "resend"}

def send_email_dispatch(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: Optional[str] = None,
    ics_content: Optional[str] = None,
    ics_filename: str = "invite.ics"
) -> Dict[str, Any]:
    """Unified email dispatcher: uses free Gmail SMTP first with calendar invite support, with automatic Resend fallback."""
    if os.getenv("SMTP_EMAIL") and os.getenv("SMTP_PASSWORD"):
        smtp_res = send_email_via_smtp(
            to_email=to_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            ics_content=ics_content,
            ics_filename=ics_filename
        )
        if smtp_res.get("success"):
            return smtp_res
    
    # Fallback to Resend
    return send_email_via_resend(to_email, subject, text_content, html_content)

def send_whatsapp_message(to_phone: str, message: str) -> Dict[str, Any]:
    """Dispatches follow-up and reminder notifications via WhatsApp."""
    # Supports Twilio or Meta WhatsApp Cloud API
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "+14155238886")

    if twilio_sid and twilio_token and to_phone:
        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            msg = client.messages.create(
                from_=f"whatsapp:{twilio_whatsapp_number}",
                body=message,
                to=f"whatsapp:{to_phone}"
            )
            return {"success": True, "sid": msg.sid}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # Fallback / Log notification if WhatsApp telephony credentials not configured
    print(f"[WhatsApp Dispatch Mock] To: {to_phone} | Message: {message}")
    return {"success": True, "mock": True, "to": to_phone}

def trigger_outbound_voice_telephony(phone_number: str, meeting_title: str, meeting_url: str) -> Dict[str, Any]:
    """Triggers outbound AI voice call or urgent telephony prompt for missing meeting attendees."""
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_caller_id = os.getenv("TWILIO_CALLER_ID")

    twiml_instructions = f"""<Response>
        <Say voice="Polly.Amy">Hello! Your scheduled meeting {meeting_title} is starting in less than 2 minutes. Please check your email for the Google Meet link or join directly now. We look forward to speaking with you!</Say>
    </Response>"""

    if twilio_sid and twilio_token and from_caller_id and phone_number:
        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            call = client.calls.create(
                twiml=twiml_instructions,
                to=phone_number,
                from_=from_caller_id
            )
            return {"success": True, "call_sid": call.sid}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Fallback / Log telephony trigger
    print(f"[Voice Telephony Triggered] Calling {phone_number} for meeting '{meeting_title}' ({meeting_url})")
    return {"success": True, "mock": True, "phone": phone_number}
