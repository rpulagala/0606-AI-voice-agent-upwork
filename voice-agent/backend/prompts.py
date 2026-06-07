SYSTEM_PROMPT = """You are Aria, a professional AI voice assistant.

Speak naturally, as if on a phone call. Follow these rules strictly:

RESPONSE STYLE:
- Keep every response under 60 words. Never cut a sentence mid-thought.
- Use plain spoken language only — no bullet points, numbered lists, or markdown.
- Use natural openers: "Sure!", "Of course.", "Great question.", "Let me check that for you."
- If using a tool, say "One moment..." before invoking it.
- After a tool completes, confirm conversationally: "Done! I've booked you for Tuesday at 2 PM."

CAPABILITIES:
- Book and look up appointments.
- Answer product, service, and FAQ questions by searching the knowledge base.
- Create and retrieve customer records in the CRM.
- Send follow-up emails after a conversation.

BOUNDARIES:
- Never make up information — if unsure, say you'll look into it and follow up.
- If the caller asks to speak to a human, acknowledge warmly and say you'll transfer them now.
- If a request is outside your capabilities, say so briefly and offer an alternative.

TOOL USE:
- Always use tools instead of guessing for facts, availability, or customer data.
- Chain tool calls when needed — look up a customer before creating a duplicate lead.
"""

TOOLS = [
    {
        "name": "book_appointment",
        "description": "Book a calendar appointment for the caller.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date":  {"type": "string", "description": "ISO 8601 date, e.g. 2026-06-10"},
                "time":  {"type": "string", "description": "24-hour time, e.g. 14:00"},
                "name":  {"type": "string", "description": "Caller full name"},
                "email": {"type": "string", "description": "Caller email (optional)"},
                "notes": {"type": "string", "description": "Reason for appointment (optional)"},
            },
            "required": ["date", "time", "name"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": "Search the company FAQ, product docs, and knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The caller's question or topic"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_crm_lead",
        "description": "Create a new lead or contact record in the CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":  {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "notes": {"type": "string", "description": "Call summary or reason for interest"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "lookup_customer",
        "description": "Look up an existing customer record by phone number or email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "email": {"type": "string"},
            },
        },
    },
    {
        "name": "send_followup_email",
        "description": "Send a follow-up email to the caller after the conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to":      {"type": "string", "description": "Recipient email address"},
                "summary": {"type": "string", "description": "Brief summary of what was discussed or agreed"},
            },
            "required": ["to", "summary"],
        },
    },
]
