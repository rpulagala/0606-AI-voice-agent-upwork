import logging
from typing import Callable, Awaitable

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

logger = logging.getLogger(__name__)

# Audio format: 16 kHz mono linear16 PCM — matches browser AudioWorklet capture.
# For Twilio / phone swap to: encoding="mulaw", sample_rate=8000
_LIVE_OPTIONS = LiveOptions(
    model="nova-2",
    language="en-US",
    encoding="linear16",
    sample_rate=16000,
    channels=1,
    smart_format=True,
    interim_results=True,
    utterance_end_ms="1500",
    vad_events=True,       # enables SpeechStarted — needed for barge-in
    endpointing=400,
)


class DeepgramSTT:
    """
    Async wrapper around the Deepgram live-transcription WebSocket.

    Usage
    -----
    stt = DeepgramSTT(api_key)
    conn = await stt.connect(on_final, on_speech_start, on_utterance_end)
    await stt.send(conn, audio_bytes)   # call repeatedly with mic chunks
    await stt.finish(conn)              # call on disconnect
    """

    def __init__(self, api_key: str) -> None:
        config = DeepgramClientOptions(options={"keepalive": "true"})
        self._client = DeepgramClient(api_key, config)

    async def connect(
        self,
        on_final: Callable[..., Awaitable[None]],
        on_speech_start: Callable[..., Awaitable[None]],
        on_utterance_end: Callable[..., Awaitable[None]],
    ):
        """
        Open a Deepgram live-transcription connection and register callbacks.

        The SDK emits events as: handler(connection, <event_kwarg>=data, **kwargs)
        All handlers must be async def and accept the connection as first positional arg.

        Parameters
        ----------
        on_final        : called with (transcript: str) on is_final transcript
        on_speech_start : called with no args on SpeechStarted (barge-in signal)
        on_utterance_end: called with no args after utterance_end_ms of silence
        """
        conn = self._client.listen.asyncwebsocket.v("1")

        async def _on_transcript(_, result, **kwargs):
            try:
                transcript = result.channel.alternatives[0].transcript
                if result.is_final and transcript.strip():
                    logger.debug("STT final: %s", transcript)
                    await on_final(transcript)
            except Exception:
                logger.exception("Error in STT transcript handler")

        async def _on_speech_started(_, speech_started, **kwargs):
            try:
                logger.debug("STT: speech started")
                await on_speech_start()
            except Exception:
                logger.exception("Error in STT speech-started handler")

        async def _on_utterance_end(_, utterance_end, **kwargs):
            try:
                logger.debug("STT: utterance end")
                await on_utterance_end()
            except Exception:
                logger.exception("Error in STT utterance-end handler")

        async def _on_error(_, error, **kwargs):
            logger.error("Deepgram error: %s", error)

        async def _on_close(_, close, **kwargs):
            logger.info("Deepgram connection closed")

        conn.on(LiveTranscriptionEvents.Transcript,    _on_transcript)
        conn.on(LiveTranscriptionEvents.SpeechStarted, _on_speech_started)
        conn.on(LiveTranscriptionEvents.UtteranceEnd,  _on_utterance_end)
        conn.on(LiveTranscriptionEvents.Error,         _on_error)
        conn.on(LiveTranscriptionEvents.Close,         _on_close)

        started = await conn.start(_LIVE_OPTIONS)
        if not started:
            raise RuntimeError("Failed to open Deepgram live connection")

        logger.info("Deepgram STT connected (nova-2)")
        return conn

    @staticmethod
    async def send(conn, audio_bytes: bytes) -> None:
        """Stream a raw audio chunk to the open Deepgram connection."""
        await conn.send(audio_bytes)

    @staticmethod
    async def finish(conn) -> None:
        """Flush and close the Deepgram connection gracefully."""
        await conn.finish()
        logger.info("Deepgram STT connection finished")
