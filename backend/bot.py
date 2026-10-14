import io
import av
import edge_tts
import os
import requests
from dotenv import load_dotenv

from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.tts_service import TTSService
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame, TTSStartedFrame, TTSStoppedFrame, TTSAudioRawFrame

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

    async def run_tts(self, text: str, *args, **kwargs):
        try:
            yield TTSStartedFrame()
            communicate = edge_tts.Communicate(text, self._voice)
            mp3_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_bytes += chunk["data"]

            if not mp3_bytes:
                yield TTSStoppedFrame()
                return

            container = av.open(io.BytesIO(mp3_bytes))
            resampler = av.AudioResampler(format="s16", layout="mono", rate=self.sample_rate)

            # 3,200 bytes = 100ms chunks at 16kHz 16-bit mono (ultra-smooth streaming)
            chunk_size = 3200
            buffer = bytearray()

            for frame in container.decode(audio=0):
                resampled_frames = resampler.resample(frame)
                for rf in resampled_frames:
                    buffer.extend(bytes(rf.planes[0]))
                    while len(buffer) >= chunk_size:
                        raw_chunk = bytes(buffer[:chunk_size])
                        del buffer[:chunk_size]
                        yield TTSAudioRawFrame(
                            audio=raw_chunk,
                            sample_rate=self.sample_rate,
                            num_channels=1
                        )

            # Flush any remaining frames from the resampler
            for rf in resampler.resample(None):
                buffer.extend(bytes(rf.planes[0]))

            if len(buffer) > 0:
                yield TTSAudioRawFrame(
                    audio=bytes(buffer),
                    sample_rate=self.sample_rate,
                    num_channels=1
                )
            yield TTSStoppedFrame()
        except Exception as e:
            print(f"[EdgeTTS] Error rendering voice: {e}")
            yield TTSStoppedFrame()


# Pre-initialize STT model
stt = WhisperSTTService(settings=WhisperSTTService.Settings(model="tiny"))

async def run_voice_agent(transport, chat_history: list = None):
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    # Initialize LLM with automatic working key selection
    if gemini_key and gemini_key.startswith("AIzaSy"):
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

    # 2. Resilient Neural Voice Synthesis (EdgeTTS) with Markdown filtering & VAD Processor
    tts = EdgeTTSService(
        voice="en-IN-NeerjaNeural",
        sample_rate=16000,
        text_filters=[MarkdownTextFilter()]
    )
    
    # Configure VAD to detect end-of-speech faster (0.4s pause instead of ~1s)
    vad_analyzer = SileroVADAnalyzer(params=VADParams(stop_secs=0.4))
    vad_processor = VADProcessor(vad_analyzer=vad_analyzer)

    # 3. Build memory context combining System Prompt + Previous Chat History
    base_messages = [{
        "role": "system",
        "content": (
            "You are Aanandi, the client-facing AI Sales Engineer for Aanandi TechnoSoft LLP (https://aanandi.in). "
            "You are speaking with a prospective client on a live voice call, transitioning from website text chat. "
            "Aanandi TechnoSoft is an elite AI-Powered Product Engineering and Workflow Automation Partner with 15+ years of experience, "
            "500+ delivered platforms, and 9 live commercial apps (Uclean Laundry, Swagmee Fashion, Jotno Patient Healthcare EHR, HungerGo, Careasy, etc.). "
            "STRICT RULES: "
            "1. You pitch ONLY Aanandi's client services, workflow automations, SaaS platforms, and portfolio. You are EXPLICITLY FORBIDDEN from discussing your own underlying source code or internal stack (do NOT mention LangGraph, Pipecat, FastAPI, WebSockets, or WebRTC). "
            "2. Review the chat history carefully, greet them by name if known, and acknowledge any requirements they already shared. "
            "3. Keep answers conversational, consultative, and brief (1-2 spoken sentences). "
            "4. Do not use any markdown formatting (no asterisks, no bullet points). "
            "5. Explicitly ask the user what business workflow or software platform they want to build. "
            "6. DO NOT ask to book a calendar slot during the call, as they are speaking with you directly. When concluding, explain they can connect with our senior technical leadership team."
        )
    }]

    # Inject history from text chat session if available
    if chat_history:
        base_messages.extend(chat_history)
    else:
        base_messages.append({"role": "assistant", "content": "Hello! I'm Aanandi. How can I help you with your project today?"})

    context = LLMContext(messages=base_messages)
    context_aggregator = LLMContextAggregatorPair(context)

    # 4. Pipeline consisting of FrameProcessors
    pipeline = Pipeline([
        transport.input(),
        vad_processor,
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