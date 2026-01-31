# Reservation Agent Implementation: Complete Technical Guide

**From Database to Function Calling - A Deep Dive**

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Layer](#database-layer)
3. [Session Management & The Connection Leak](#session-management)
4. [Tool Functions](#tool-functions)
5. [Reservation Agent with Function Calling](#reservation-agent)
6. [Test Script Execution Flow](#test-script-execution-flow)
7. [The Bug & The Fix](#the-bug--the-fix)
8. [Complete Execution Trace](#complete-execution-trace)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TEST SCRIPT                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │   TEST 1     │  │   TEST 2     │  │   TEST 3     │                       │
│  │  Check Room  │  │   Create     │  │   Check      │                       │
│  │ Availability │──│ Reservation  │──│   Status     │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
│         │                 │                 │                               │
│         └─────────────────┴─────────────────┘                               │
│                           │                                                  │
│                    ┌─────────────┐                                           │
│                    │ ToolRegistry│                                           │
│                    │  - session  │                                           │
│                    │  - sync_svc │                                           │
│                    └──────┬──────┘                                           │
│                           │                                                  │
└───────────────────────────┼──────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────────────────────────┐
│                    ┌──────▼──────┐                                           │
│                    │   Agent     │                                           │
│                    │  OpenAI LLM │                                           │
│                    │ + Functions │                                           │
│                    └──────┬──────┘                                           │
│                           │                                                  │
│              ┌────────────┼────────────┐                                     │
│              ▼            ▼            ▼                                     │
│        ┌─────────┐  ┌─────────┐  ┌─────────┐                                │
│        │  query  │  │ create  │  │  check  │                                │
│        │inventory│  │ ticket  │  │ status  │                                │
│        └────┬────┘  └────┬────┘  └────┬────┘                                │
│             │            │            │                                      │
└─────────────┼────────────┼────────────┼──────────────────────────────────────┘
              │            │            │
┌─────────────┼────────────┼────────────┼──────────────────────────────────────┐
│             ▼            ▼            ▼                                      │
│        ┌─────────────────────────────────────┐                               │
│        │      PostgreSQL (asyncpg)           │                               │
│        │  ┌──────────────┐  ┌──────────────┐ │                               │
│        │  │ShadowInventory│  │ReservationTicket│                             │
│        │  └──────────────┘  └──────────────┘ │                               │
│        └─────────────────────────────────────┘                               │
│                                                                              │
│  CONNECTION POOL (SQLAlchemy)                                                │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                                │
│  │Conn 1  │ │Conn 2  │ │Conn 3  │ │Conn 4  │ ...                             │
│  │(in use)│ │(avail) │ │(avail) │ │(avail) │                                │
│  └────────┘ └────────┘ └────────┘ └────────┘                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Layer

### 1. Database Engine Configuration (`src/reservation/db.py`)

```python
"""Database connection and session management."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Use async PostgreSQL driver (asyncpg)
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://lotus:lotus@localhost:5432/blacklotus"
)

# Engine: Manages the connection pool
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True for SQL logging
    future=True
)

# Session factory: Creates AsyncSession instances
async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False  # Keep objects usable after commit
)
```

**Key Concepts:**

| Component | Purpose |
|-----------|---------|
| `create_async_engine` | Creates connection pool to PostgreSQL |
| `sessionmaker` | Factory for creating session objects |
| `expire_on_commit=False` | Objects remain attached after commit (prevents lazy-loading errors) |

### 2. Connection Pool Mechanics

```
┌─────────────────────────────────────────────────────────────┐
│                    SQLAlchemy Engine                        │
│                   (Connection Pool)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────────┐                                         │
│   │  Application │                                         │
│   └──────┬───────┘                                         │
│          │ "I need a session"                              │
│          ▼                                                 │
│   ┌──────────────┐                                         │
│   │ async_session│  ◄─── Creates AsyncSession wrapper      │
│   └──────┬───────┘                                         │
│          │ "Checkout connection from pool"                  │
│          ▼                                                 │
│   ┌─────────────────────────────────────────┐               │
│   │           Connection Pool               │               │
│   │  ┌────────┐┌────────┐┌────────┐        │               │
│   │  │  FREE  ││  FREE  ││ IN USE │        │               │
│   │  │   ○    ││   ○    ││   ●    │        │               │
│   │  └────────┘└────────┘└────┬───┘        │               │
│   │           └───────────────┘             │               │
│   │              Checkout given to          │               │
│   │              AsyncSession               │               │
│   └─────────────────────────────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. Session Lifecycle (The Problem Area)

#### Original Buggy Code:

```python
# src/reservation/db.py
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes."""
    async with async_session() as session:
        yield session
    # Session closes here when generator exits normally
```

**The Bug in `scripts/test_agent_tools.py`:**

```python
class ToolRegistry:
    async def setup(self):
        await init_db()
        
        # ❌ BUG: Using 'break' exits generator without cleanup!
        async for session in get_session():
            self.session = session
            break  # Generator never completes, session stays "checked out"
```

**What Happens:**

```
Step 1: async for session in get_session()
        │
        └── Calls get_session() generator
            └── async with async_session() as session
                └── Checks out Connection #1 from pool
                    └── yield session  ←── Returns to caller

Step 2: self.session = session  ←── Stores reference

Step 3: break  ←── ABRUPT EXIT!
        │
        └── Generator is suspended, not closed
        └── async with block never exits
        └── Connection #1 stays "checked out"
        └── Marked as "in use" in pool

Step 4: Tests run using the same session...

Step 5: await close_db() / engine.dispose()
        │
        └── Tries to close all connections
        └── Connection #1 is still "checked out"
        └── Can't return it to pool properly

Step 6: Event loop closes
        │
        └── Garbage collector finds leaked connection
        └── Tries to force-close it
        └── ⚠️ RuntimeError: Event loop is closed
        └── ⚠️ SAWarning: non-checked-in connection
```

---

## Session Management

### The Fix: Explicit Session Lifecycle

```python
class ToolRegistry:
    def __init__(self):
        self.session = None
        self.sync_service = None
        
    async def setup(self):
        """Initialize DB and create session."""
        await init_db()
        
        # ✅ FIX: Create session directly, no generator
        self.session = async_session()
        await self.session.__aenter__()  # Explicitly enter context
        
        erp_client = MockERPClient(failure_rate=0.0)
        self.sync_service = ERPSyncService(erp_client)
        
    async def teardown(self):
        """Close session and cleanup."""
        if self.session:
            # ✅ FIX: Explicitly exit context
            await self.session.__aexit__(None, None, None)
            self.session = None
        await close_db()
```

**Usage with Guaranteed Cleanup:**

```python
async def test_conversation():
    registry = ToolRegistry()
    await registry.setup()
    
    try:
        # ... run tests ...
        pass
    finally:
        # ✅ Always runs, even if exception occurs
        await registry.teardown()
```

### Comparison: Before vs After

| Aspect | Before (Buggy) | After (Fixed) |
|--------|---------------|---------------|
| Session creation | `async for ... break` | `async_session()` + `__aenter__()` |
| Session storage | Reference to "open" generator | Direct session object |
| Cleanup | None (leaked) | `__aexit__()` in `finally` block |
| On exception | Worse leak | Still cleaned up |
| Pool state | Connection stuck "in use" | Connection returned properly |

---

## Tool Functions

### 1. `query_room_inventory()`

**Purpose:** Check room availability for given dates

```python
async def query_room_inventory(
    session: AsyncSession,
    check_in: str,
    check_out: str,
    guests: int,
    sync_service: ERPSyncService
) -> dict:
    """
    Check room availability from shadow database.
    
    Flow:
    1. Parse dates and calculate nights
    2. Check cache freshness (last ERP sync)
    3. Query ShadowInventory for each room type
    4. Return formatted response for LLM
    """
    check_in_date = date.fromisoformat(check_in)
    check_out_date = date.fromisoformat(check_out)
    nights = (check_out_date - check_in_date).days
    
    # Check cache freshness
    last_sync = await sync_service.get_last_sync(session)
    cache_fresh = sync_service.is_cache_fresh(last_sync, max_age_minutes=120)
    
    available_rooms = []
    
    for room_type in RoomType:
        # Query: Find available inventory for ALL nights in range
        result = await session.execute(
            select(ShadowInventory).where(
                and_(
                    ShadowInventory.room_type == room_type,
                    ShadowInventory.date >= check_in_date,
                    ShadowInventory.date < check_out_date,
                    ShadowInventory.is_available == True
                )
            )
        )
        inventory_items = result.scalars().all()
        
        # Room available only if inventory exists for EVERY night
        if len(inventory_items) == nights:
            avg_rate = sum(item.rate for item in inventory_items) / nights
            total = sum(item.rate for item in inventory_items)
            
            available_rooms.append({
                "room_type": room_type.value,
                "rate_per_night": round(avg_rate, 2),
                "total_estimate": round(total, 2),
                "amenities": _get_amenities(room_type)
            })
    
    return {
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "available_rooms": available_rooms,
        "cache_info": {
            "fresh": cache_fresh,
            "warning": None if cache_fresh else "Data may be stale"
        }
    }
```

**SQL Generated:**

```sql
SELECT shadow_inventory.id, shadow_inventory.room_type, 
       shadow_inventory.date, shadow_inventory.is_available, 
       shadow_inventory.rate, shadow_inventory.last_synced
FROM shadow_inventory
WHERE shadow_inventory.room_type = 'DELUXE'
  AND shadow_inventory.date >= '2026-02-07'
  AND shadow_inventory.date < '2026-02-10'
  AND shadow_inventory.is_available = TRUE
```

### 2. `create_reservation_ticket()`

**Purpose:** Create a pending ticket for human staff review

```python
async def create_reservation_ticket(
    session: AsyncSession,
    guest_name: str,
    phone_number: str,
    check_in: str,
    check_out: str,
    room_type: str,
    guests: int,
    special_requests: str = "",
    call_transcript: str = ""
) -> dict:
    """
    Create a ticket for human staff review.
    
    THE BUG (Fixed):
    ----------------
    Original code:
        result = await session.execute(
            select(ReservationTicket).order_by(ReservationTicket.id.desc())
        )
        last_ticket = result.scalar_one_or_none()  # ❌ FAILS if >1 row!
    
    Problem:
        - Query returns ALL tickets (no LIMIT)
        - scalar_one_or_none() expects 0 or 1 rows
        - If database has multiple tickets: raises exception
    
    Fix:
        - Added .limit(1) to query
    
    Correct code:
        result = await session.execute(
            select(ReservationTicket)
            .order_by(ReservationTicket.id.desc())
            .limit(1)  # ✅ Now returns max 1 row
        )
    """
    # Generate sequential ticket ID (LOTUS-0001, LOTUS-0002, etc.)
    result = await session.execute(
        select(ReservationTicket)
        .order_by(ReservationTicket.id.desc())
        .limit(1)  # ✅ THE FIX
    )
    last_ticket = result.scalar_one_or_none()
    next_num = 1 if not last_ticket else last_ticket.id + 1
    ticket_id = f"LOTUS-{next_num:04d}"
    
    # Create ticket object
    ticket = ReservationTicket(
        ticket_id=ticket_id,
        guest_name=guest_name,
        phone_number=phone_number,
        check_in=date.fromisoformat(check_in),
        check_out=date.fromisoformat(check_out),
        room_type=room_type,
        guests=guests,
        special_requests=special_requests or None,
        call_transcript=call_transcript or None,
        status=TicketStatus.PENDING
    )
    
    # Save to database
    session.add(ticket)
    await session.commit()  # Generates INSERT SQL
    
    return {
        "ticket_id": ticket_id,
        "status": "pending",
        "message": f"Thank you {guest_name}! I've submitted your reservation...",
        "expected_response_time": "30 minutes"
    }
```

**SQL Generated:**

```sql
-- Get last ticket ID
SELECT reservation_ticket.id, reservation_ticket.ticket_id, ...
FROM reservation_ticket
ORDER BY reservation_ticket.id DESC
LIMIT 1

-- Insert new ticket
INSERT INTO reservation_ticket (
    ticket_id, guest_name, phone_number, check_in, check_out,
    room_type, guests, special_requests, call_transcript, status
) VALUES (
    'LOTUS-0002', 'John Doe', '+1-555-123-4567',
    '2026-02-07', '2026-02-10', 'deluxe', 2, NULL, '[Test]', 'pending'
)
```

### 3. `check_ticket_status()`

**Purpose:** Lookup existing reservation by ticket ID

```python
async def check_ticket_status(session: AsyncSession, ticket_id: str) -> dict:
    """Check status of an existing ticket."""
    result = await session.execute(
        select(ReservationTicket)
        .where(ReservationTicket.ticket_id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        return {
            "found": False,
            "message": f"I couldn't find a ticket with ID {ticket_id}."
        }
    
    return {
        "found": True,
        "ticket_id": ticket.ticket_id,
        "status": ticket.status.value,
        "guest_name": ticket.guest_name,
        "check_in": ticket.check_in.isoformat(),
        "check_out": ticket.check_out.isoformat(),
        "room_type": ticket.room_type.value,
        "message": status_messages.get(ticket.status, "Status unknown.")
    }
```

---

## Reservation Agent

### OpenAI Function Calling Architecture

```python
class ReservationAgent:
    """
    Agent that handles reservation conversations with database tool use.
    
    Uses OpenAI Responses API with function calling:
    1. Define tools (schemas)
    2. Send user input + tools to model
    3. Model decides which tools to call
    4. Execute function calls
    5. Return results to model
    6. Model generates final response
    """
    
    def __init__(self):
        self.llm = OpenAILLM()
        self.tools: dict[str, Callable] = {}
        
    def register_tool(self, name: str, handler: Callable):
        """Register a tool handler function."""
        self.tools[name] = handler
```

### Tool Schemas

```python
TOOLS = [
    {
        "type": "function",
        "name": "query_room_inventory",
        "description": "Check room availability for given dates...",
        "parameters": {
            "type": "object",
            "properties": {
                "check_in": {
                    "type": "string",
                    "description": "Check-in date in YYYY-MM-DD format"
                },
                "check_out": {
                    "type": "string", 
                    "description": "Check-out date in YYYY-MM-DD format"
                },
                "guests": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4
                }
            },
            "required": ["check_in", "check_out", "guests"]
        }
    },
    # ... similar for create_reservation_ticket and check_ticket_status
]
```

### Two-Step Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FUNCTION CALLING FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: Send user message + tools                                          │
│  ═══════════════════════════════════                                        │
│                                                                             │
│  Input: "What rooms available Feb 7-10 for 2 guests?"                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ POST /v1/responses                                                  │    │
│  │ {                                                                   │    │
│  │   "model": "gpt-4o",                                                │    │
│  │   "input": [                                                        │    │
│  │     {"role": "system", "content": "You are a hotel assistant..."},  │    │
│  │     {"role": "user", "content": "What rooms available..."}          │    │
│  │   ],                                                                │    │
│  │   "tools": ["query_room_inventory", "create_reservation_ticket",    │    │
│  │              "check_ticket_status"]                                  │    │
│  │ }                                                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ OpenAI Model Decision                                               │    │
│  │                                                                     │    │
│  │ User wants to check availability → Need to call                     │    │
│  │ query_room_inventory with:                                          │    │
│  │   - check_in: "2026-02-07"                                          │    │
│  │   - check_out: "2026-02-10"                                         │    │
│  │   - guests: 2                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                            │                                                │
│                            ▼                                                │
│  Response from API:                                                         │
│  {                                                                          │
│    "output": [                                                              │
│      {                                                                      │
│        "type": "function_call",                                             │
│        "call_id": "call_abc123",                                            │
│        "name": "query_room_inventory",                                      │
│        "arguments": '{"check_in":"2026-02-07",                             │
│                      "check_out":"2026-02-10","guests":2}'                 │
│      }                                                                      │
│    ]                                                                        │
│  }                                                                          │
│                            │                                                │
├────────────────────────────┼────────────────────────────────────────────────┤
│                            │                                                │
│  STEP 2: Execute function call                                              │
│  ═══════════════════════════                                                │
│                            │                                                │
│                            ▼                                                │
│  Parse arguments: json.loads(call.arguments)                                │
│                            │                                                │
│                            ▼                                                │
│  Execute: await query_room_inventory(                                       │
│               session=registry.session,                                     │
│               check_in="2026-02-07",                                        │
│               check_out="2026-02-10",                                       │
│               guests=2,                                                     │
│               sync_service=registry.sync_service                            │
│           )                                                                 │
│                            │                                                │
│                            ▼                                                │
│  Result: {                                                                  │
│    "available_rooms": [                                                     │
│      {"room_type": "standard", "rate_per_night": 161.67, ...},             │
│      {"room_type": "deluxe", "rate_per_night": 239.67, ...},               │
│      {"room_type": "suite", "rate_per_night": 422.67, ...}                 │
│    ]                                                                        │
│  }                                                                          │
│                            │                                                │
├────────────────────────────┼────────────────────────────────────────────────┤
│                            │                                                │
│  STEP 3: Send results back to model                                         │
│  ══════════════════════════════════                                         │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ POST /v1/responses (continuation)                                   │    │
│  │ {                                                                   │    │
│  │   "input": [                                                        │    │
│  │     {                                                               │    │
│  │       "type": "function_call",                                      │    │
│  │       "call_id": "call_abc123",                                     │    │
│  │       "name": "query_room_inventory",                               │    │
│  │       "arguments": "..."                                            │    │
│  │     },                                                              │    │
│  │     {                                                               │    │
│  │       "type": "function_call_output",                               │    │
│  │       "call_id": "call_abc123",                                     │    │
│  │       "output": '{"available_rooms":[...]}'                         │    │
│  │     }                                                               │    │
│  │   ]                                                                 │    │
│  │ }                                                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                            │                                                │
│                            ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Model generates final response using tool results                   │    │
│  │                                                                     │    │
│  │ "I found availability for Feb 7–10...                              │    │
│  │  Standard — $161.67 per night...                                    │    │
│  │  Deluxe — $239.67 per night..."                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Test Script Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TEST_CONVERSATION() FLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. SETUP                                                                   │
│  ═══════                                                                    │
│  registry = ToolRegistry()                                                  │
│  await registry.setup()                                                     │
│       │                                                                     │
│       ├── await init_db()                      ──► Create tables if needed  │
│       ├── self.session = async_session()       ──► Create session object    │
│       ├── await self.session.__aenter__()      ──► Checkout connection      │
│       └── Setup ERP sync service                                            │
│       │                                                                     │
│       └── Print: "✓ Database connected (using pre-seeded data)"            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  2. INITIALIZE AGENT                                                        │
│  ═══════════════════                                                        │
│  agent = ReservationAgent()                                                 │
│  await agent.initialize()                                                   │
│       │                                                                     │
│       └── Create OpenAI conversation                                        │
│                                                                             │
│  agent.register_tool("query_room_inventory", registry.query_room_inventory) │
│  agent.register_tool("create_reservation_ticket", ...)                      │
│  agent.register_tool("check_ticket_status", ...)                            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  3. TEST 1: CHECK AVAILABILITY                                              │
│  ═════════════════════════════                                              │
│  User: "What rooms do you have available from 2026-02-07 to 2026-02-10..."  │
│       │                                                                     │
│       ├──► OpenAI: Decides to call query_room_inventory                     │
│       │         check_in="2026-02-07", check_out="2026-02-10", guests=2    │
│       │                                                                     │
│       ├──► Execute: await registry.query_room_inventory(...)                │
│       │         └── SQL query to ShadowInventory table                      │
│       │         └── Returns available rooms list                            │
│       │                                                                     │
│       ├──► Send results back to OpenAI                                      │
│       │                                                                     │
│       └──► AI Response: "I found availability for Feb 7–10...               │
│                 Standard — $161.67 per night                                │
│                 Deluxe — $239.67 per night                                  │
│                 Suite — $422.67 per night"                                  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  4. TEST 2: CREATE RESERVATION                                              │
│  ═════════════════════════════                                              │
│  User: "I'd like to book a deluxe room... My name is John Doe..."          │
│       │                                                                     │
│       ├──► OpenAI: Decides to call create_reservation_ticket                │
│       │         Extracts: name, phone, dates, room_type, guests             │
│       │                                                                     │
│       ├──► Execute: await registry.create_reservation_ticket(...)           │
│       │         ├── Query for last ticket ID                                │
│       │         ├── Create ReservationTicket object                         │
│       │         ├── session.add(ticket)                                     │
│       │         ├── await session.commit()      ──► INSERT to database      │
│       │         └── Return ticket info                                      │
│       │                                                                     │
│       ├──► Send results back to OpenAI                                      │
│       │                                                                     │
│       └──► AI Response: "All set — your reservation request is submitted.   │
│                 Ticket ID: LOTUS-0002"                                      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  5. TEST 3: CHECK TICKET STATUS                                             │
│  ══════════════════════════════                                             │
│  User: "What's the status of my reservation LOTUS-0002?"                    │
│       │                                                                     │
│       ├──► OpenAI: Decides to call check_ticket_status                      │
│       │         ticket_id="LOTUS-0002"                                      │
│       │                                                                     │
│       ├──► Execute: await registry.check_ticket_status("LOTUS-0002")        │
│       │         └── SQL: SELECT * FROM reservation_ticket                   │
│       │                    WHERE ticket_id = 'LOTUS-0002'                   │
│       │         └── Returns ticket data                                     │
│       │                                                                     │
│       ├──► Send results back to OpenAI                                      │
│       │                                                                     │
│       └──► AI Response: "I checked ticket LOTUS-0002 — it's in pending...   │
│                 Status: pending (staff reviewing)"                          │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  6. CLEANUP                                                                 │
│  ═════════                                                                  │
│  (finally block - ALWAYS executes)                                          │
│       │                                                                     │
│       └── await registry.teardown()                                         │
│            ├── await self.session.__aexit__(None, None, None)               │
│            │      └── Return connection to pool                             │
│            ├── self.session = None                                          │
│            └── await close_db()                                             │
│                   └── engine.dispose()                                      │
│                   └── Close all pool connections                            │
│                                                                             │
│  Print: "✅ All tests completed!"                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Bug & The Fix

### Original Buggy Code

```python
# scripts/test_agent_tools.py (BEFORE)
class ToolRegistry:
    async def setup(self):
        await init_db()
        
        # ❌ PROBLEM: Using async for + break
        async for session in get_session():
            self.session = session
            break  # Generator never properly closes!
```

### The Error Explained

```
Error Chain:
═══════════

1. async for session in get_session():
   └── Calls get_session() generator

2. Inside get_session():
   async with async_session() as session:
       └── Checks out Connection from pool
       yield session  ←── Returns to caller

3. break (in setup()):
   └── Exits the for-loop immediately
   └── Generator is left suspended
   └── async with block never exits
   └── Connection stays "checked out"

4. Tests run...

5. asyncio.run() finishes:
   └── Event loop closes

6. Garbage Collector runs:
   └── Finds unclosed generator
   └── Tries to close it
   └── Tries to close connection
   └── Event loop already closed!

7. Exception:
   RuntimeError: Event loop is closed
   
   SAWarning: garbage collector trying to clean up 
              non-checked-in connection
```

### Fixed Code

```python
# scripts/test_agent_tools.py (AFTER)
class ToolRegistry:
    async def setup(self):
        await init_db()
        
        # ✅ FIX: Create session directly
        self.session = async_session()
        await self.session.__aenter__()
        
    async def teardown(self):
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
        await close_db()

async def test_conversation():
    registry = ToolRegistry()
    await registry.setup()
    
    try:
        # ... tests ...
    finally:
        await registry.teardown()  # ✅ Always called
```

---

## Complete Execution Trace

### With Bug (Original Logs)

```
✓ Database connected (using pre-seeded data)

TEST 1: Check availability
User: What rooms...
AI: I found availability...

TEST 2: Create a reservation
User: I'd like to book...
AI: All set — your reservation...

TEST 3: Check ticket status
User: What's the status...
AI: I checked ticket LOTUS-0002...

✅ All tests completed!

─────────────────────────────────────────────────────────────────────────────
⚠️ EXCEPTION (after tests complete):

Exception terminating connection <AdaptedConnection <asyncpg.connection...>>
Traceback (most recent call last):
  File ".../sqlalchemy/pool/base.py", line 372, in _close_connection
    self._dialect.do_terminate(connection)
  ...
RuntimeError: Event loop is closed

SAWarning: The garbage collector is trying to clean up non-checked-in 
           connection ..., which will be terminated. Please ensure that 
           SQLAlchemy pooled connections are returned to the pool explicitly.
```

### With Fix (Current Logs)

```
============================================================
🧪 Testing Reservation Agent with Custom Functions
============================================================
✓ Database connected (using pre-seeded data)

------------------------------------------------------------
TEST 1: Check availability
------------------------------------------------------------

User: What rooms do you have available from 2026-02-07 to 2026-02-10 for 2 guests?

AI: Thanks — I checked availability for Feb 7–10 (2 guests). Here are the options...
- Standard — Rate: $161.67 per night
- Deluxe — Rate: $239.67 per night
- Suite — Rate: $422.67 per night

------------------------------------------------------------
TEST 2: Create a reservation
------------------------------------------------------------

User: I'd like to book a deluxe room from 2026-02-07 to 2026-02-10 for 2 guests...

AI: All set — I submitted your booking request.
Reservation ticket: LOTUS-0004 (status: pending)
...

------------------------------------------------------------
TEST 3: Check ticket status
------------------------------------------------------------

User: What's the status of my reservation LOTUS-0004?

AI: I checked on ticket LOTUS-0004...
Status: pending (under staff review)

============================================================
✅ All tests completed!
============================================================

(No exceptions, no warnings)
```

---

## Key Takeaways

| # | Lesson | Application |
|---|--------|-------------|
| 1 | **Don't break out of async generators** | Use direct instantiation instead |
| 2 | **Always cleanup resources** | Use `try/finally` or context managers |
| 3 | **Understand your connection pool** | Know when connections are checked out vs returned |
| 4 | **Scalar queries need LIMIT** | `scalar_one_or_none()` expects max 1 row |
| 5 | **Function calling is two-step** | Call model → Execute tools → Call model again |

---

## File Locations

| Component | Path |
|-----------|------|
| Database engine & session | `src/reservation/db.py` |
| Tool functions | `src/reservation/tools.py` |
| Agent with function calling | `src/voice_ai/services/reservation_agent.py` |
| Test script | `scripts/test_agent_tools.py` |
| Database models | `src/reservation/models.py` |
| This documentation | `docs/RESERVATION_AGENT_IMPLEMENTATION.md` |
