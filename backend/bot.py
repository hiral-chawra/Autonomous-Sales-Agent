import os
import requests
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.google.tts import GoogleTTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.aggregators.llm_context import LLMContext

from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame

load_dotenv()

class RawPCMFrameSerializer(FrameSerializer):
    def __init__(self, sample_rate: int = 16000, num_channels: int = 1):
        super().__init__()
        self.sample_rate = sample_rate
        self.num_channels = num_channels

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(
                audio=data,
                sample_rate=self.sample_rate,
                num_channels=self.num_channels
            )
        return None


async def book_meeting(function_name, tool_call_id, args, llm, context, result_callback):
    """Triggers the Cal.com API v2 to book an appointment."""
    url = "https://api.cal.com/v2/bookings"
    payload = {
        "start": args.get("start_time"),
        "eventTypeId": int(os.getenv("CAL_EVENT_TYPE_ID", "7297448")),
        "attendee": {
            "name": args.get("name", "Valued Client"),
            "email": args.get("email", "client@example.com"),
            "timeZone": "Asia/Kolkata",
            "language": "en"
        }
    }
    api_key = os.getenv("CAL_API_KEY") or os.getenv("CAL_COM_API_KEY", "")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "cal-api-version": "2024-08-13",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            await result_callback({"status": "success", "message": "Meeting successfully scheduled."})
        else:
            await result_callback({"status": "error", "message": "Slot unavailable. Please choose another time."})
    except Exception as e:
        await result_callback({"status": "error", "message": str(e)})

# Pre-initialize STT model to make connection handling instant
stt = WhisperSTTService(model="tiny")

async def run_voice_agent(transport):
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    if elevenlabs_key:
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService, ElevenLabsTTSSettings
        tts = ElevenLabsTTSService(
            api_key=elevenlabs_key,
            settings=ElevenLabsTTSSettings(voice="21m00Tcm4TlvDq8ikWAM")
        )
    else:
        from pipecat.services.google.tts import GoogleTTSService, GoogleTTSSettings
        tts = GoogleTTSService(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            settings=GoogleTTSSettings(voice="en-IN-Wavenet-A")
        )

    from pipecat.services.google.llm import GoogleLLMService, GoogleLLMSettings
    llm = GoogleLLMService(
        api_key=os.getenv("GEMINI_API_KEY", ""),
        settings=GoogleLLMSettings(model="gemini-1.5-flash")
    )

    llm.register_function("book_meeting", book_meeting)

    context = LLMContext(
        messages=[{
            "role": "system",
            "content": (
                "You are Aanandi, an AI sales engineer for Aanandi TechnoSoft. Keep answers brief (1-2 sentences). "
                "Help qualify leads and book software demos."
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

    task = PipelineTask(pipeline, params=PipelineParams())
    runner = PipelineRunner()
    await runner.run(task)