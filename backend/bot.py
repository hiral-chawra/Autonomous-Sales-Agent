import io
import av
import edge_tts
import os
import requests
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.tts_service import TTSService
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


class EdgeTTSService(TTSService):
    """High-quality streaming Neural TTS service using EdgeTTS and PyAV for 16kHz PCM audio."""
    def __init__(self, voice: str = "en-IN-NeerjaNeural", sample_rate: int = 16000, **kwargs):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._voice = voice

    async def run_tts(self, text: str):
        try:
            communicate = edge_tts.Communicate(text, self._voice)
            mp3_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_bytes += chunk["data"]

            if not mp3_bytes:
                return

            container = av.open(io.BytesIO(mp3_bytes))
            resampler = av.AudioResampler(format="s16", layout="mono", rate=self.sample_rate)

            # Yield PCM16 frames in 1600-byte (50ms) chunks for real-time audio playback
            chunk_size = 1600
            buffer = bytearray()

            for frame in container.decode(audio=0):
                resampled_frames = resampler.resample(frame)
                for rf in resampled_frames:
                    buffer.extend(bytes(rf.planes[0]))
                    while len(buffer) >= chunk_size:
                        raw_chunk = bytes(buffer[:chunk_size])
                        del buffer[:chunk_size]
                        yield OutputAudioRawFrame(
                            audio=raw_chunk,
                            sample_rate=self.sample_rate,
                            num_channels=1
                        )

            if len(buffer) > 0:
                yield OutputAudioRawFrame(
                    audio=bytes(buffer),
                    sample_rate=self.sample_rate,
                    num_channels=1
                )
        except Exception as e:
            print(f"[EdgeTTS] Error rendering voice: {e}")


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
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    # 1. Initialize LLM with automatic working key selection
    if openrouter_key and openrouter_key.startswith("sk-or"):
        from pipecat.services.openai.llm import OpenAILLMService
        llm = OpenAILLMService(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            settings=OpenAILLMService.Settings(model="openai/gpt-4o-mini")
        )
    elif gemini_key and gemini_key.startswith("AIzaSy"):
        from pipecat.services.google.llm import GoogleLLMService, GoogleLLMSettings
        llm = GoogleLLMService(
            api_key=gemini_key,
            settings=GoogleLLMSettings(model="gemini-1.5-flash")
        )
    else:
        from pipecat.services.openai.llm import OpenAILLMService
        llm = OpenAILLMService(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            settings=OpenAILLMService.Settings(model="openai/gpt-4o-mini")
        )

    llm.register_function("book_meeting", book_meeting)

    # 2. Resilient Neural Voice Synthesis (EdgeTTS)
    tts = EdgeTTSService(voice="en-IN-NeerjaNeural", sample_rate=16000)

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