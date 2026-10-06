import os
import random
import operator
import requests
from typing import TypedDict, Annotated, Sequence, Literal
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

cal_api_key = os.getenv("CAL_API_KEY") or os.getenv("CAL_COM_API_KEY", "")

# Define FSM Lead Stages & Pending Steps
LeadStage = Literal["NEW_LEAD", "QUALIFYING", "BOOKING_OFFERED", "CALL_BOOKED", "NURTURE", "DISQUALIFIED"]
PendingStep = Literal["COLLECT_NAME", "COLLECT_EMAIL", "COLLECT_PHONE", "VERIFY_OTP", "VERIFIED"]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    lead_stage: LeadStage
    bant_score: int  # 1-10
    user_name: str
    user_email: str
    user_phone: str
    is_verified: bool
    otp_code: str
    pending_step: PendingStep
    tool_payload: dict | None
    needs_human: bool

# Tools Definition
@tool
def query_knowledge_base(query: str) -> str:
    """Searches product documentation, case studies, and enterprise FAQs."""
    return f"Knowledge base results for '{query}': Aanandi TechnoSoft builds custom enterprise AI agents, workflow automation, and voice bots with 99.99% uptime SLA, CRM integrations, and dedicated engineering support."

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
def send_email(to_email: str, subject: str, body: str) -> str:
    """Sends an email to the lead via Resend API."""
    try:
        from dispatch import send_email_dispatch
        result = send_email_dispatch(to_email=to_email, subject=subject, text_content=body)
        if result.get("success"):
            return f"Email successfully sent to {to_email}."
        else:
            return f"Failed to send email: {result.get('error')}"
    except Exception as e:
        return f"Error sending email: {str(e)}"

tools = [query_knowledge_base, generate_booking_link, send_email]

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
    last_msg = messages[-1].content.strip() if messages else ""
    
    is_verified = state.get("is_verified", False)
    pending_step = state.get("pending_step", "COLLECT_NAME")
    user_name = state.get("user_name", "")
    user_email = state.get("user_email", "")
    user_phone = state.get("user_phone", "")
    otp_code = state.get("otp_code", "")

    # ── Phase 1: Conversational Capture & Verification ──────────────────────────
    if not is_verified and pending_step != "VERIFIED":
        # Smart Check: If user typed an email address at ANY point while name/email is pending
        if "@" in last_msg and "." in last_msg and pending_step in ["COLLECT_NAME", "COLLECT_EMAIL"]:
            user_email = last_msg.strip().lower()
            display_name = user_name if user_name else "there"
            return {
                "messages": [AIMessage(content=f"Thank you, **{display_name}**! Lastly, what is your phone number?")],
                "user_email": user_email,
                "pending_step": "COLLECT_PHONE",
                "tool_payload": None
            }

        # Step 1: Collect Name
        if pending_step == "COLLECT_NAME":
            # Check for exact standalone greeting words
            if last_msg.lower().strip() in ["hi", "hello", "hey", "start", "hi!", "hello!"]:
                return {
                    "messages": [AIMessage(content="👋 Welcome to Aanandi TechnoSoft! May I have your full name to get started?")],
                    "pending_step": "COLLECT_NAME",
                    "tool_payload": None
                }
            # User provided their name (e.g. "Hiral Chawra")
            user_name = last_msg.strip().title()
            return {
                "messages": [AIMessage(content=f"Nice to meet you, **{user_name}**! What is your email address so we can secure your session?")],
                "user_name": user_name,
                "pending_step": "COLLECT_EMAIL",
                "tool_payload": None
            }

        # Step 2: Collect Email
        if pending_step == "COLLECT_EMAIL":
            if "@" in last_msg and "." in last_msg:
                user_email = last_msg.strip().lower()
                display_name = user_name if user_name else "there"
                return {
                    "messages": [AIMessage(content=f"Thank you, **{display_name}**! Lastly, what is your phone number?")],
                    "user_email": user_email,
                    "pending_step": "COLLECT_PHONE",
                    "tool_payload": None
                }
            else:
                return {
                    "messages": [AIMessage(content="Please provide a valid email address (e.g. name@company.com).")],
                    "pending_step": "COLLECT_EMAIL",
                    "tool_payload": None
                }

        # Step 3: Collect Phone
        if pending_step == "COLLECT_PHONE" or (not user_phone and pending_step not in ["VERIFY_OTP"]):
            user_phone = last_msg
            target_email = user_email.strip() if (user_email and "@" in user_email) else os.getenv("SMTP_EMAIL", "pyashkumar0312@gmail.com")

            # Generate and dispatch 6-digit OTP
            new_otp = str(random.randint(100000, 999999))
            from dispatch import send_email_dispatch
            dispatch_res = send_email_dispatch(
                to_email=target_email,
                subject="Your Aanandi Security Verification Code",
                text_content=f"Hello {user_name or 'Valued Customer'},\n\nYour 6-digit security code is: {new_otp}\nValid for 10 minutes."
            )
            is_mock = dispatch_res.get("mock", False)
            if is_mock:
                msg_text = (
                    f"🔐 We've dispatched a 6-digit verification code to **{target_email}**.\n\n"
                    f"*(Demo Mode: No SMTP/Resend API key configured in `.env`. Your security code is `{new_otp}`)*\n\n"
                    "Please type the 6-digit security code below to verify your session."
                )
            else:
                msg_text = (
                    f"🔐 We've sent a 6-digit verification code to **{target_email}**!\n\n"
                    "Please check your email inbox (and spam folder) and type the 6-digit security code below to verify your session."
                )

            return {
                "messages": [AIMessage(content=msg_text)],
                "user_phone": user_phone,
                "user_email": target_email,
                "otp_code": new_otp,
                "pending_step": "VERIFY_OTP",
                "tool_payload": None
            }

        # Step 4: Verify OTP
        if pending_step == "VERIFY_OTP":
            cleaned_code = "".join(filter(str.isdigit, last_msg))
            if cleaned_code == otp_code and len(cleaned_code) == 6:
                return {
                    "messages": [AIMessage(content="✅ **Email Verified Successfully!**\n\nHow can I help you today with custom AI agents, workflow automation, or enterprise solutions?")],
                    "is_verified": True,
                    "pending_step": "VERIFIED",
                    "tool_payload": {
                        "type": "mcq",
                        "data": {
                            "title": "Quick Exploration Options",
                            "options": [
                                "Ask about Custom CRM Integrations",
                                "Inquire about AI Voice Bots",
                                "Talk to AI or Book Call"
                            ]
                        }
                    }
                }
            else:
                return {
                    "messages": [AIMessage(content="❌ Invalid verification code. Please check your email and type the correct 6-digit code.")],
                    "pending_step": "VERIFY_OTP",
                    "tool_payload": None
                }


    # ── Phase 2 & 3: RAG Q&A, MCQs, & Call Routing ──────────────────────────────
    if any(k in last_msg.lower() for k in ["book", "call", "talk", "demo", "pricing", "tier", "schedule"]):
        return {
            "messages": [AIMessage(content="How would you like to connect with our team?")],
            "lead_stage": "BOOKING_OFFERED",
            "tool_payload": {
                "type": "call_routing",
                "data": {}
            }
        }

    # RAG / General Technical Q&A
    kb_res = query_knowledge_base.invoke({"query": last_msg})
    response_content = (
        f"Thank you for asking! {kb_res}\n\n"
        "What specific feature or automation requirement would you like to explore next?"
    )
    
    return {
        "messages": [AIMessage(content=response_content)],
        "lead_stage": "QUALIFYING",
        "tool_payload": {
            "type": "mcq",
            "data": {
                "title": "Suggested Follow-ups",
                "options": [
                    "Tell me about Custom CRM Integrations",
                    "How do AI Voice Bots work?",
                    "Talk to AI or Book Call"
                ]
            }
        }
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

checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer)

