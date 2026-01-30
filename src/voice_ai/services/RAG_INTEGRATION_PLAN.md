# RAG + Notepad + Escalation Integration Plan

## Complete Restaurant Reservation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                  TELEPHONE RESERVATION SYSTEM                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. User calls restaurant                                        │
│     ↓                                                            │
│  2. Twilio → WebSocket → VoiceSession starts                    │
│     ↓                                                            │
│  3. User: "I want a table for 4 on Saturday at 7pm"            │
│     ↓                                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ PARALLEL PROCESSING (all async)                         │   │
│  │                                                           │   │
│  │  A. 📝 NOTEPAD (Data Extraction)                        │   │
│  │     Extract: {                                            │   │
│  │       party_size: 4,                                      │   │
│  │       date: "2026-02-01",                                │   │
│  │       time: "19:00"                                       │   │
│  │     }                                                      │   │
│  │                                                           │   │
│  │  B. 🔍 RAG (Vector Search + DB Query)                    │   │
│  │     Query: "availability for 4 people on 2026-02-01"     │   │
│  │     Results: [                                            │   │
│  │       {time: "18:00", table: "5", capacity: 4},         │   │
│  │       {time: "19:00", table: "12", capacity: 6},        │   │
│  │       {time: "20:00", table: "8", capacity: 4}          │   │
│  │     ]                                                      │   │
│  │                                                           │   │
│  │  C. 💬 LLM (Response Generation)                         │   │
│  │     Context: Notepad + RAG results                        │   │
│  │     Response: "We have tables available at 6pm, 7pm,     │   │
│  │                or 8pm. The 7pm slot is perfect for 4!"   │   │
│  └─────────────────────────────────────────────────────────┘   │
│     ↓                                                            │
│  4. TTS speaks response to user                                 │
│     ↓                                                            │
│  5. User: "7pm works. My name is John Smith, 555-1234"        │
│     ↓                                                            │
│  6. Notepad updated: {name, phone, party_size, date, time}     │
│     ↓                                                            │
│  7. Check completeness: ALL REQUIRED FIELDS ✅                  │
│     ↓                                                            │
│  8. Create reservation in DB                                    │
│     ↓                                                            │
│  9. Send confirmation SMS (Twilio)                              │
│     ↓                                                            │
│  10. End call, persist session to DB                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Where RAG Fits in VoiceSession

### Integration Points

```python
class VoiceSession:
    def __init__(self, websocket: WebSocket):
        # ... existing ...
        self.llm = OpenAILLM()
        self.tts = DeepgramTTS()

        # 🆕 NEW SERVICES
        self.rag = RAGService()  # Vector search + context retrieval
        self.data_extractor = DataExtractor()  # Notepad capture
        self.escalation_mgr = EscalationManager()  # Human handoff

    async def process_llm_and_tts(self, user_input: str):
        # 1. Extract data from user input (parallel with RAG)
        extraction_task = asyncio.create_task(
            self.data_extractor.extract_fields(user_input, self.notepad)
        )

        # 2. Query RAG for relevant context
        rag_context = await self.rag.get_context(
            query=user_input,
            notepad=self.notepad  # Use captured data for smart queries
        )

        # 3. Wait for extraction to complete
        extracted = await extraction_task
        self.notepad.update(extracted)

        # 4. Build LLM context with RAG results + notepad
        llm_context = self._build_context(rag_context, self.notepad)

        # 5. Stream LLM response (with context)
        async for chunk in self.llm.stream_complete(
            input=user_input,
            conversation_id=self.conversation_id,
            context=llm_context  # RAG + notepad
        ):
            # ... existing TTS code ...
```

## RAG Service Architecture

### File: `services/rag_service.py`

```python
class RAGService:
    """
    Retrieval-Augmented Generation for voice AI.

    Combines:
    - Vector search (embeddings) for semantic similarity
    - SQL queries for structured data (availability, menu, etc.)
    - Business rules (minimum party size, blackout dates, etc.)
    """

    def __init__(self):
        self.vector_store = PgVectorStore()  # PostgreSQL with pgvector
        self.db = DatabaseClient()  # Structured queries

    async def get_context(self, query: str, notepad: dict) -> dict:
        """
        Get relevant context for LLM based on user query + notepad.

        Returns:
            {
                "availability": [...],  # Available tables/times
                "menu_items": [...],    # Relevant menu info
                "policies": [...],      # Cancellation, dress code, etc.
                "faq": [...]            # Similar questions
            }
        """

        # Determine what kind of information is needed
        intent = self._classify_intent(query)

        if intent == "availability_check":
            return await self._get_availability(notepad)

        elif intent == "menu_question":
            return await self._search_menu(query)

        elif intent == "policy_question":
            return await self._search_policies(query)

        else:
            # General semantic search
            return await self._semantic_search(query)

    async def _get_availability(self, notepad: dict) -> dict:
        """
        Query availability based on captured notepad data.

        SQL example:
        SELECT table_id, capacity, time_slot
        FROM availability
        WHERE date = %(date)s
          AND capacity >= %(party_size)s
          AND status = 'available'
        ORDER BY time_slot
        """

        party_size = notepad.get("party_size")
        date = notepad.get("date")

        if not date:
            # No date yet, return general availability
            return {"message": "Which date are you interested in?"}

        # Query database
        available_slots = await self.db.query(
            """
            SELECT time_slot, table_id, capacity
            FROM availability
            WHERE date = $1
              AND capacity >= $2
              AND status = 'available'
            ORDER BY time_slot
            """,
            date, party_size or 1
        )

        return {
            "availability": available_slots,
            "date": date,
            "party_size": party_size
        }

    async def _search_menu(self, query: str) -> dict:
        """
        Vector search through menu items.

        Example:
        Query: "Do you have vegetarian options?"
        → Finds: Veggie Burger, Garden Salad, Pasta Primavera
        """

        # Generate embedding for query
        query_embedding = await self._embed(query)

        # Cosine similarity search
        results = await self.vector_store.similarity_search(
            collection="menu_items",
            embedding=query_embedding,
            limit=5
        )

        return {
            "menu_items": [r["content"] for r in results],
            "relevance_scores": [r["score"] for r in results]
        }

    async def _search_policies(self, query: str) -> dict:
        """
        Vector search through restaurant policies.

        Example:
        Query: "What's your cancellation policy?"
        → Finds: "Free cancellation up to 2 hours before..."
        """

        query_embedding = await self._embed(query)

        results = await self.vector_store.similarity_search(
            collection="policies",
            embedding=query_embedding,
            limit=3
        )

        return {
            "policies": [r["content"] for r in results]
        }

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding using OpenAI."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
```

## Database Schema for RAG

### Table: `availability` (structured data)

```sql
CREATE TABLE availability (
  id UUID PRIMARY KEY,
  date DATE NOT NULL,
  time_slot TIME NOT NULL,
  table_id TEXT NOT NULL,
  capacity INT NOT NULL,
  status TEXT NOT NULL,  -- available|reserved|blocked
  UNIQUE(date, time_slot, table_id)
);

CREATE INDEX idx_availability_date ON availability(date);
CREATE INDEX idx_availability_status ON availability(status);
```

### Table: `menu_embeddings` (vector search)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE menu_embeddings (
  id UUID PRIMARY KEY,
  item_name TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL,  -- appetizer|entree|dessert
  tags TEXT[],  -- vegetarian, gluten-free, etc.
  embedding vector(1536),  -- OpenAI embedding dimension
  metadata JSONB
);

CREATE INDEX idx_menu_embedding ON menu_embeddings
  USING ivfflat (embedding vector_cosine_ops);
```

### Table: `policy_embeddings` (vector search)

```sql
CREATE TABLE policy_embeddings (
  id UUID PRIMARY KEY,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  category TEXT NOT NULL,  -- cancellation|dress_code|parking
  embedding vector(1536),
  metadata JSONB
);

CREATE INDEX idx_policy_embedding ON policy_embeddings
  USING ivfflat (embedding vector_cosine_ops);
```

## RAG Query Examples

### Example 1: Availability Check with Notepad

```python
User: "Do you have a table for 6 on Valentine's Day?"

# 1. Extract to notepad
notepad = {
    "party_size": 6,
    "date": "2026-02-14"
}

# 2. RAG availability query
rag_context = await rag.get_context(query, notepad)
# Returns:
{
    "availability": [
        {"time_slot": "17:00", "table_id": "10", "capacity": 8},
        {"time_slot": "21:00", "table_id": "15", "capacity": 6}
    ]
}

# 3. LLM response with context
"Yes! We have tables for 6 on Valentine's Day. We have availability at
5pm or 9pm. Which would you prefer?"
```

### Example 2: Menu Question (No Notepad Needed)

```python
User: "What vegetarian options do you have?"

# 1. Semantic vector search
rag_context = await rag._search_menu(query)
# Returns:
{
    "menu_items": [
        "Veggie Burger - house-made patty with avocado",
        "Garden Salad - seasonal vegetables, balsamic",
        "Pasta Primavera - fresh vegetables, marinara"
    ]
}

# 2. LLM response
"We have great vegetarian options! Our Veggie Burger features a
house-made patty with avocado, we have a Garden Salad with seasonal
vegetables, and Pasta Primavera with fresh vegetables and marinara."
```

### Example 3: Complex Query (RAG + Notepad)

```python
User: "Party of 8, need vegetarian options, this Saturday"

# 1. Extract to notepad
notepad = {
    "party_size": 8,
    "date": "2026-02-01",
    "dietary_restrictions": ["vegetarian"]
}

# 2. RAG queries (parallel)
availability = await rag._get_availability(notepad)
menu = await rag._search_menu("vegetarian options")

# 3. LLM synthesizes
"For a party of 8 this Saturday, we have tables at 6pm and 8pm.
For your vegetarian guests, we offer Veggie Burgers, Garden Salad,
and Pasta Primavera. Would you like me to reserve one of those times?"
```

---

## YOUR QUESTIONS ANSWERED

## Q1: Function Calling vs Separate Extraction?

### ✅ **USE FUNCTION CALLING (Structured Outputs)**

You're right! **OpenAI function calling is better** for GPT-4.1+ because:

**Advantages:**
1. ✅ **Native integration** - OpenAI handles extraction automatically
2. ✅ **Guaranteed JSON** - No parsing errors
3. ✅ **Single LLM call** - Extraction happens during main response
4. ✅ **Schema enforcement** - Types validated by OpenAI
5. ✅ **No separate model** - Cheaper (1 call instead of 2)

### Revised Implementation with Function Calling

```python
# In OpenAILLM provider
async def stream_complete(
    input: str,
    conversation_id: str,
    tools: list[dict] | None = None  # 🆕 NEW
) -> AsyncIterator[str]:
    """Stream LLM response with optional function calling."""

    # Define reservation capture function
    reservation_tool = {
        "type": "function",
        "function": {
            "name": "capture_reservation_data",
            "description": "Capture reservation details from user",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "party_size": {"type": "integer", "minimum": 1},
                    "date": {"type": "string", "format": "date"},
                    "time": {"type": "string"},
                    "special_requests": {"type": "string"}
                }
            }
        }
    }

    response = await self.client.responses.create(
        conversation_id=conversation_id,
        input=input,
        tools=[reservation_tool],  # 👈 Enable function calling
        tool_choice="auto"  # Let model decide when to call
    )

    # Model will call capture_reservation_data() automatically
    # and include structured data in response
```

### In VoiceSession:

```python
async def process_llm_and_tts(self, user_input: str):
    # Define tools for this turn
    tools = [self._get_reservation_tool()]

    async for event in self.llm.stream_complete(
        input=user_input,
        conversation_id=self.conversation_id,
        tools=tools
    ):
        # Check for function call
        if event.type == "function_call":
            # Extract structured data
            data = json.loads(event.arguments)
            self.notepad.update(data)
            logger.info(f"📝 Function call captured: {data}")

        elif event.type == "text_delta":
            # Regular text streaming
            sentence_buffer += event.text
            # ... TTS logic ...
```

**Verdict: Use function calling for notepad extraction. It's cleaner and more reliable.**

---

## Q2: Does Twilio Support Easy Escalation?

### ✅ **YES! Twilio has native escalation features**

### Option 1: Transfer to Human Agent (Direct)

```python
# When escalation requested, use Twilio's <Dial> verb
from twilio.twiml.voice_response import VoiceResponse, Dial

async def handle_escalation(session: VoiceSession):
    """Transfer call to human agent."""

    # Stop AI processing
    session.state = "escalated"

    # Create TwiML to transfer call
    response = VoiceResponse()
    response.say("Let me connect you with a team member.")

    # Dial agent's phone number
    dial = Dial(
        action="/escalation/complete",  # Webhook when call ends
        timeout=30,
        caller_id="+1234567890"  # Restaurant's number
    )
    dial.number(
        "+1555AGENT01",  # Agent's phone
        status_callback_event=["initiated", "answered"],
        status_callback="/escalation/status"
    )
    response.append(dial)

    # Send TwiML to Twilio
    await session.websocket.send_text(
        json.dumps({
            "event": "transfer",
            "twiml": str(response)
        })
    )
```

### Option 2: Queue with Hold Music

```python
response = VoiceResponse()
response.say("Please hold while I connect you.")

# Add to Twilio queue
response.enqueue(
    "support_queue",
    wait_url="http://your-server.com/hold-music.xml",
    wait_url_method="GET"
)
```

Agents use Twilio's **TaskRouter** to pull from queue.

### Option 3: Hybrid (AI + Human Together)

**Most sophisticated:** Keep WebSocket open, add agent as 3rd party:

```python
# 1. User still connected via WebSocket
# 2. Agent joins via separate WebSocket: /ws/agent/{session_id}
# 3. Both user and agent hear each other
# 4. AI can optionally chime in with suggestions to agent
```

**This is the best approach** because:
- ✅ Seamless handoff (no transfer clicks)
- ✅ AI can whisper suggestions to agent (not heard by user)
- ✅ Agent sees full notepad + conversation history
- ✅ Agent can hand back to AI if they resolve blocker

### Twilio Features for Escalation:

| Feature | Use Case |
|---------|----------|
| `<Dial>` | Direct transfer to agent phone |
| `<Queue>` | Hold with music, FIFO agent assignment |
| `<Conference>` | Multi-party calls (user + agent + supervisor) |
| TaskRouter | Intelligent routing (by skill, availability) |
| Media Streams | Keep WebSocket open during escalation |

**Verdict: Twilio makes escalation easy. Use `<Dial>` for simple cases, WebSocket bridging for sophisticated handoff.**

---

## Complete Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FULL SYSTEM ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Twilio Call ──→ WebSocket (/ws/twilio)                         │
│                      │                                            │
│                      ↓                                            │
│  ┌─────────────────────────────────────────────────────┐        │
│  │              VoiceSession                            │        │
│  │                                                       │        │
│  │  State: idle → listening → processing → speaking     │        │
│  │                      ↓                                │        │
│  │         ┌─────────────────────────┐                 │        │
│  │         │   STT (Deepgram Flux)   │                 │        │
│  │         │   - Continuous streaming │                 │        │
│  │         │   - Turn detection       │                 │        │
│  │         └──────────┬──────────────┘                 │        │
│  │                    │ transcript                      │        │
│  │                    ↓                                 │        │
│  │         ┌─────────────────────────┐                 │        │
│  │         │   🔍 RAG Service         │                 │        │
│  │         │   - Vector search        │                 │        │
│  │         │   - Availability DB      │                 │        │
│  │         │   - Menu/Policy search   │                 │        │
│  │         └──────────┬──────────────┘                 │        │
│  │                    │ context                         │        │
│  │                    ↓                                 │        │
│  │         ┌─────────────────────────┐                 │        │
│  │         │   💬 LLM (OpenAI)        │                 │        │
│  │         │   + Function Calling     │◄────────┐      │        │
│  │         │   + Streaming responses  │         │      │        │
│  │         └──────────┬──────────────┘         │      │        │
│  │                    │                          │      │        │
│  │         ┌──────────┴──────────┐              │      │        │
│  │         │                     │              │      │        │
│  │         ↓                     ↓              │      │        │
│  │    text response      📝 function_call      │      │        │
│  │         │               (notepad data)       │      │        │
│  │         │                     │              │      │        │
│  │         │                     └──────────────┘      │        │
│  │         │                       update notepad      │        │
│  │         │                                            │        │
│  │         ↓                                            │        │
│  │  Check for:                                         │        │
│  │  • <ESCALATE> tag? ──→ 🆘 EscalationManager        │        │
│  │  • Data complete?  ──→ ✅ Create reservation       │        │
│  │  • Need more info? ──→ 🔄 Continue conversation    │        │
│  │         │                                            │        │
│  │         ↓                                            │        │
│  │  ┌─────────────────────────┐                       │        │
│  │  │  🔊 TTS (Deepgram Aura)  │                       │        │
│  │  │  - Sentence buffering    │                       │        │
│  │  │  - Epoch-based dropping  │                       │        │
│  │  └──────────┬──────────────┘                       │        │
│  │             │ PCM audio                              │        │
│  └─────────────┼────────────────────────────────────────┘        │
│                ↓                                                  │
│  Audio → Twilio → User's Phone                                  │
│                                                                   │
│  On Session End:                                                 │
│    💾 SessionStorage.save_session()                              │
│       - Persist notepad to PostgreSQL                            │
│       - Export to CRM if lead                                    │
│       - Send confirmation SMS                                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Summary & Recommendations

### ✅ Use Function Calling (not separate extraction)
- GPT-4.1 function calling is faster, cheaper, more reliable
- One LLM call instead of two
- Guaranteed JSON schema

### ✅ Twilio Escalation is Easy
- Use `<Dial>` for simple transfer
- Use WebSocket bridging for sophisticated handoff
- Use `<Queue>` + TaskRouter for enterprise setup

### ✅ RAG + Notepad Work Together
- RAG provides **facts** (availability, menu, policies)
- Notepad captures **user preferences** (name, date, size)
- LLM synthesizes **personalized response** from both

### ✅ All Three Features Integrate Cleanly
1. **Notepad** - Captures data via function calling (automatic)
2. **RAG** - Queries context based on notepad + user input
3. **Escalation** - Triggers when data incomplete or user requests

### Next Steps (Implementation Order)

1. **First:** Add function calling to OpenAILLM for notepad capture
2. **Second:** Build RAGService with PgVector for menu/availability
3. **Third:** Add EscalationManager with Twilio `<Dial>` integration
4. **Fourth:** Tie it all together in VoiceSession.process_llm_and_tts()

Clean, modular, production-ready. 🚀
