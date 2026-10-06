import os
import requests
from dotenv import load_dotenv

load_dotenv()

def send_email_dispatch(to_email: str, subject: str, text_content: str) -> dict:
    """Sends an email using the Resend API."""
    api_key = os.getenv("RESEND_API_KEY")
    
    if not api_key:
        print(f"Mock Email sent to {to_email}: {subject}")
        return {"success": True, "message": "Mock email sent (No API key)."}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": "Aanandi Bot <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "text": text_content
    }

    try:
        response = requests.post("https://api.resend.com/emails", json=payload, headers=headers)
        if response.status_code in [200, 201]:
            return {"success": True}
        return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}