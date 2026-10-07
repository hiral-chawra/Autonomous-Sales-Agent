import os
import re
import random
import operator
import requests
from typing import TypedDict, Annotated, Sequence, Literal
from dotenv import load_dotenv, find_dotenv

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

load_dotenv(find_dotenv(usecwd=True))

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

# Comprehensive Knowledge Base Data
PROJECTS_AND_CASE_STUDIES = """Aanandi TechnoSoft has successfully designed, developed, and deployed high-impact AI agents and software projects across key industries:

1. 🏥 **Healthcare & Telemedicine**:
   - **AI Patient Triage & Voice Appointment Bots**: Automated appointment scheduling, EHR integration, and pre-consultation symptom intake with ultra-low latency voice audio.

2. 🏦 **FinTech & Financial Services**:
   - **Automated Lead Qualification & KYC Verification**: Real-time user document intake, instant fraud risk scoring, and automated compliance routing.

3. 🛍️ **E-Commerce & Retail**:
   - **24/7 Autonomous Sales & Multimodal Shopping Agents**: Interactive web chat & voice widget supporting product recommendations, order tracking, and cart recovery.

4. 🏢 **Enterprise SaaS & CRM Automation**:
   - **Custom Workflow & CRM Integration Agents**: Automated bi-directional sync with Salesforce, HubSpot, and Zoho CRM, backed by PostgreSQL and Redis.

5. 🏡 **Real Estate & Legal Tech**:
   - **Intelligent Document Extraction & Onboarding Assistants**: Instant parsing of complex legal contracts and property inquiry handling.

6. 🎙️ **Real-Time Multimodal Web Widgets**:
   - High-performance web widget powered by Python FastAPI, LangGraph, Pipecat, Whisper STT, and ElevenLabs TTS."""

# Tools Definition
@tool
def query_knowledge_base(query: str) -> str:
    """Searches product documentation, case studies, fields, and enterprise FAQs for Aanandi TechnoSoft."""
    q_lower = query.lower()
    if any(k in q_lower for k in ["project", "projects", "fildes", "field", "fields", "built", "made", "work", "worked", "portfolio", "case", "study", "studies", "industry", "sector"]):
        return PROJECTS_AND_CASE_STUDIES
    return f"Aanandi TechnoSoft builds custom enterprise AI agents, workflow automation, real-time voice bots, and CRM integrations with 99.99% SLA and dedicated engineering support.\n\nKey Projects & Solutions:\n{PROJECTS_AND_CASE_STUDIES}"

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

# ── Intent Helpers ─────────────────────────────────────────────────────────────
def is_user_query(text: str) -> bool:
    """Determines whether text is a user inquiry/question rather than a name, email, or phone input."""
    if not text or not text.strip():
        return False
    
    text_clean = text.strip()
    text_lower = text_clean.lower()

    # Standalone greetings
    if text_lower in ["hi", "hello", "hey", "start", "hi!", "hello!", "hey!", "good morning", "good afternoon"]:
        return False

    # Email inputs are NEVER user queries
    if "@" in text_clean and "." in text_clean:
        return False

    if "?" in text_clean:
        return True

    query_keywords = [
        "what", "which", "how", "who", "where", "why", "can", "could", "would", "should", "will",
        "tell", "show", "need", "want", "project", "projects", "fildes", "field", "fields",
        "work", "worked", "built", "make", "made", "pricing", "cost", "price", "demo",
        "help", "about", "feature", "features", "service", "services", "case", "portfolio",
        "done", "experience", "integrate", "crm", "voice", "bot", "agent", "security",
        "sla", "uptime", "support", "tech", "stack", "ai", "aanandi", "call", "book",
        "appointment", "pay", "payment", "tier", "info", "information", "detail", "details",
        "recommend", "automation", "workflow", "system", "app", "application", "software",
        "company", "firm", "developer", "engineering"
    ]

    # Use word boundary matching so "ai" doesn't match inside "gmail" or "email"
    pattern = r'\b(' + '|'.join(re.escape(kw) for kw in query_keywords) + r')\b'
    if re.search(pattern, text_lower):
        return True

    words = text_lower.split()
    if len(words) > 4:
        return True

    return False

def extract_name(text: str) -> str | None:
    """Extracts clean name if user is introducing themselves, else None."""
    if not text or not text.strip():
        return None

    text_clean = text.strip()
    text_lower = text_clean.lower()

    if is_user_query(text_clean):
        return None

    # Ignore general conversational responses / help queries
    non_names = {
        "hi", "hello", "hey", "start", "thanks", "thank you", "yes", "no", "sure", "ok", "okay",
        "demo", "pricing", "projects", "services", "ai", "bot", "voice", "help", "info", "details",
        "what can you do", "what i can help you with", "how can you help me", "tell me more"
    }
    if text_lower in non_names:
        return None

    prefixes = ["my name is ", "i am ", "i'm ", "this is ", "call me ", "myself "]
    has_prefix = False
    for p in prefixes:
        if text_lower.startswith(p):
            text_clean = text_clean[len(p):].strip()
            has_prefix = True
            break

    words = text_clean.split()
    if 1 <= len(words) <= 3 and all(w.replace("-", "").replace(".", "").replace("_", "").isalpha() for w in words):
        common_words = {"the", "a", "an", "what", "how", "why", "where", "when", "can", "could", "would", "should", "will", "is", "are", "help", "need", "want", "just", "looking", "nothing", "anything", "something"}
        if not has_prefix and any(w.lower() in common_words for w in words):
            return None
        return text_clean.title()

    return None

def generate_ai_answer(user_query: str, kb_data: str) -> str:
    """Generates an intelligent answer using OpenRouter LLM if available, or structured response as fallback."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                model="openai/gpt-4o-mini",
                temperature=0.3
            )
            sys_msg = SystemMessage(content=(
                "You are Aanandi, the elite AI Sales Engineer for Aanandi TechnoSoft. "
                "Answer the user's question clearly, warmly, and professionally using the following Knowledge Base data:\n\n"
                f"{kb_data}\n\n"
                "Keep your response concise and formatted nicely with markdown bullet points."
            ))
            res = llm.invoke([sys_msg, HumanMessage(content=user_query)])
            if res and res.content:
                return res.content.strip()
        except Exception:
            pass

    return (
        f"Here is information about our projects and capabilities:\n\n{kb_data}\n\n"
        "What specific feature or industry solution would you like to explore next?"
    )

# ── Graph Nodes Definition ─────────────────────────────────────────────────────
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

    # ── 1. Check for Call / Booking Request (Overriding Priority) ──────────────
    if any(k in last_msg.lower() for k in ["book", "call", "talk", "demo", "pricing", "tier", "schedule"]):
        return {
            "messages": [AIMessage(content="How would you like to connect with our team?")],
            "lead_stage": "BOOKING_OFFERED",
            "tool_payload": {
                "type": "call_routing",
                "data": {}
            }
        }

    # ── 2. Email Address Input Detection (Direct Priority before Q&A) ───────────
    if ("@" in last_msg and "." in last_msg) or (pending_step == "COLLECT_EMAIL" and "@" in last_msg):
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', last_msg)
        extracted_email = match.group(0).lower() if match else last_msg.strip().lower()
        display_name = user_name if user_name else "there"
        return {
            "messages": [AIMessage(content=f"Thank you, **{display_name}**! What is your contact phone number to finalize your session verification?")],
            "user_email": extracted_email,
            "pending_step": "COLLECT_PHONE",
            "tool_payload": None
        }

    # ── 3. OTP Escape Hatch & Verification ─────────────────────────────────────
    if pending_step == "VERIFY_OTP":
        target_mail = user_email.strip() if (user_email and "@" in user_email) else os.getenv("SMTP_EMAIL", "pyashkumar0312@gmail.com")
        
        # Check for escape hatch requests (Resend OTP or Change Email)
        if any(k in last_msg.lower() for k in ["resend", "resend_otp", "resend code", "didn't receive", "didnt receive"]):
            new_otp = str(random.randint(100000, 999999))
            from dispatch import send_email_dispatch
            send_email_dispatch(
                to_email=target_mail,
                subject="Your Aanandi Security Verification Code (Resent)",
                text_content=f"Hello {user_name or 'Valued Customer'},\n\nYour new 6-digit security code is: {new_otp}\nValid for 10 minutes."
            )
            return {
                "messages": [AIMessage(content=f"🔄 **New verification code sent!**\n\nPlease check your inbox (**{target_mail}**) and enter the 6-digit code below.")],
                "user_email": target_mail,
                "otp_code": new_otp,
                "pending_step": "VERIFY_OTP",
                "tool_payload": {
                    "type": "otp_options",
                    "data": {"user_email": target_mail, "can_resend": True, "can_change_email": True}
                }
            }

        if any(k in last_msg.lower() for k in ["change email", "change_email", "wrong email", "different email"]):
            return {
                "messages": [AIMessage(content="Sure! Please fill in your updated email address below to receive a new code:")],
                "user_email": "",
                "pending_step": "COLLECT_EMAIL",
                "tool_payload": {
                    "type": "lead_form",
                    "data": {"title": "Update Email Address", "fields": ["email"]}
                }
            }

        cleaned_digits = "".join(filter(str.isdigit, last_msg))
        if len(cleaned_digits) == 6 and not is_user_query(last_msg):
            if cleaned_digits == otp_code:
                return {
                    "messages": [AIMessage(content="✅ **Email Verified Successfully!**\n\nHow can I help you today with custom AI agents, workflow automation, or enterprise solutions?")],
                    "is_verified": True,
                    "pending_step": "VERIFIED",
                    "tool_payload": {
                        "type": "mcq",
                        "data": {
                            "title": "Suggested Follow-ups",
                            "options": [
                                "Which projects have you made so far?",
                                "Tell me about Custom CRM Integrations",
                                "How do AI Voice Bots work?",
                                "Talk to AI or Book Call"
                            ]
                        }
                    }
                }
            else:
                return {
                    "messages": [AIMessage(content=f"❌ Invalid verification code. Please check your inbox (**{target_mail}**) and enter the correct 6-digit code.")],
                    "pending_step": "VERIFY_OTP",
                    "tool_payload": {
                        "type": "otp_options",
                        "data": {"user_email": target_mail, "can_resend": True, "can_change_email": True}
                    }
                }

    # ── 4. Phone Number Input Detection ────────────────────────────────────────
    cleaned_digits = "".join(filter(str.isdigit, last_msg))
    if len(cleaned_digits) in [10, 11, 12] and not is_user_query(last_msg) and pending_step in ["COLLECT_PHONE", "COLLECT_EMAIL", "COLLECT_NAME"]:
        user_phone = last_msg.strip()
        target_email = user_email.strip() if (user_email and "@" in user_email) else os.getenv("SMTP_EMAIL", "pyashkumar0312@gmail.com")

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
                f"*(Demo Mode: Your security code is `{new_otp}`)*\n\n"
                "Please type the 6-digit code below to verify your session."
            )
        else:
            msg_text = (
                f"🔐 We've sent a 6-digit verification code to **{target_email}**!\n\n"
                "Please check your inbox and type the 6-digit security code below to verify your session."
            )

        return {
            "messages": [AIMessage(content=msg_text)],
            "user_phone": user_phone,
            "user_email": target_email,
            "otp_code": new_otp,
            "pending_step": "VERIFY_OTP",
            "tool_payload": {
                "type": "otp_options",
                "data": {"user_email": target_email, "can_resend": True, "can_change_email": True}
            }
        }

    # ── 5. Name Input Detection ────────────────────────────────────────────────
    if (pending_step == "COLLECT_NAME" or not user_name) and not is_user_query(last_msg):
        potential_name = extract_name(last_msg)
        if potential_name:
            user_name = potential_name
            return {
                "messages": [AIMessage(content=f"Nice to meet you, **{user_name}**! What is your email address so we can secure your session and send you detailed project briefs?")],
                "user_name": user_name,
                "pending_step": "COLLECT_EMAIL",
                "tool_payload": {
                    "type": "lead_form",
                    "data": {"title": "Submit Email Address", "fields": ["email"]}
                }
            }

    # ── 6. Standalone Greetings ────────────────────────────────────────────────
    if last_msg.lower().strip() in ["hi", "hello", "hey", "start", "hi!", "hello!"]:
        if is_verified:
            return {
                "messages": [AIMessage(content="👋 Welcome back! How can I help you today? Ask me any question or pick a topic below.")],
                "pending_step": "VERIFIED",
                "tool_payload": {
                    "type": "mcq",
                    "data": {
                        "title": "Quick Questions",
                        "options": [
                            "Which projects have you made so far?",
                            "Tell me about Custom CRM Integrations",
                            "How do AI Voice Bots work?",
                            "Talk to AI or Book Call"
                        ]
                    }
                }
            }
        else:
            return {
                "messages": [AIMessage(content="👋 Welcome to Aanandi TechnoSoft! I'm Aanandi, your AI Sales Engineer.\n\nPlease fill out your details below to start your session:")],
                "pending_step": "COLLECT_NAME" if not user_name else pending_step,
                "tool_payload": {
                    "type": "lead_form",
                    "data": {
                        "title": "Quick Session Verification",
                        "fields": ["name", "email", "phone"]
                    }
                }
            }

    # ── 7. Non-blocking Product / Knowledge Base Q&A ────────────────────────────
    kb_res = query_knowledge_base.invoke({"query": last_msg})
    ai_answer = generate_ai_answer(last_msg, kb_res)

    # If lead is NOT yet verified, append the appropriate next prompt in sequence and suppress MCQ options
    if not is_verified:
        payload = None
        if pending_step == "COLLECT_NAME" or not user_name:
            ai_answer += "\n\n---\n👤 **Before we proceed further, may I know your full name?**"
            next_step = "COLLECT_NAME"
            payload = {"type": "lead_form", "data": {"title": "Quick Verification Form", "fields": ["name", "email", "phone"]}}
        elif pending_step == "COLLECT_EMAIL" or not user_email:
            display_name = user_name if user_name else "there"
            ai_answer += f"\n\n---\n📧 **To secure your session, {display_name}, what is your email address?**"
            next_step = "COLLECT_EMAIL"
            payload = {"type": "lead_form", "data": {"title": "Provide Email Address", "fields": ["email"]}}
        elif pending_step == "COLLECT_PHONE" or not user_phone:
            display_name = user_name if user_name else "there"
            ai_answer += f"\n\n---\n📱 **{display_name}, what is your contact phone number to complete verification?**"
            next_step = "COLLECT_PHONE"
            payload = {"type": "lead_form", "data": {"title": "Provide Contact Phone", "fields": ["phone"]}}
        elif pending_step == "VERIFY_OTP":
            target_mail = user_email or "your email"
            ai_answer += f"\n\n---\n🔐 **Please check your inbox and enter the 6-digit verification code sent to {target_mail}.**"
            next_step = "VERIFY_OTP"
            payload = {"type": "otp_options", "data": {"user_email": target_mail, "can_resend": True, "can_change_email": True}}
        else:
            next_step = pending_step

        return {
            "messages": [AIMessage(content=ai_answer)],
            "lead_stage": "QUALIFYING",
            "pending_step": next_step,
            "tool_payload": payload
        }

    # If already verified, return AI answer WITH suggested follow-ups MCQ payload
    return {
        "messages": [AIMessage(content=ai_answer)],
        "lead_stage": "QUALIFYING",
        "pending_step": "VERIFIED",
        "tool_payload": {
            "type": "mcq",
            "data": {
                "title": "Suggested Follow-ups",
                "options": [
                    "Which projects have you made so far?",
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
