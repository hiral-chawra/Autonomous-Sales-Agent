import os
import operator
import requests
from typing import TypedDict, Annotated, Sequence, Literal
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

load_dotenv()

openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
cal_api_key = os.getenv("CAL_API_KEY") or os.getenv("CAL_COM_API_KEY", "")

# Define FSM Lead Stages
LeadStage = Literal["NEW_LEAD", "QUALIFYING", "BOOKING_OFFERED", "CALL_BOOKED", "NURTURE", "DISQUALIFIED"]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    lead_stage: LeadStage
    bant_score: int  # 1-10
    user_email: str
    user_name: str
    needs_human: bool

# Tools Definition
@tool
def query_knowledge_base(query: str) -> str:
    """Searches product documentation, case studies, and enterprise FAQs."""
    return f"Knowledge base results for '{query}': Enterprise tier includes custom integrations, 99.99% SLA, and dedicated support."

@tool
def generate_booking_link(email: str, name: str) -> str:
    """Generates a custom pre-filled Cal.com scheduling link for the lead."""
    api_k = os.getenv("CAL_API_KEY") or os.getenv("CAL_COM_API_KEY", cal_api_key)
    headers = {
        "Authorization": f"Bearer {api_k}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13",
    }
    
    try:
        response = requests.get("https://api.cal.com/v2/me", headers=headers, timeout=10)
        if response.status_code == 200:
            user_data = response.json().get("data", {})
            username = user_data.get("username", "booking")
            return f"https://cal.com/{username}/discovery-call?name={requests.utils.quote(name)}&email={requests.utils.quote(email)}"
        else:
            return f"https://cal.com/booking?name={requests.utils.quote(name)}&email={requests.utils.quote(email)}"
    except Exception as e:
        return f"Error generating booking link: {str(e)}"

@tool
def create_cal_booking(
    email: str,
    name: str,
    start_time_iso_utc: str,
    time_zone: str = "Asia/Kolkata",
    event_type_id: int = 7297448,
) -> str:
    """Directly books and confirms a meeting in Cal.com."""
    api_k = os.getenv("CAL_API_KEY") or os.getenv("CAL_COM_API_KEY", cal_api_key)
    headers = {
        "Authorization": f"Bearer {api_k}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13",
    }
    
    payload = {
        "eventTypeId": event_type_id,
        "start": start_time_iso_utc,
        "attendee": {
            "name": name,
            "email": email,
            "timeZone": time_zone,
            "language": "en",
        },
    }
    
    try:
        response = requests.post("https://api.cal.com/v2/bookings", json=payload, headers=headers, timeout=10)
        data = response.json()
        if response.status_code in [200, 201] and data.get("status") == "success":
            booking_data = data.get("data", {})
            return (
                f"Booking successfully confirmed on Cal.com!\n"
                f"- Booking ID: {booking_data.get('id')}\n"
                f"- Start: {booking_data.get('start')}\n"
                f"- Meeting Link: {booking_data.get('meetingUrl')}"
            )
        else:
            err = data.get("error", {}).get("message") or data.get("message") or str(data)
            return f"Cal.com booking request failed: {err}"
    except Exception as e:
        return f"Error creating booking: {str(e)}"

@tool
def send_email(to_email: str, subject: str, body: str) -> str:
    """Sends an email to the lead via Gmail SMTP / Resend."""
    try:
        from dispatch import send_email_dispatch
        result = send_email_dispatch(to_email=to_email, subject=subject, text_content=body)
        if result.get("success"):
            return f"Email successfully sent to {to_email}."
        else:
            return f"Failed to send email: {result.get('error')}"
    except Exception as e:
        return f"Error sending email: {str(e)}"

tools = [query_knowledge_base, generate_booking_link, create_cal_booking, send_email]

# Graph Nodes Definition
def triage_node(state: AgentState):
    """Assesses lead qualification and lifecycle stage."""
    current_stage = state.get("lead_stage") or "QUALIFYING"
    current_bant = state.get("bant_score") or 5
    return {
        "lead_stage": current_stage,
        "bant_score": current_bant,
    }

def reasoning_node(state: AgentState):
    """Generates next response or tool call based on current state."""
    messages = state["messages"]
    last_msg = messages[-1].content if messages else ""
    
    # Responsive sales engineer logic
    if any(k in last_msg.lower() for k in ["demo", "book", "schedule", "call", "meeting", "time"]):
        response_content = (
            "I'd be happy to schedule a demo for you! "
            "Please pick a convenient time slot using the calendar widget below or let me know your preferred date."
        )
        return {
            "messages": [HumanMessage(content=response_content)],
            "lead_stage": "BOOKING_OFFERED"
        }
    
    response_content = (
        "Thank you for reaching out! I'm Aanandi, AI Sales Engineer at Aanandi TechnoSoft. "
        "We build enterprise AI agents, custom workflow automation, and voice bots. "
        "How can we help automate your business processes?"
    )
    return {
        "messages": [HumanMessage(content=response_content)],
        "lead_stage": "QUALIFYING"
    }

def should_continue(state: AgentState):
    return "end"

# Construct the StateGraph
workflow = StateGraph(AgentState)
workflow.add_node("triage", triage_node)
workflow.add_node("reasoner", reasoning_node)

workflow.set_entry_point("triage")
workflow.add_edge("triage", "reasoner")
workflow.add_edge("reasoner", END)

from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer)
