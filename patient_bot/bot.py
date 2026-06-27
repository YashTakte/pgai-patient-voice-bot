"""
patient_bot/bot.py
------------------
The Pipecat pipeline that powers our simulated patient.

Audio flows like this:

    Twilio WebSocket  ->  STT (Deepgram)  ->  LLM (the "patient")  ->  TTS (Cartesia)  ->  Twilio WebSocket

Pipecat handles the hard parts for us: VAD (knowing when the other agent
stopped talking), interruption/barge-in, and turn-taking. We just describe
the patient's persona + goal via a system prompt and let it converse.

Both sides of the call are captured as text and the audio is recorded, so we
can review each call afterwards and write the bug report.

Written against Pipecat 1.4.0 (universal LLMContext + LLMContextAggregatorPair;
the bot's first turn is triggered with LLMRunFrame).
"""

import datetime
import os
import sys
import wave

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMRunFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

logger.remove()
logger.add(sys.stderr, level="INFO")


class Transcript:
    """Shared, ordered collector for both sides of the conversation.

    Two small probe processors feed this: one placed right after STT
    (captures the AGENT's transcribed speech) and one placed right after
    the LLM (captures the PATIENT's generated words). Keeping a single
    shared collector means the lines stay in the order they happened.

    Each line is stamped with the elapsed time since the call started
    (mm:ss), which makes it easy to jump to the moment in the recording,
    exactly the format the bug report uses ("transcript at 1:23").
    """

    def __init__(self):
        import time

        self.lines = []
        self._agent_buf = []
        self._patient_buf = []
        self._start = time.monotonic()
        self._time = time  # keep a handle for stamping

    def _stamp(self):
        elapsed = int(self._time.monotonic() - self._start)
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

    def add_agent_text(self, text):
        # A new agent utterance means the patient's last line is finished.
        self.flush_patient()
        self._agent_buf.append(text)

    def add_patient_text(self, text):
        # A new patient word means the agent's last line is finished.
        self.flush_agent()
        self._patient_buf.append(text)

    def flush_agent(self):
        if self._agent_buf:
            text = " ".join(self._agent_buf).strip()
            if text:
                line = f"[{self._stamp()}] [AGENT] {text}"
                self.lines.append(line)
                logger.info(line)
            self._agent_buf = []

    def flush_patient(self):
        if self._patient_buf:
            text = "".join(self._patient_buf).strip()
            if text:
                line = f"[{self._stamp()}] [PATIENT] {text}"
                self.lines.append(line)
                logger.info(line)
            self._patient_buf = []

    def flush_all(self):
        self.flush_agent()
        self.flush_patient()


class AgentProbe(FrameProcessor):
    """Captures the agent's transcribed speech. Placed right after STT."""

    def __init__(self, transcript: Transcript):
        super().__init__()
        self._t = transcript

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            self._t.add_agent_text(frame.text)
        await self.push_frame(frame, direction)


class PatientProbe(FrameProcessor):
    """Captures the patient's generated words. Placed right after the LLM."""

    def __init__(self, transcript: Transcript):
        super().__init__()
        self._t = transcript

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            self._t.add_patient_text(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            self._t.flush_patient()
        await self.push_frame(frame, direction)


async def run_bot(
    websocket,
    stream_sid: str,
    call_sid: str,
    system_prompt: str,
    opening_line: str,
    scenario_name: str,
    patient_speaks_first: bool = False,
    voice_id: str | None = None,
):
    """Build and run the patient pipeline for a single call.

    patient_speaks_first:
        False (default) -> the agent greets first (realistic for a real
        production line), then the patient responds. True -> the patient
        opens the call immediately (useful for some edge-case tests).
    voice_id:
        Cartesia voice ID for this patient. Falls back to CARTESIA_VOICE_ID
        from the environment if a scenario doesn't specify one.
    """

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=serializer,
        ),
    )

    # --- The three AI services ---------------------------------------
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o",
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id=voice_id
        or os.getenv("CARTESIA_VOICE_ID", "79a125e8-cd45-4c13-8a67-188112f4dd22"),
    )

    # The patient's brain: persona + goal live in the system prompt.
    messages = [{"role": "system", "content": system_prompt}]
    context = LLMContext(messages)
    aggregators = LLMContextAggregatorPair(context)

    # Record raw audio (both sides mixed) for the deliverable.
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_buffer = AudioBufferProcessor()

    # Shared transcript + two probes (agent side, patient side).
    transcript = Transcript()
    agent_probe = AgentProbe(transcript)
    patient_probe = PatientProbe(transcript)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            agent_probe,                # capture AGENT speech right after STT
            aggregators.user(),
            llm,
            patient_probe,              # capture PATIENT words right after LLM
            tts,
            transport.output(),
            audio_buffer,
            aggregators.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            allow_interruptions=True,
        ),
    )

    recording_path = f"recordings/{scenario_name}_{ts}.wav"

    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        os.makedirs("recordings", exist_ok=True)
        with wave.open(recording_path, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio)
        logger.info(f"Saved recording -> {recording_path}")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected.")
        await audio_buffer.start_recording()
        if patient_speaks_first:
            # Patient opens the call immediately.
            logger.info("Patient will open the call.")
            context.add_message(
                {
                    "role": "system",
                    "content": f"Begin the call now by saying: {opening_line}",
                }
            )
            await task.queue_frames([LLMRunFrame()])
        else:
            # Realistic: let the agent greet first. The patient will reply
            # when it hears the agent (driven by VAD + the user aggregator).
            logger.info("Waiting for the agent to greet first.")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        # Persist transcript on hang-up.
        transcript.flush_all()
        os.makedirs("transcripts", exist_ok=True)
        tpath = f"transcripts/{scenario_name}_{ts}.txt"
        with open(tpath, "w", encoding="utf-8") as f:
            f.write("\n".join(transcript.lines))
        logger.info(f"Saved transcript -> {tpath}")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)