import logging
from typing import AsyncGenerator

import anthropic

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024


class ClaudeLLM:
    """
    Async streaming wrapper around the Anthropic Messages API.

    Usage
    -----
    llm = ClaudeLLM(api_key)
    async for event in llm.chat(messages, system=SYSTEM_PROMPT, tools=TOOLS):
        if event["type"] == "text":
            sentence_buffer += event["text"]   # feed to TTS sentence-by-sentence
        elif event["type"] == "tool_use":
            result = await dispatch_tool(event["name"], event["input"])

    Yields
    ------
    {"type": "text",     "text": "..."}                         — streamed token
    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}  — complete call
    """

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        logger.debug("LLM chat: model=%s, messages=%d, tools=%d",
                     self._model, len(messages), len(tools or []))
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                # Yield text tokens as they arrive — feeds TTS without waiting for full response
                async for token in stream.text_stream:
                    if token:
                        yield {"type": "text", "text": token}

                # After streaming completes, emit any tool calls
                # (input is already a parsed dict — no JSON handling needed)
                final = await stream.get_final_message()
                for block in final.content:
                    if block.type == "tool_use":
                        logger.debug("LLM tool call: %s(%s)", block.name, block.input)
                        yield {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }

        except anthropic.APIStatusError as e:
            logger.error("Anthropic API error %s: %s", e.status_code, e.message)
            raise
        except anthropic.APIConnectionError:
            logger.exception("Anthropic connection error")
            raise
