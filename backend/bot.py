import os
import requests
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

# Updated 1.x Service Imports
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

# Updated 1.x Universal Context Imports
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.aggregators.llm_context import LLMContext

load_dotenv()

async def book_meeting(function_name, tool_call_id, args, llm, context, result_callback):
    """Triggers the Cal.com API v2 to book an appointment."""
    url = "https://api.cal.com/v2/bookings"
    payload = {
        "start": args["start_time"],
        "eventTypeId": int(os.getenv("CAL_EVENT_TYPE_ID", "0")),
        "attendees": [
            {
                "name": args["name"],
                "email": args["email"],
                "timeZone": "Asia/Kolkata"
            }
        ]
    }
    headers = {
        "Authorization": f"Bearer {os.getenv('CAL_COM_API_KEY')}",
        "cal-api-version": "2026-02-25",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in (200, 201):
            await result_callback({"status": "success", "message": "Meeting successfully scheduled."})
        else:
            await result_callback({"status": "error", "message": "Slot unavailable. Please choose another time."})
    except Exception as e:
        await result_callback({"status": "error", "message": str(e)})

async def run_voice_agent(transport):
    stt = WhisperSTTService(model="base")
    tts = ElevenLabsTTSService(api_key=os.getenv("ELEVENLABS_API_KEY"))
    llm = GoogleLLMService(api_key=os.getenv("GEMINI_API_KEY"), model="gemini-1.5-flash")

    llm.register_function("book_meeting", book_meeting)

    # 1.x Universal Context Implementation
    context = LLMContext(
        messages=[{
            "role": "system",
            "content": (
                "You are an AI sales assistant for Aanandi Technosoft. Keep answers brief (1-2 sentences). "
                "If the user asks to speak with a human or book an appointment, collect their name, "
                "email address, and target date/time, then trigger the book_meeting tool with start_time "
                "formatted in ISO 8601 (e.g., 2026-10-05T14:00:00Z)."
            )
        }]
    )
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant()
    ])

    task = PipelineTask(pipeline, PipelineParams())
    runner = PipelineRunner()
    await runner.run(task)