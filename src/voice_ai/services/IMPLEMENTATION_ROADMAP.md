# Implementation Roadmap: Restaurant Reservation System

## Executive Summary

Adding 3 major features to the voice AI pipeline:
1. **📝 Lead Capture (Notepad)** - Capture structured reservation data
2. **🔍 RAG (Vector Search)** - Query availability, menu, policies
3. **🆘 Human Escalation** - Hand off to human agents when needed

All three integrate cleanly into the existing `VoiceSession` architecture.

---

## Current Architecture (What We Have)

```
VoiceSession (voice_session.py) - 486 lines
    │
    ├─→ STT (Deepgram Flux) - Continuous streaming, turn detection
    ├─→ LLM (OpenAI Responses API) - Conversation with streaming
    └─→ TTS (Deepgram Aura 2) - Sentence-by-sentence synthesis

States: idle → listening → processing → speaking
Interrupt handling: Epoch-based barge-in detection
Format handling: PCM 16kHz internally, μ-law for Twilio
```

**This is production-ready and works well.** We're adding features, not rewriting.

---

## New Architecture (What We're Building)

```
VoiceSession (Enhanced)
    │
    ├─→ STT (Deepgram) ──→ transcript
    │
    ├─→ 🆕 RAG Service
    │   ├─ Vector search (pgvector) - Menu, policies, FAQ
    │   └─ SQL queries - Availability, reservations
    │       │
    │       └─→ context (relevant facts)
    │
    ├─→ LLM (OpenAI + Function Calling) 🆕
    │   ├─ Context from RAG
    │   ├─ Function: capture_reservation_data() 🆕
    │   └─ Streams response + structured data
    │       │
    │       ├─→ text response ──→ TTS
    │       └─→ function_call ──→ 📝 Notepad 🆕
    │
    ├─→ 🆕 Escalation Manager
    │   └─ Detects: <ESCALATE>, incomplete data, user frustration
    │       └─→ Twilio <Dial> ──→ Human agent
    │
    ├─→ TTS (Deepgram)
    │
    └─→ 🆕 Session Storage
        └─ Saves: notepad, transcript, metadata
```

---

## Phase 1: Lead Capture (Notepad) ⭐ START HERE

**Goal:** Capture reservation details as user speaks

**Why first?** Foundation for RAG queries and escalation decisions.

### Changes to VoiceSession

**File:** `services/voice_session.py`

```python
class VoiceSession:
    def __init__(self, websocket: WebSocket):
        # ... existing ...

        # 🆕 NEW: Notepad for structured data capture
        self.notepad: dict[str, Any] = {}
        self.notepad_schema = RESERVATION_SCHEMA  # See below
        self.data_complete: bool = False
```

### New Provider Method (OpenAILLM)

**File:** `providers/llm/openai.py`

```python
class OpenAILLM:
    async def stream_complete(
        input: str,
        conversation_id: str,
        tools: list[dict] | None = None,  # 🆕 NEW
        context: dict | None = None       # 🆕 NEW (for RAG)
    ) -> AsyncIterator[LLMEvent]:
        """
        Stream LLM response with function calling support.

        Yields:
            LLMEvent - Either text_delta or function_call
        """

        response = await self.client.responses.create(
            conversation_id=conversation_id,
            input=input,
            tools=tools,  # Enable function calling
            additional_context=context  # Inject RAG results
        )

        async for event in response.stream():
            if event.type == "response.output_text.delta":
                yield LLMEvent(type="text", content=event.delta)

            elif event.type == "response.function_call":
                yield LLMEvent(
                    type="function_call",
                    name=event.name,
                    arguments=event.arguments
                )
```

### Update process_llm_and_tts()

**File:** `services/voice_session.py` (line ~289)

```python
async def process_llm_and_tts(self, user_input: str):
    # ... existing conversation_id creation ...

    # 🆕 Define function for data capture
    tools = [{
        "type": "function",
        "function": {
            "name": "capture_reservation_data",
            "description": "Capture reservation details from user",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "party_size": {"type": "integer", "minimum": 1},
                    "date": {"type": "string", "format": "date"},
                    "time": {"type": "string"},
                    "special_requests": {"type": "string"}
                }
            }
        }
    }]

    # Stream LLM with function calling enabled
    sentence_buffer = ""
    full_response = ""

    async for event in self.llm.stream_complete(
        input=user_input,
        conversation_id=self.conversation_id,
        tools=tools
    ):
        if event.type == "text":
            # Existing TTS logic
            sentence_buffer += event.content
            full_response += event.content
            # ... sentence boundary detection ...

        elif event.type == "function_call":
            # 🆕 NEW: Capture structured data
            data = json.loads(event.arguments)
            self.notepad.update(data)
            logger.info(f"📝 Notepad updated: {data}")

            # Check if all required fields captured
            self.data_complete = self._check_completeness()

            if self.data_complete:
                logger.info("✅ All required data captured!")
                # Could trigger reservation creation here
```

### Schema Definition

**File:** `models/schemas.py` (new file)

```python
from typing import TypedDict

class ReservationData(TypedDict, total=False):
    name: str
    phone: str
    email: str | None
    party_size: int
    date: str  # ISO format: YYYY-MM-DD
    time: str  # HH:MM
    special_requests: str | None

RESERVATION_SCHEMA = {
    "required_fields": ["name", "phone", "party_size", "date", "time"],
    "optional_fields": ["email", "special_requests"]
}
```

### Persistence on Session End

**File:** `services/voice_session.py` (line ~459)

```python
async def __aexit__(self, exc_type, exc_val, exc_tb):
    logger.info("Cleaning up voice session")

    # 🆕 NEW: Save notepad to database
    if self.notepad:
        from voice_ai.services.session_storage import SessionStorage
        storage = SessionStorage()

        await storage.save_session(
            conversation_id=self.conversation_id,
            notepad=self.notepad,
            metadata={
                "duration": time.time() - self._start_time,
                "data_complete": self.data_complete,
                "escalated": self.escalation_requested
            }
        )
        logger.info(f"💾 Notepad saved: {len(self.notepad)} fields")

    # ... existing STT cleanup ...
```

### New Service: SessionStorage

**File:** `services/session_storage.py` (new file)

```python
import asyncpg
from voice_ai.config import settings

class SessionStorage:
    """Persist voice session data to PostgreSQL."""

    def __init__(self):
        self.pool = None  # Connection pool

    async def save_session(
        self,
        conversation_id: str,
        notepad: dict,
        metadata: dict
    ) -> None:
        """Save session to database."""

        # TODO: Initialize pool if needed
        # For now, simple insert
        async with asyncpg.create_pool(settings.database_url) as pool:
            await pool.execute(
                """
                INSERT INTO voice_sessions (conversation_id, notepad, metadata)
                VALUES ($1, $2, $3)
                ON CONFLICT (conversation_id) DO UPDATE
                SET notepad = $2, metadata = $3, updated_at = NOW()
                """,
                conversation_id,
                json.dumps(notepad),
                json.dumps(metadata)
            )

    async def get_session(self, conversation_id: str) -> dict | None:
        """Retrieve session data."""
        # Implementation...
```

**Database Migration:**

```sql
CREATE TABLE voice_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT UNIQUE NOT NULL,
    notepad JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_notepad_phone ON voice_sessions ((notepad->>'phone'));
CREATE INDEX idx_created_at ON voice_sessions (created_at DESC);
```

**Phase 1 Complete:** Data capture working, persisted to DB.

---

## Phase 2: RAG Integration

**Goal:** Query availability, menu, policies from vector DB + SQL

**Why second?** Uses notepad data for smart queries.

### New Service: RAGService

**File:** `services/rag_service.py` (new file)

```python
from pgvector.asyncpg import register_vector
import asyncpg

class RAGService:
    """Retrieval-Augmented Generation for restaurant context."""

    async def get_context(self, query: str, notepad: dict) -> dict:
        """
        Get relevant context based on query + notepad.

        Returns dict with:
        - availability: List of available times/tables
        - menu_items: Relevant menu info
        - policies: Relevant policies
        """

        intent = self._classify_intent(query)

        if intent == "availability":
            return await self._get_availability(notepad)
        elif intent == "menu":
            return await self._search_menu(query)
        elif intent == "policy":
            return await self._search_policies(query)
        else:
            return await self._semantic_search(query)

    async def _get_availability(self, notepad: dict) -> dict:
        """SQL query for available tables."""
        date = notepad.get("date")
        party_size = notepad.get("party_size", 1)

        if not date:
            return {"message": "Which date are you interested in?"}

        # Query PostgreSQL
        async with asyncpg.create_pool(settings.database_url) as pool:
            slots = await pool.fetch(
                """
                SELECT time_slot, table_id, capacity
                FROM availability
                WHERE date = $1
                  AND capacity >= $2
                  AND status = 'available'
                ORDER BY time_slot
                """,
                date, party_size
            )

        return {
            "availability": [dict(s) for s in slots],
            "date": date,
            "party_size": party_size
        }

    async def _search_menu(self, query: str) -> dict:
        """Vector search menu items."""
        embedding = await self._embed(query)

        async with asyncpg.create_pool(settings.database_url) as pool:
            await register_vector(pool)

            results = await pool.fetch(
                """
                SELECT item_name, description, category
                FROM menu_embeddings
                ORDER BY embedding <=> $1
                LIMIT 5
                """,
                embedding
            )

        return {"menu_items": [dict(r) for r in results]}

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding via OpenAI."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI()

        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
```

### Integration in VoiceSession

**File:** `services/voice_session.py`

```python
class VoiceSession:
    def __init__(self, websocket: WebSocket):
        # ... existing ...
        self.rag = RAGService()  # 🆕 NEW

async def process_llm_and_tts(self, user_input: str):
    # ... existing ...

    # 🆕 Query RAG for context
    rag_context = await self.rag.get_context(
        query=user_input,
        notepad=self.notepad
    )

    # Pass context to LLM
    async for event in self.llm.stream_complete(
        input=user_input,
        conversation_id=self.conversation_id,
        tools=tools,
        context=rag_context  # 🆕 RAG results injected
    ):
        # ... existing logic ...
```

**Database Migrations:**

```sql
-- Availability table
CREATE TABLE availability (
    date DATE NOT NULL,
    time_slot TIME NOT NULL,
    table_id TEXT NOT NULL,
    capacity INT NOT NULL,
    status TEXT DEFAULT 'available',
    PRIMARY KEY (date, time_slot, table_id)
);

-- Menu embeddings (pgvector)
CREATE EXTENSION vector;

CREATE TABLE menu_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    embedding vector(1536)
);

CREATE INDEX idx_menu_embedding ON menu_embeddings
  USING ivfflat (embedding vector_cosine_ops);
```

**Phase 2 Complete:** AI has access to real-time availability + menu data.

---

## Phase 3: Human Escalation

**Goal:** Hand off to human agent when needed

**Why third?** Uses notepad + RAG context to inform agent.

### New Service: EscalationManager

**File:** `services/escalation_manager.py` (new file)

```python
class EscalationManager:
    """Manage human escalation requests."""

    async def request_escalation(
        self,
        session_id: str,
        reason: str,
        context: dict
    ) -> str:
        """
        Add session to escalation queue.

        Returns: queue_id
        """
        # In production: use Redis queue
        # For now: simple in-memory
        escalation = {
            "session_id": session_id,
            "reason": reason,
            "context": context,
            "requested_at": datetime.utcnow()
        }

        # Notify agents (webhook, websocket, etc.)
        await self._notify_agents(escalation)

        return f"queue:{session_id}"
```

### Integration in VoiceSession

**File:** `services/voice_session.py`

```python
class VoiceSession:
    def __init__(self, websocket: WebSocket):
        # ... existing ...
        self.escalation_mgr = EscalationManager()  # 🆕 NEW
        self.escalation_requested: bool = False

async def process_llm_and_tts(self, user_input: str):
    # ... after LLM streaming ...

    # 🆕 Check for escalation signals
    if "<ESCALATE>" in full_response:
        await self._handle_escalation()

    # 🆕 Or check if required data missing after N turns
    if self._turn_count > 5 and not self.data_complete:
        await self._handle_escalation(reason="missing_data")

async def _handle_escalation(self, reason: str = "user_requested"):
    """Request human escalation."""
    logger.info(f"🆘 Escalation: {reason}")

    self.escalation_requested = True

    # Add to queue with context
    await self.escalation_mgr.request_escalation(
        session_id=self.conversation_id,
        reason=reason,
        context={
            "notepad": self.notepad,
            "missing_fields": self._get_missing_fields(),
            "transcript": self._transcript
        }
    )

    # Inform user
    hold_msg = "Let me connect you with a team member. Please hold."
    await self._synthesize_hold_message(hold_msg)

    # Use Twilio to transfer
    await self._transfer_to_agent()

async def _transfer_to_agent(self):
    """Use Twilio <Dial> to transfer call."""
    from twilio.twiml.voice_response import VoiceResponse, Dial

    response = VoiceResponse()
    response.say("Transferring now.")

    dial = Dial(timeout=30)
    dial.number(settings.agent_phone_number)
    response.append(dial)

    # Send TwiML to Twilio (implementation depends on transport)
    # For Media Streams, might need to close WebSocket and use Twilio API
```

### Twilio Integration

**File:** `api/routes/voice_ws.py`

```python
@router.post("/escalation/transfer/{conversation_id}")
async def transfer_to_agent(conversation_id: str):
    """
    HTTP endpoint for Twilio to transfer call.

    Called when escalation requested during Media Streams.
    """
    from twilio.rest import Client

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    # Update ongoing call to transfer
    call = client.calls(conversation_id).update(
        twiml=f'<Response><Dial>{settings.agent_phone_number}</Dial></Response>'
    )

    return {"status": "transferred"}
```

**Phase 3 Complete:** Human escalation working with Twilio transfer.

---

## Testing Strategy

### Unit Tests

```python
# tests/test_notepad.py
async def test_function_calling_captures_data():
    """Test LLM function calling updates notepad."""
    session = VoiceSession(mock_websocket)
    await session.process_llm_and_tts("My name is John, party of 4")

    assert session.notepad["name"] == "John"
    assert session.notepad["party_size"] == 4

# tests/test_rag.py
async def test_availability_query():
    """Test RAG returns available times."""
    rag = RAGService()
    context = await rag.get_context(
        query="availability",
        notepad={"date": "2026-02-01", "party_size": 4}
    )

    assert "availability" in context
    assert len(context["availability"]) > 0

# tests/test_escalation.py
async def test_escalation_triggered():
    """Test escalation on incomplete data."""
    session = VoiceSession(mock_websocket)
    session._turn_count = 6
    session.data_complete = False

    await session.process_llm_and_tts("I don't know")

    assert session.escalation_requested is True
```

### Integration Tests

```python
# tests/test_full_flow.py
async def test_complete_reservation_flow():
    """
    Test full conversation: user makes reservation,
    data captured, availability checked, reservation created.
    """
    session = VoiceSession(mock_websocket)

    # Turn 1: User states intent
    await session.on_turn_end("I want to make a reservation")

    # Turn 2: Provide details
    await session.on_turn_end("John Smith, party of 4, Saturday at 7")

    # Turn 3: Phone number
    await session.on_turn_end("555-1234")

    # Verify notepad
    assert session.notepad["name"] == "John Smith"
    assert session.notepad["party_size"] == 4
    assert session.notepad["phone"] == "555-1234"
    assert session.data_complete is True

    # Verify reservation created in DB
    session_data = await SessionStorage().get_session(session.conversation_id)
    assert session_data["notepad"]["name"] == "John Smith"
```

---

## Deployment Checklist

### Environment Variables (add to .env)

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/voice_ai

# Twilio (for escalation)
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=xxxxx
AGENT_PHONE_NUMBER=+15551234567

# OpenAI (embeddings for RAG)
OPENAI_API_KEY=sk-xxxxx
```

### Database Setup

```bash
# Install pgvector extension
psql -d voice_ai -c "CREATE EXTENSION vector;"

# Run migrations
psql -d voice_ai < migrations/001_voice_sessions.sql
psql -d voice_ai < migrations/002_availability.sql
psql -d voice_ai < migrations/003_menu_embeddings.sql
```

### Seed Data

```python
# scripts/seed_menu.py
async def seed_menu():
    """Populate menu_embeddings table."""
    menu_items = [
        {"name": "Veggie Burger", "desc": "House-made patty with avocado", "cat": "entree"},
        {"name": "Caesar Salad", "desc": "Romaine, parmesan, croutons", "cat": "appetizer"},
        # ... more items ...
    ]

    for item in menu_items:
        embedding = await embed(f"{item['name']} {item['desc']}")
        await db.execute(
            "INSERT INTO menu_embeddings (item_name, description, category, embedding) VALUES ($1, $2, $3, $4)",
            item["name"], item["desc"], item["cat"], embedding
        )

# scripts/seed_availability.py
async def seed_availability():
    """Populate availability table."""
    dates = ["2026-02-01", "2026-02-02", ...]
    times = ["17:00", "17:30", "18:00", ...]
    tables = [{"id": "1", "cap": 2}, {"id": "2", "cap": 4}, ...]

    for date in dates:
        for time in times:
            for table in tables:
                await db.execute(
                    "INSERT INTO availability (date, time_slot, table_id, capacity, status) VALUES ($1, $2, $3, $4, 'available')",
                    date, time, table["id"], table["cap"]
                )
```

---

## Monitoring & Metrics

### Key Metrics to Track

1. **Notepad Metrics**
   - % of sessions with complete data
   - Average fields captured per turn
   - Most commonly missing field

2. **RAG Metrics**
   - Vector search latency (p50, p95, p99)
   - SQL query latency
   - Cache hit rate

3. **Escalation Metrics**
   - % of calls escalated
   - Escalation reasons (user_requested vs missing_data vs frustrated)
   - Time to agent pickup

4. **End-to-End Metrics**
   - Call completion rate (reservation created)
   - Average call duration
   - User satisfaction (post-call survey)

### Logging

```python
# Add to voice_session.py
logger.info(f"📝 Notepad: {self.notepad}")
logger.info(f"🔍 RAG latency: {rag_duration:.3f}s")
logger.info(f"🆘 Escalation: {reason}")
```

---

## Summary: What Gets Modified

### Modified Files (3)

1. **services/voice_session.py**
   - Add: `self.notepad`, `self.rag`, `self.escalation_mgr`
   - Modify: `process_llm_and_tts()` - add function calling + RAG + escalation
   - Modify: `__aexit__()` - persist notepad

2. **providers/llm/openai.py**
   - Add: `tools` parameter for function calling
   - Add: `context` parameter for RAG injection
   - Yield: `LLMEvent` (text or function_call)

3. **api/routes/voice_ws.py**
   - Add: `/escalation/transfer/{id}` endpoint

### New Files (5)

1. **services/rag_service.py** - Vector search + SQL queries
2. **services/escalation_manager.py** - Queue + agent assignment
3. **services/session_storage.py** - Persist to PostgreSQL
4. **models/schemas.py** - TypedDict for notepad data
5. **models/llm_events.py** - LLMEvent dataclass

### Database Migrations (3)

1. `voice_sessions` table - Persist notepad
2. `availability` table - Restaurant bookings
3. `menu_embeddings` table - Vector search (pgvector)

---

## Timeline Estimate

| Phase | Effort | Duration |
|-------|--------|----------|
| Phase 1: Notepad | Medium | 2-3 days |
| Phase 2: RAG | Medium | 2-3 days |
| Phase 3: Escalation | Small | 1-2 days |
| Testing | Medium | 2 days |
| **Total** | | **7-10 days** |

---

## Decision Log

### ✅ Use Function Calling (not separate extraction)
- **Reason:** Native OpenAI support, single LLM call, guaranteed JSON
- **Alternative:** Separate extraction LLM call (slower, more expensive)

### ✅ Use Twilio <Dial> for Escalation
- **Reason:** Simple, works with existing Twilio setup
- **Alternative:** WebSocket bridging (more complex, better UX)
- **Future:** Upgrade to WebSocket bridging for seamless handoff

### ✅ Use pgvector for Embeddings
- **Reason:** Single database, no external vector DB needed
- **Alternative:** Pinecone, Weaviate (adds dependency)

### ✅ RAG Context Injected via OpenAI API
- **Reason:** Responses API supports `additional_context`
- **Alternative:** Manually prepend to user message (less clean)

---

## Risk Mitigation

### Risk 1: LLM Doesn't Call Function
- **Mitigation:** Clear function descriptions, examples in system prompt
- **Fallback:** Parse text response for data (regex)

### Risk 2: RAG Latency
- **Mitigation:** Cache frequent queries (Redis), async parallel execution
- **Fallback:** Timeout after 2s, proceed without context

### Risk 3: Escalation Loop (user keeps getting transferred)
- **Mitigation:** Track escalation count per session, limit to 1 transfer
- **Fallback:** Offer callback instead

### Risk 4: pgvector Performance at Scale
- **Mitigation:** Proper indexes, query optimization, consider sharding
- **Fallback:** Migrate to dedicated vector DB (Pinecone) if needed

---

## Success Criteria

1. ✅ **Notepad:** 90%+ sessions capture all required fields
2. ✅ **RAG:** <500ms latency for availability queries
3. ✅ **Escalation:** <10% escalation rate, <30s wait time
4. ✅ **Overall:** 80%+ reservation completion rate

---

## Next Steps

1. **Review these 4 planning docs**
2. **Approve architecture**
3. **Start Phase 1: Implement notepad with function calling**
4. **Test thoroughly**
5. **Phase 2: Add RAG**
6. **Phase 3: Add escalation**

**All planning docs created:**
- `HUMAN_ESCALATION_PLAN.md`
- `LEAD_CAPTURE_PLAN.md`
- `RAG_INTEGRATION_PLAN.md`
- `IMPLEMENTATION_ROADMAP.md` (this file)

**Ready to build! 🚀**
