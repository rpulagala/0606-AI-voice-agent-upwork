import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
# Each handler is an async function: async def handler(input: dict) -> str
# Register real integrations here in Week 3 (Google Calendar, HubSpot, etc.)
# ---------------------------------------------------------------------------

_REGISTRY: dict = {}


def register(name: str):
    """Decorator to register a tool handler by name."""
    def decorator(fn):
        _REGISTRY[name] = fn
        return fn
    return decorator


async def dispatch(name: str, tool_input: dict) -> str:
    """
    Route an LLM tool call to its handler.
    Falls back to a stub response if no real handler is registered.
    """
    handler = _REGISTRY.get(name)
    if handler:
        logger.info("Tool dispatch: %s(%s)", name, tool_input)
        return await handler(tool_input)

    # Stub fallback — remove each stub as real integrations are added in Week 3
    logger.info("Tool stub: %s(%s)", name, tool_input)
    stubs = {
        "book_appointment":      _stub_book_appointment,
        "search_knowledge_base": _stub_search_kb,
        "create_crm_lead":       _stub_create_lead,
        "lookup_customer":       _stub_lookup_customer,
        "send_followup_email":   _stub_send_email,
    }
    stub = stubs.get(name)
    if stub:
        return await stub(tool_input)

    return f"{name} completed successfully."


# ---------------------------------------------------------------------------
# Stub handlers (Week 2) — replace with real integrations in Week 3
# ---------------------------------------------------------------------------

async def _stub_book_appointment(inp: dict) -> str:
    date  = inp.get("date", "the requested date")
    time  = inp.get("time", "the requested time")
    name  = inp.get("name", "the caller")
    return f"Appointment booked for {name} on {date} at {time}."


async def _stub_search_kb(inp: dict) -> str:
    query = inp.get("query", "")
    return (
        f"Based on our knowledge base: '{query}' — "
        "I found relevant information. Our team can provide full details; "
        "would you like me to send a follow-up email?"
    )


async def _stub_create_lead(inp: dict) -> str:
    name = inp.get("name", "the caller")
    return f"Lead record created in the CRM for {name}."


async def _stub_lookup_customer(inp: dict) -> str:
    identifier = inp.get("email") or inp.get("phone") or "the provided details"
    return f"Customer record found for {identifier}: returning customer, last contact 30 days ago."


async def _stub_send_email(inp: dict) -> str:
    to = inp.get("to", "the caller")
    return f"Follow-up email sent to {to} with a summary of today's conversation."
