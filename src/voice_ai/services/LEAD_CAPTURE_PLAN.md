# Lead Capture / Notepad Architecture Plan

## Overview

The "notepad" feature captures structured data during conversations:
- **Restaurant Reservation Context:** Name, phone, party size, date/time, special requests
- **Lead Generation Context:** Email, company, pain points, budget
- **Support Context:** Issue description, account info, previous tickets

Think of it as the AI taking notes in real-time as the user speaks.

## Where It Fits in Current Architecture

```
VoiceSession (voice_session.py)
    │
    ├─→ STT ──→ transcript: "My name is John, party of 4"
    │
    ├─→ LLM ──→ response + STRUCTURED_DATA
    │               │
    │               └─→ {
    │                     "name": "John",
    │                     "party_size": 4
    │                   }
    │
    ├─→ 🆕 DataExtractor.extract_fields()
    │       - Parses LLM response
    │       - Updates session.notepad
    │       - Validates completeness
    │
    └─→ TTS ──→ "Perfect, John, party of 4. What date works for you?"
```

## Data Flow: Turn-by-Turn Capture

### Example Reservation Conversation

```
Turn 1:
User: "Hi, I'd like to make a reservation"
AI: "I'd be happy to help! What name should I put the reservation under?"
Notepad: {}

Turn 2:
User: "John Smith"
AI: "Great, John. How many people will be dining with you?"
Notepad: {
  "name": "John Smith"
}

Turn 3:
User: "Four people, for this Saturday at 7pm"
AI: "Perfect! Party of 4 this Saturday at 7pm. Can I get a phone number in case we need to reach you?"
Notepad: {
  "name": "John Smith",
  "party_size": 4,
  "date": "2026-02-01",  # Resolved "this Saturday"
  "time": "19:00"
}

Turn 4:
User: "555-1234"
AI: "Excellent! I have John Smith, party of 4, Saturday February 1st at 7pm. Phone: 555-1234. Should I confirm this reservation?"
Notepad: {
  "name": "John Smith",
  "party_size": 4,
  "date": "2026-02-01",
  "time": "19:00",
  "phone": "555-1234",
  "status": "pending_confirmation"
}
```

## Integration Points in VoiceSession

### 1. Add Notepad to VoiceSession State (line ~67)

```python
# Lead capture / notepad
self.notepad: dict[str, Any] = {}  # Captured structured data
self.notepad_schema: dict | None = None  # Expected fields for this conversation type
self.data_complete: bool = False  # All required fields captured
```

### 2. Inject DataExtractor

```python
def __init__(self, websocket: WebSocket):
    # ... existing code ...
    self.data_extractor = DataExtractor()  # NEW
```

### 3. Extract Data After LLM Response

**In `process_llm_and_tts()` (after LLM streaming, line ~423):**

```python
# After LLM completes
logger.info(f"← LLM: {chunk_count} chunks → {sentence_count} sentences")

# 🆕 Extract structured data from conversation turn
extracted = await self.data_extractor.extract_fields(
    user_input=user_input,
    ai_response=full_response,  # Need to capture this
    current_notepad=self.notepad
)

# Update notepad with new fields
if extracted:
    self.notepad.update(extracted)
    logger.info(f"📝 Notepad updated: {self.notepad}")

    # Check if all required fields captured
    if self.notepad_schema:
        self.data_complete = self._check_completeness()
```

### 4. Persist Notepad on Session End

**In `__aexit__()` (line ~459):**

```python
async def __aexit__(self, exc_type, exc_val, exc_tb):
    logger.info("Cleaning up voice session")

    # 🆕 Save notepad to database
    if self.notepad:
        await SessionStorage.save_session(
            conversation_id=self.conversation_id,
            notepad=self.notepad,
            transcript=self._get_full_transcript(),  # Optional
            metadata={
                "duration": self._duration,
                "turns": self._turn_count,
                "escalated": self.escalation_requested
            }
        )
        logger.info(f"💾 Notepad saved: {len(self.notepad)} fields")

    # ... existing cleanup code ...
```

## New Service: DataExtractor

**File:** `services/data_extractor.py`

### Responsibilities:
1. **Extract structured fields** from unstructured conversation
2. **Resolve ambiguity** (e.g., "this Saturday" → actual date)
3. **Validate format** (phone numbers, emails, dates)
4. **Incrementally build** notepad across turns

### Key Methods:

```python
async def extract_fields(
    user_input: str,
    ai_response: str,
    current_notepad: dict
) -> dict:
    """
    Extract new fields from latest conversation turn.

    Uses LLM to parse user input + AI response and identify:
    - What the user provided (name, date, etc.)
    - What was confirmed/clarified by AI

    Returns:
        Dict of newly captured fields to merge into notepad
    """

async def validate_field(field_name: str, value: Any) -> tuple[bool, Any]:
    """
    Validate and normalize a captured field.

    Examples:
    - "555-1234" → "+1-555-1234" (normalize)
    - "this Saturday" → "2026-02-01" (resolve relative date)
    - "john@example" → INVALID (incomplete email)
    """

def check_completeness(notepad: dict, schema: dict) -> bool:
    """
    Check if all required fields are captured.

    Schema example:
    {
        "name": {"required": True},
        "phone": {"required": True},
        "email": {"required": False},
        "party_size": {"required": True},
        "date": {"required": True}
    }
    """
```

## LLM Prompt Engineering for Data Extraction

### Approach 1: OpenAI Function Calling (Structured Outputs)

OpenAI's **Responses API** supports function calling. Define a schema:

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "capture_reservation_data",
            "description": "Capture reservation details from conversation",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "date": {"type": "string", "format": "date"},
                    "time": {"type": "string"},
                    "special_requests": {"type": "string"}
                },
                "required": ["name", "phone", "party_size", "date", "time"]
            }
        }
    }
]
```

LLM will automatically call this function with extracted data.

### Approach 2: Structured JSON in Response

Instruct LLM to include JSON in response:

```
System Prompt:
"After each user message, extract any reservation details and include them as JSON:

<DATA>
{
  "name": "John Smith",
  "party_size": 4
}
</DATA>

Only include fields the user explicitly mentioned this turn."
```

Then parse `<DATA>` tags in `process_llm_and_tts()`.

### Approach 3: Separate Extraction Call (Recommended)

After each turn, make a **second LLM call** dedicated to extraction:

```python
async def extract_fields(user_input, ai_response, current_notepad):
    prompt = f"""
    Analyze this conversation turn and extract structured data.

    User said: "{user_input}"
    AI responded: "{ai_response}"

    Current notepad: {json.dumps(current_notepad)}

    Extract any NEW fields the user provided (name, phone, email, party size, date, time, etc.).
    Resolve relative dates ("this Saturday" → actual date).
    Return ONLY new/updated fields as JSON.

    Output JSON only, no explanation.
    """

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",  # Cheap, fast
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)
```

**This approach is best because:**
- ✅ Doesn't slow down main LLM response (done in parallel with TTS)
- ✅ Can use cheaper model (gpt-4o-mini) for extraction
- ✅ Clean separation: main LLM focuses on conversation, extractor focuses on data
- ✅ Easy to debug/tune extraction without affecting conversation flow

## Notepad Schema per Conversation Type

### Restaurant Reservation Schema

```python
RESERVATION_SCHEMA = {
    "name": {"required": True, "type": "string"},
    "phone": {"required": True, "type": "string", "format": "phone"},
    "email": {"required": False, "type": "string", "format": "email"},
    "party_size": {"required": True, "type": "integer", "min": 1, "max": 20},
    "date": {"required": True, "type": "string", "format": "date"},
    "time": {"required": True, "type": "string", "format": "time"},
    "special_requests": {"required": False, "type": "string"},
    "high_chair_needed": {"required": False, "type": "boolean"},
    "dietary_restrictions": {"required": False, "type": "array"}
}
```

### Sales Lead Schema

```python
LEAD_SCHEMA = {
    "name": {"required": True, "type": "string"},
    "company": {"required": False, "type": "string"},
    "email": {"required": True, "type": "string", "format": "email"},
    "phone": {"required": False, "type": "string", "format": "phone"},
    "industry": {"required": False, "type": "string"},
    "company_size": {"required": False, "type": "string"},
    "pain_points": {"required": False, "type": "array"},
    "budget": {"required": False, "type": "string"},
    "timeline": {"required": False, "type": "string"}
}
```

### Setting Schema Dynamically

```python
# At session start, determine conversation type
if intent == "reservation":
    session.notepad_schema = RESERVATION_SCHEMA
elif intent == "lead_generation":
    session.notepad_schema = LEAD_SCHEMA
```

## Integration with RAG (Vector Search)

Notepad + RAG work together:

```
User: "Do you have availability for 6 people on Saturday?"
  ↓
1. Extract data: {"party_size": 6, "date": "2026-02-01"}
  ↓
2. RAG query: "SELECT * FROM availability WHERE date='2026-02-01' AND capacity >= 6"
  ↓
3. LLM context: "Available times: 6pm, 8pm, 9pm"
  ↓
4. LLM response: "We have tables for 6 available at 6pm, 8pm, or 9pm. Which works best?"
```

**RAG provides facts, Notepad captures user preferences.**

## New Service: SessionStorage

**File:** `services/session_storage.py`

### Responsibilities:
1. **Persist notepad** to database on session end
2. **Retrieve past sessions** by phone/email (returning customers)
3. **Export leads** to CRM (Salesforce, HubSpot)

### Key Methods:

```python
async def save_session(
    conversation_id: str,
    notepad: dict,
    transcript: str | None,
    metadata: dict
) -> None:
    """Save session data to PostgreSQL."""

async def get_session(conversation_id: str) -> dict:
    """Retrieve saved session data."""

async def find_customer(phone: str | None, email: str | None) -> list[dict]:
    """Find previous sessions for returning customer."""

async def export_to_crm(conversation_id: str) -> None:
    """Export lead data to external CRM."""
```

## Database Schema

### Table: `voice_sessions`

```sql
CREATE TABLE voice_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id TEXT UNIQUE NOT NULL,
  notepad JSONB NOT NULL,  -- Captured structured data
  transcript TEXT,  -- Full conversation (optional)
  metadata JSONB,  -- Duration, turns, escalated, etc.
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for searching
CREATE INDEX idx_notepad_name ON voice_sessions ((notepad->>'name'));
CREATE INDEX idx_notepad_phone ON voice_sessions ((notepad->>'phone'));
CREATE INDEX idx_notepad_email ON voice_sessions ((notepad->>'email'));
CREATE INDEX idx_created_at ON voice_sessions (created_at DESC);
```

## Real-Time Notepad Updates (Optional)

For debugging or dashboards, stream notepad updates to frontend:

```python
# In process_llm_and_tts() after updating notepad:
await self.websocket.send_json({
    "event": "notepad_update",
    "data": self.notepad
})
```

Frontend dashboard shows notepad filling in real-time during call.

## Validation & Error Handling

### Phone Number Validation

```python
import phonenumbers

def validate_phone(value: str) -> tuple[bool, str]:
    try:
        parsed = phonenumbers.parse(value, "US")
        if phonenumbers.is_valid_number(parsed):
            formatted = phonenumbers.format_number(
                parsed,
                phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            return True, formatted
        return False, value
    except:
        return False, value
```

### Date Resolution

```python
from dateutil.parser import parse as parse_date
from datetime import datetime, timedelta

def resolve_relative_date(text: str) -> str:
    """Convert 'this Saturday' → '2026-02-01'"""
    today = datetime.now()

    if "today" in text.lower():
        return today.strftime("%Y-%m-%d")
    elif "tomorrow" in text.lower():
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "saturday" in text.lower():
        # Find next Saturday
        days_ahead = 5 - today.weekday()  # Saturday is 5
        if days_ahead <= 0:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    else:
        # Try parsing absolute date
        try:
            parsed = parse_date(text)
            return parsed.strftime("%Y-%m-%d")
        except:
            return text  # Return as-is if can't parse
```

## Testing Scenarios

### Scenario 1: Complete Reservation

```
Turn 1: User: "I want to book a table"
        Notepad: {}

Turn 2: User: "John Smith, party of 4"
        Notepad: {"name": "John Smith", "party_size": 4}

Turn 3: User: "This Saturday at 7"
        Notepad: {..., "date": "2026-02-01", "time": "19:00"}

Turn 4: User: "555-1234"
        Notepad: {..., "phone": "+1-555-1234"}
        Status: COMPLETE ✅
```

### Scenario 2: Incomplete Data (Escalation Trigger)

```
Turn 1-5: User provides name, date, time but NO PHONE
Turn 6: AI: "I'll need a phone number to confirm"
Turn 7: User: "I don't want to give my number"
        → Escalation triggered (missing required field)
```

### Scenario 3: Returning Customer

```
Turn 1: User: "I want to make a reservation"
Turn 2: User: "555-1234"
        → System finds previous session with phone
        Notepad auto-filled: {
          "name": "John Smith",  # From previous visit
          "phone": "+1-555-1234"
        }
        AI: "Welcome back, John! What date works for you?"
```

## Performance Optimization

### Parallel Execution

```python
async def process_llm_and_tts(user_input: str):
    # Start extraction in parallel with TTS
    extraction_task = asyncio.create_task(
        self.data_extractor.extract_fields(...)
    )

    # ... TTS synthesis happens concurrently ...

    # Await extraction result when ready
    extracted = await extraction_task
    self.notepad.update(extracted)
```

**Result:** Zero latency added to user experience.

## Metrics to Track

1. **Capture Rate** - % of sessions with complete notepad
2. **Fields per Turn** - How many fields captured per interaction
3. **Validation Errors** - % of fields requiring correction
4. **Time to Complete** - Average turns to capture all required fields
5. **Abandonment** - % of calls dropped before notepad complete

## Integration with Human Escalation

When escalating, notepad is passed to human agent:

```python
await escalation_mgr.request_escalation(
    session_id=self.conversation_id,
    reason="missing_required_fields",
    context={
        "notepad": self.notepad,  # 👈 Give agent what we've captured
        "missing_fields": ["phone"],
        "transcript": self._transcript
    }
)
```

Agent sees: "John Smith, party of 4, Feb 1 @ 7pm. **Missing: Phone number**"

## Summary

**Notepad is the AI's memory:**
- Captures structured data turn-by-turn
- Validates and normalizes in real-time
- Persists to database on session end
- Powers RAG queries (availability checks)
- Enables returning customer recognition
- Handed to human agents on escalation

**Key Insight:** Use a **separate cheap LLM call** (gpt-4o-mini) for extraction after each turn. Runs in parallel with TTS, zero latency impact.

**Integration is clean:**
- VoiceSession gets `notepad` dict + `data_extractor`
- DataExtractor is standalone service (uses separate LLM)
- SessionStorage persists on `__aexit__()`
- Works seamlessly with RAG + Escalation
