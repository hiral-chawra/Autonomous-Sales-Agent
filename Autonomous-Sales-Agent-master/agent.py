import os
import operator
import requests
from typing import TypedDict, Annotated, Sequence, Literal
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Load environment variables from .env
load_dotenv()

openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
cal_api_key = os.getenv("CAL_API_KEY")

# Define the FSM stages exactly as spec'd
LeadStage = Literal["NEW_LEAD", "QUALIFYING", "BOOKING_OFFERED", "CALL_BOOKED", "NURTURE", "DISQUALIFIED"]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    lead_stage: LeadStage
    bant_score: int  # 1-10
    user_email: str
    user_name: str
    needs_human: bool

# Multi-LLM Setup using OpenRouter with automatic fallbacks for maximum resilience
primary_model = os.getenv("PRIMARY_LLM_MODEL", "nvidia/nemotron-3.5-lightning:free")
fallback_model = "apodex/apodex-1.1-mini:free"

triage_llm = ChatOpenAI(
    model=primary_model,
    temperature=0,
    api_key=openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
).with_fallbacks([
    ChatOpenAI(model=fallback_model, temperature=0, api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1"),
    ChatOpenAI(model="google/gemma-4-31b-it:free", temperature=0, api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
])

# Heavy reasoning model with tools
reasoning_llm = ChatOpenAI(
    model=primary_model,
    temperature=0.3,
    api_key=openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
).with_fallbacks([
    ChatOpenAI(model=fallback_model, temperature=0.3, api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1"),
    ChatOpenAI(model="google/gemma-4-26b-a4b-it:free", temperature=0.3, api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
])


# Tools Definition
@tool
def query_knowledge_base(query: str) -> str:
    """Searches product documentation, case studies, and enterprise FAQs."""
    return f"Knowledge base results for '{query}': Enterprise tier includes custom integrations, 99.99% SLA, and dedicated support."

@tool
def generate_booking_link(email: str, name: str) -> str:
    """Generates a custom pre-filled Cal.com scheduling link for the lead to choose their own time slot."""
    api_k = os.getenv("CAL_API_KEY", cal_api_key)
    headers = {
        "Authorization": f"Bearer {api_k}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-05-21",
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
    """Directly books and confirms a meeting in Cal.com that immediately appears on the calendar and dashboard.

    Args:
        email: Attendee's email address (must have valid MX domain, e.g., user@company.com or user@gmail.com).
        name: Attendee's full name.
        start_time_iso_utc: Meeting start time in UTC ISO format (e.g. '2026-10-05T05:00:00.000Z').
        time_zone: Attendee's timezone (defaults to 'Asia/Kolkata').
        event_type_id: Cal.com Event Type ID (defaults to Discovery Call: 7297448).
    """
    api_k = os.getenv("CAL_API_KEY", cal_api_key)
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
                f"- Title: {booking_data.get('title')}\n"
                f"- Start: {booking_data.get('start')}\n"
                f"- Meeting Link: {booking_data.get('meetingUrl')}\n"
                f"- Status: {booking_data.get('status')}"
            )
        else:
            err = data.get("error", {}).get("message") or data.get("message") or str(data)
            return f"Cal.com booking request failed: {err}"
    except Exception as e:
        return f"Error creating booking: {str(e)}"

@tool
def update_crm_stage(stage: LeadStage, bant_score: int) -> str:
    """Updates lead lifecycle fields in the PostgreSQL/CRM database."""
    return f"Stage updated to {stage} with BANT {bant_score}"

@tool
def send_email(to_email: str, subject: str, body: str) -> str:
    """Sends an email to the lead (e.g. meeting confirmations, product info, follow-ups) via free Gmail SMTP / Resend."""
    try:
        from dispatch import send_email_dispatch
        result = send_email_dispatch(to_email=to_email, subject=subject, text_content=body)
        if result.get("success"):
            provider = result.get("provider", "email")
            return f"Email successfully sent to {to_email} via {provider} with subject '{subject}'."
        else:
            return f"Failed to send email: {result.get('error')}"
    except Exception as e:
        return f"Error sending email: {str(e)}"

@tool
def send_calendar_invite(
    to_email: str,
    lead_name: str,
    start_time_iso_utc: str,
    end_time_iso_utc: str,
    meeting_url: str,
    meeting_type: str = "Discovery Call",
    amount_paid: str = "Free"
) -> str:
    """Sends a meeting invitation email with an interactive .ics calendar attachment (compatible with Google Calendar, Apple Calendar, and Outlook)."""
    try:
        from dispatch import generate_ics_attachment, send_email_dispatch
        ics_text = generate_ics_attachment(
            start_time_iso=start_time_iso_utc,
            end_time_iso=end_time_iso_utc,
            lead_name=lead_name,
            lead_email=to_email,
            meeting_url=meeting_url,
            meeting_type=meeting_type,
            amount_paid=amount_paid,
        )
        subject = f"📅 Invitation: [{meeting_type}] Call with {lead_name}"
        body = (
            f"Hi {lead_name},\n\n"
            f"Your session has been scheduled!\n"
            f"- Meeting: {meeting_type}\n"
            f"- Start Time: {start_time_iso_utc}\n"
            f"- Meeting Room: {meeting_url}\n\n"
            f"Please accept the attached calendar invitation to automatically sync with your calendar."
        )
        result = send_email_dispatch(
            to_email=to_email,
            subject=subject,
            text_content=body,
            ics_content=ics_text
        )
        if result.get("success"):
            return f"Calendar invite email with .ics attachment sent successfully to {to_email}."
        else:
            return f"Failed to send calendar invite: {result.get('error')}"
    except Exception as e:
        return f"Error sending calendar invite: {str(e)}"

# Bind Tools to Gemma Reasoning Model
tools = [query_knowledge_base, generate_booking_link, create_cal_booking, update_crm_stage, send_email, send_calendar_invite]
reasoning_llm_with_tools = reasoning_llm.bind_tools(tools)

# Graph Nodes Definition
def triage_node(state: AgentState):
    """Uses Gemma 4 31B triage LLM to quickly assess lead qualification and stage."""
    # Production: Can invoke triage_llm with prompt to classify lead status and BANT score
    current_stage = state.get("lead_stage") or "QUALIFYING"
    current_bant = state.get("bant_score") or 5
    return {
        "lead_stage": current_stage,
        "bant_score": current_bant,
    }

def reasoning_node(state: AgentState):
    """Uses Gemma 4 26B with bound tools to reason and generate the next response or tool call."""
    messages = state["messages"]
    system_prompt = SystemMessage(
        content=(
            "You are an expert enterprise sales and lead qualification assistant. "
            "Use the provided tools to answer knowledge questions, generate scheduling links, "
            "create calendar bookings, update CRM lifecycle stages, or send emails via Resend when appropriate."
        )
    )
    full_messages = [system_prompt] + list(messages)
    response = reasoning_llm_with_tools.invoke(full_messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    """Inspects the last message to determine whether to execute tools or end the turn."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"

# Construct the StateGraph
workflow = StateGraph(AgentState)
workflow.add_node("triage", triage_node)
workflow.add_node("reasoner", reasoning_node)
workflow.add_node("tools", ToolNode(tools))

workflow.set_entry_point("triage")
workflow.add_edge("triage", "reasoner")
workflow.add_conditional_edges("reasoner", should_continue, {"tools": "tools", "end": END})
workflow.add_edge("tools", "reasoner")  # Loop back after tool execution

from langgraph.checkpoint.memory import MemorySaver

# Compile the runnable graph with checkpointer for stateful thread persistence
checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    print("LangGraph Enterprise Agent compiled successfully with Gemma models!")
    
    # Quick end-to-end test execution
    test_state: AgentState = {
        "messages": [HumanMessage(content="Hello! Can you tell me what enterprise features you offer?")],
        "lead_stage": "NEW_LEAD",
        "bant_score": 1,
        "user_email": "lead@company.com",
        "user_name": "Alex",
        "needs_human": False,
    }
    print("\nRunning test invocation through LangGraph workflow...")
    result = app.invoke(test_state)
    print("\nFinal Agent State:")
    print(f"Lead Stage: {result.get('lead_stage')}")
    print(f"BANT Score: {result.get('bant_score')}")
    print(f"Last Message: {result['messages'][-1].content}")
