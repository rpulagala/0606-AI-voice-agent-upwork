import logging
from typing import AsyncGenerator

from elevenlabs import VoiceSettings
from elevenlabs.client import AsyncElevenLabs

logger = logging.getLogger(__name__)

_MODEL = "eleven_turbo_v2"    # lowest-latency ElevenLabs model
_OUTPUT_FORMAT = "mp3_44100_128"
_VOICE_SETTINGS = VoiceSettings(
    stability=0.5,
    similarity_boost=0.75,
    style=0.0,
    use_speaker_boost=True,
)


class ElevenLabsTTS:
    """
    Async wrapper around ElevenLabs streaming TTS.

    Usage
    -----
    tts = ElevenLabsTTS(api_key, voice_id)
    async for chunk in tts.stream("Hello there."):
        await websocket.send_bytes(chunk)
    """

    def __init__(self, api_key: str, voice_id: str) -> None:
        self._client = AsyncElevenLabs(api_key=api_key)
        self._voice_id = voice_id

    async def stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Yield MP3 audio chunks as they arrive from ElevenLabs.
        First chunk typically arrives in ~300 ms (eleven_turbo_v2).
        Call once per sentence for best latency.
        """
        logger.debug("TTS stream start: %r", text[:80])
        try:
            async for chunk in self._client.text_to_speech.convert(
                voice_id=self._voice_id,
                text=text,
                model_id=_MODEL,
                voice_settings=_VOICE_SETTINGS,
                output_format=_OUTPUT_FORMAT,
                optimize_streaming_latency="4",  # max latency reduction
            ):
                if chunk:
                    yield chunk
        except Exception:
            logger.exception("ElevenLabs TTS error for text: %r", text[:80])
            raise
