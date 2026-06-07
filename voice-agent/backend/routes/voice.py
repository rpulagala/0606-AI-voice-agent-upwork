import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import settings
from prompts import SYSTEM_PROMPT, TOOLS
from services.llm import ClaudeLLM
from services.memory import ConversationMemory
from services.stt import DeepgramSTT
from services.tts import ElevenLabsTTS
from tools.router import dispatch

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])

_SENTENCE_ENDS = (".", "!", "?")
_MAX_TOOL_ROUNDS = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(buffer: str) -> tuple[list[str], str]:
    """Pop completed sentences from the front of buffer; return (sentences, rest)."""
    sentences: list[str] = []
    while True:
        earliest = -1
        for sep in _SENTENCE_ENDS:
            pos = buffer.find(sep)
            if pos != -1 and (earliest == -1 or pos < earliest):
                earliest = pos
        if earliest == -1:
            break
        sentence = buffer[: earliest + 1].strip()
        buffer = buffer[earliest + 1:]
        if sentence:
            sentences.append(sentence)
    return sentences, buffer


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()

    session_id = str(uuid4())
    logger.info("Voice session started: %s  client=%s", session_id, websocket.client)

    memory: ConversationMemory = websocket.app.state.memory
    stt = DeepgramSTT(settings.DEEPGRAM_API_KEY)
    tts = ElevenLabsTTS(settings.ELEVENLABS_API_KEY, settings.ELEVENLABS_VOICE_ID)
    llm = ClaudeLLM(settings.ANTHROPIC_API_KEY)

    messages: list[dict] = await memory.load(session_id)
    transcript_buffer: str = ""
    respond_task: asyncio.Task | None = None
    ws_lock = asyncio.Lock()

    # -- WebSocket write helpers --------------------------------------------

    async def send_audio(chunk: bytes) -> None:
        async with ws_lock:
            await websocket.send_bytes(chunk)

    async def send_ctrl(data: dict) -> None:
        async with ws_lock:
            await websocket.send_text(json.dumps(data))

    # -- STT callbacks ------------------------------------------------------

    async def on_final(transcript: str) -> None:
        nonlocal transcript_buffer
        transcript_buffer += (" " if transcript_buffer else "") + transcript
        logger.debug("STT final: %r", transcript)

    async def on_speech_start() -> None:
        nonlocal respond_task
        if respond_task and not respond_task.done():
            logger.info("Barge-in — cancelling active response")
            respond_task.cancel()
        await send_ctrl({"type": "speech_start"})

    async def on_utterance_end() -> None:
        nonlocal transcript_buffer, respond_task
        text = transcript_buffer.strip()
        transcript_buffer = ""
        if not text:
            return
        logger.info("Utterance complete: %r", text)
        await send_ctrl({"type": "transcript", "text": text})
        respond_task = asyncio.create_task(_respond(text))

    # -- LLM → TTS pipeline -------------------------------------------------

    async def _respond(user_text: str) -> None:
        messages.append({"role": "user", "content": user_text})

        for _round in range(_MAX_TOOL_ROUNDS):
            assistant_text = ""
            sentence_buffer = ""
            tool_event: dict | None = None

            try:
                async for event in llm.chat(
                    messages=messages,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                ):
                    if event["type"] == "text":
                        assistant_text += event["text"]
                        sentence_buffer += event["text"]

                        sentences, sentence_buffer = _split_sentences(sentence_buffer)
                        for sentence in sentences:
                            async for chunk in tts.stream(sentence):
                                await send_audio(chunk)

                    elif event["type"] == "tool_use":
                        tool_event = event

            except asyncio.CancelledError:
                logger.info("BARGE-IN: response cancelled mid-turn")
                return

            # Flush any trailing text without a sentence-ending punctuation mark
            if sentence_buffer.strip():
                try:
                    async for chunk in tts.stream(sentence_buffer.strip()):
                        await send_audio(chunk)
                except asyncio.CancelledError:
                    return

            if tool_event:
                content: list[dict] = []
                if assistant_text.strip():
                    content.append({"type": "text", "text": assistant_text.strip()})
                content.append({
                    "type":  "tool_use",
                    "id":    tool_event["id"],
                    "name":  tool_event["name"],
                    "input": tool_event["input"],
                })
                messages.append({"role": "assistant", "content": content})

                tool_result = await dispatch(tool_event["name"], tool_event["input"])
                messages.append({
                    "role": "user",
                    "content": [{
                        "type":        "tool_result",
                        "tool_use_id": tool_event["id"],
                        "content":     tool_result,
                    }],
                })

            else:
                if assistant_text.strip():
                    messages.append({"role": "assistant", "content": assistant_text.strip()})
                break

        logger.info("Response done (%d chars). History: %d messages", len(assistant_text), len(messages))
        await memory.save(session_id, messages)
        await send_ctrl({"type": "response_done"})

    # -- Audio receive loop -------------------------------------------------

    try:
        stt_conn = await stt.connect(on_final, on_speech_start, on_utterance_end)
    except Exception:
        logger.exception("Failed to open Deepgram STT connection")
        await websocket.close(code=1011)
        return

    try:
        async for audio_chunk in websocket.iter_bytes():
            await stt.send(stt_conn, audio_chunk)
    except WebSocketDisconnect:
        logger.info("Voice session disconnected: %s", session_id)
    except Exception:
        logger.exception("Unexpected error in voice receive loop")
    finally:
        await stt.finish(stt_conn)
        if respond_task and not respond_task.done():
            respond_task.cancel()
        await memory.save(session_id, messages)
        logger.info("Voice session closed: %s  total messages: %d", session_id, len(messages))
