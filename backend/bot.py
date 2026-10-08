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


# Pre-initialize STT model to make connection handling instant
stt = WhisperSTTService(model="tiny")

async def run_voice_agent(transport, chat_history: list = None):
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    # 1. Initialize LLM with automatic working key selection
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

    # 2. Resilient Neural Voice Synthesis (EdgeTTS) & VAD Processor
    tts = EdgeTTSService(voice="en-IN-NeerjaNeural", sample_rate=16000)
    
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.processors.audio.vad_processor import VADProcessor
    vad_analyzer = SileroVADAnalyzer()
    vad_processor = VADProcessor(vad_analyzer=vad_analyzer)

    # 3. Build memory context combining System Prompt + Previous Chat History
    base_messages = [{
        "role": "system",
        "content": (
            "You are Aanandi, an AI sales engineer for Aanandi TechnoSoft. "
            "You are now on a live voice call with the user, transitioning from a text chat. "
            "DO NOT ask to book a calendar slot, as they are already speaking with you directly. "
            "Review the chat history, greet them by name if known, and ask follow-up questions "
            "about their project requirements or enterprise needs. Keep answers conversational and brief (1-2 sentences)."
        )
    }]

    # Inject history from text chat session if available
    if chat_history:
        base_messages.extend(chat_history)
    else:
        base_messages.append({"role": "assistant", "content": "Hello! I'm Aanandi. How can I help you with your project today?"})

    context = LLMContext(messages=base_messages)
    context_aggregator = LLMContextAggregatorPair(context)

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