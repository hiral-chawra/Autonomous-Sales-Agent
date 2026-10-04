import os
import json
import requests
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

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
    try:
        dt_start = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
        dt_end = datetime.fromisoformat(end_time_iso.replace('Z', '+00:00'))
        fmt_start = dt_start.strftime('%Y%m%dT%H%M%SZ')
        fmt_end = dt_end.strftime('%Y%m%dT%H%M%SZ')
    except Exception:
        fmt_start = "20261005T100000Z"
        fmt_end = "20261005T103000Z"

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

def send_email_via_smtp(
    to_email: Union[str, List[str]],
    subject: str,
    text_content: str,
    html_content: Optional[str] = None,
    ics_content: Optional[str] = None,
    ics_filename: str = "invite.ics"
) -> Dict[str, Any]:
    """Sends emails with optional .ics calendar invites using Gmail SMTP."""
    sender_email = os.getenv("SMTP_EMAIL", SMTP_EMAIL)
    sender_password = os.getenv("SMTP_PASSWORD", SMTP_PASSWORD)

    if not sender_email or not sender_password:
        return {"success": False, "error": "SMTP_EMAIL or SMTP_PASSWORD not configured."}

    try:
        root_msg = MIMEMultipart("mixed") if ics_content else MIMEMultipart("alternative")
        root_msg["From"] = f"Aanandi Automations <{sender_email}>"

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

def send_email_via_resend(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: Optional[str] = None
) -> Dict[str, Any]:
    """Sends transactional and follow-up emails using the Resend REST API."""
    if not RESEND_API_KEY:
        return {"success": False, "error": "RESEND_API_KEY is not configured."}

    if not html_content:
        formatted_body = "".join(f"<p>{paragraph}</p>" for paragraph in text_content.split("\n\n") if paragraph)
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; line-height: 1.6; color: #333;">
            {formatted_body}
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
    """Unified email dispatcher: uses free Gmail SMTP first, with automatic Resend fallback."""
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

    return send_email_via_resend(to_email, subject, text_content, html_content)
