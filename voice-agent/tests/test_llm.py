"""
Day 4 — Claude LLM streaming + tool call test.
Run AFTER implementing backend/services/llm.py (ClaudeLLM class).

Requires in voice-agent/.env:
    ANTHROPIC_API_KEY=sk-ant-...

Run:
    python tests/test_llm.py                  # all cases
    python tests/test_llm.py --case plain     # simple reply, no tools
    python tests/test_llm.py --case tool      # expects book_appointment call
    python tests/test_llm.py --case multi     # multi-turn conversation

Expected output (--case tool):
    --- tool: appointment booking ---
    [user] I'd like to book for next Tuesday at 2pm. My name is Sarah.
    [text] "Sure, let me book..."  @ 412 ms
    [tool] book_appointment({"date": "2026-06-09", "time": "14:00", "name": "Sarah"})  @ 510 ms
    Done. 1 text event(s), 1 tool call(s), first-event: 412 ms  ✓

ClaudeLLM interface this test expects (services/llm.py):
    class ClaudeLLM:
        def __init__(self, api_key: str, model: str = "claude-sonnet-4-6")
        async def chat(
            self,
            messages: list[dict],
            system: str = "",
            tools: list[dict] | None = None,
        ) -> AsyncGenerator[dict, None]
        # yields: {"type": "text", "text": "..."} | {"type": "tool_use", "name": "...", "input": {...}}
"""
import asyncio
import argparse
import sys
import os
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

FIRST_TOKEN_TARGET_MS = 800

SYSTEM_PROMPT = (
    "You are a concise voice assistant. "
    "Reply in 1–2 natural spoken sentences (under 35 words). "
    "Use the provided tools when the caller's request requires one."
)

TOOLS = [
    {
        "name": "book_appointment",
        "description": "Book a calendar appointment for the caller.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date":  {"type": "string", "description": "ISO 8601, e.g. 2026-06-10"},
                "time":  {"type": "string", "description": "24 h, e.g. 14:00"},
                "name":  {"type": "string", "description": "Caller full name"},
                "email": {"type": "string", "description": "Caller email (optional)"},
            },
            "required": ["date", "time", "name"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": "Search the company FAQ / knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]

CASES = {
    "plain": {
        "desc": "simple greeting - no tool call expected",
        "messages": [{"role": "user", "content": "Hi, can you hear me?"}],
        "expect_tool": None,
    },
    "tool": {
        "desc": "appointment booking - expects book_appointment call",
        "messages": [
            {"role": "user",
             "content": "I'd like to book an appointment for next Tuesday at 2pm. "
                        "My name is Sarah Chen."},
        ],
        "expect_tool": "book_appointment",
    },
    "multi": {
        "desc": "multi-turn conversation",
        "messages": [
            {"role": "user",      "content": "What are your opening hours?"},
            {"role": "assistant", "content": "We're open Monday to Friday, 9am to 5pm."},
            {"role": "user",      "content": "Great - can I book this Friday at 3pm? "
                                             "Name is James Park."},
        ],
        "expect_tool": "book_appointment",
    },
    "faq": {
        "desc": "knowledge base lookup",
        "messages": [{"role": "user", "content": "Do you offer free consultations?"}],
        "expect_tool": "search_knowledge_base",
    },
}


async def run_case(llm, name: str, case: dict):
    print(f"\n--- {name}: {case['desc']} ---")
    for m in case["messages"]:
        print(f"  [{m['role']}] {m['content']}")
    print()

    text_events = []
    tool_calls = []
    t_start = time.perf_counter()
    t_first = None

    async for event in llm.chat(
        messages=case["messages"],
        system=SYSTEM_PROMPT,
        tools=TOOLS,
    ):
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        if t_first is None:
            t_first = elapsed_ms

        if event["type"] == "text":
            text_events.append(event["text"])
            print(f"  [text] {event['text']!r}  @ {elapsed_ms:.0f} ms")
        elif event["type"] == "tool_use":
            tool_calls.append(event)
            print(f"  [tool] {event['name']}({event['input']})  @ {elapsed_ms:.0f} ms")

    latency_ok = t_first and t_first <= FIRST_TOKEN_TARGET_MS
    status = "OK" if latency_ok else "WARN: slow"
    print(f"\n  Done. {len(text_events)} text event(s), {len(tool_calls)} tool call(s), "
          f"first-event: {t_first:.0f} ms  {status}")

    # Assertions
    expected_tool = case["expect_tool"]
    if expected_tool:
        assert tool_calls, (
            f"[{name}] Expected tool call '{expected_tool}' but got none.\n"
            f"  Full response: {''.join(text_events)}\n"
            f"  Check system prompt or tools list."
        )
        got = tool_calls[0]["name"]
        assert got == expected_tool, (
            f"[{name}] Expected '{expected_tool}', got '{got}'"
        )
        print(f"  [OK] tool call validated: {got}")
        if expected_tool == "book_appointment":
            inp = tool_calls[0]["input"]
            assert "name" in inp, f"book_appointment missing 'name' field: {inp}"
            assert "date" in inp or "time" in inp, \
                f"book_appointment missing date/time: {inp}"
    else:
        assert text_events, f"[{name}] Expected text response but got none"
        assert not tool_calls, \
            f"[{name}] Did not expect a tool call but got: {[t['name'] for t in tool_calls]}"

    return {"name": name, "first_ms": t_first, "text": len(text_events), "tools": len(tool_calls)}


async def run(selected_cases: list[str]):
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY in ("placeholder", "stub", ""):
        print("ERROR: ANTHROPIC_API_KEY is not set in voice-agent/.env")
        print("       Get your key at console.anthropic.com")
        sys.exit(1)

    from services.llm import ClaudeLLM

    llm = ClaudeLLM(api_key=ANTHROPIC_API_KEY)
    results = []

    for name in selected_cases:
        result = await run_case(llm, name, CASES[name])
        results.append(result)

    print(f"\n{'-' * 55}")
    print(f"Cases run: {len(results)}")
    avg_first = sum(r["first_ms"] for r in results if r["first_ms"]) / len(results)
    print(f"Avg first-event latency: {avg_first:.0f} ms  (target <= {FIRST_TOKEN_TARGET_MS} ms)")
    slow = [r for r in results if r["first_ms"] and r["first_ms"] > FIRST_TOKEN_TARGET_MS]
    if slow:
        print(f"WARN: {len(slow)} case(s) exceeded latency target: {[r['name'] for r in slow]}")
    else:
        print("OK   All cases passed assertions and latency target")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Claude LLM streaming")
    parser.add_argument(
        "--case",
        choices=[*CASES.keys(), "all"],
        default="all",
        help="Which test case to run (default: all)",
    )
    args = parser.parse_args()
    cases = list(CASES.keys()) if args.case == "all" else [args.case]
    asyncio.run(run(cases))
