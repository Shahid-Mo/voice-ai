# Human Escalation Architecture Plan

## Overview

Human escalation allows the AI to hand off conversations to human agents when:
- User explicitly asks ("I want to talk to a person")
- Request is too complex for AI
- User shows frustration (repeated corrections, angry tone)
- Business policy requires human (high-value bookings, complaints)
- System errors prevent AI from helping

## Where It Fits in Current Architecture

```
VoiceSession (voice_session.py)
    │
    ├─→ STT (Deepgram) ──→ transcript
    │
    ├─→ LLM (OpenAI) ──→ response + ESCALATION_SIGNAL
    │                      │
    │                      └─→ 🆕 EscalationManager.request_escalation()
    │                          - Pause AI pipeline
    │                          - Add to queue
    │                          - Notify user: "Connecting you to an agent..."
    │
    └─→ TTS (Deepgram) ──→ "Please hold, connecting you now..."
```

## Integration Points in VoiceSession

### 1. Add State to VoiceSession (line ~67)

```python
# Escalation state
self.escalation_requested: bool = False
self.escalation_reason: str | None = None
self.escalation_queue_position: str | None = None
```

### 2. Inject EscalationManager

```python
def __init__(self, websocket: WebSocket):
    # ... existing code ...
    self.escalation_mgr = EscalationManager()  # NEW
```

### 3. Detect Escalation in LLM Response

**In `process_llm_and_tts()` (line ~289):**

```python
async for llm_chunk in self.llm.stream_complete(...):
    # Check for escalation signals
    if "<ESCALATE>" in llm_chunk or "ESCALATION_REQUESTED" in llm_chunk:
        await self._handle_escalation_request(
            reason="llm_detected",
            context={"user_input": user_input}
        )
        break  # Stop processing
```

### 4. New Method: Handle Escalation

```python
async def _handle_escalation_request(self, reason: str, context: dict) -> None:
    """Request human escalation and pause AI."""
    logger.info(f"🆘 Escalation requested: {reason}")

    self.escalation_requested = True
    self.escalation_reason = reason

    # Add to queue
    queue_id = await self.escalation_mgr.request_escalation(
        session_id=self.conversation_id,
        reason=reason,
        context=context
    )
    self.escalation_queue_position = queue_id

    # Inform user
    hold_message = (
        "I understand you'd like to speak with someone. "
        "Let me connect you to one of our team members. "
        "Please hold for just a moment."
    )

    # Synthesize hold message
    await self._synthesize_and_send(hold_message)

    # Pause STT processing (stop responding to user speech)
    self.state = "escalated"  # NEW STATE
```

## New Service: EscalationManager

**File:** `services/escalation_manager.py`

### Responsibilities:
1. **Queue management** - FIFO queue for escalation requests
2. **Agent assignment** - Match sessions with available agents
3. **Status tracking** - pending → assigned → completed
4. **Context passing** - Give agent full conversation history

### Key Methods:

```python
async def request_escalation(session_id, reason, context) -> queue_id
  # Add to queue, return position

async def assign_agent(session_id, agent_id) -> bool
  # Assign human agent to session

async def get_next_escalation() -> dict
  # For agent dashboard: pull next session

async def cancel_escalation(session_id)
  # User resolved issue, remove from queue
```

## Agent Handoff Flow

### 1. User Requests Escalation
```
User: "I want to talk to a person"
  ↓
STT: transcript → "I want to talk to a person"
  ↓
LLM: detects intent → <ESCALATE reason="user_requested">
  ↓
VoiceSession: _handle_escalation_request()
  ↓
EscalationManager: add to queue
  ↓
TTS: "Connecting you to an agent, please hold..."
  ↓
State: listening → escalated
```

### 2. Agent Dashboard Pulls Next Session
```
Agent opens dashboard
  ↓
Dashboard: GET /api/escalations/next
  ↓
EscalationManager: get_next_escalation()
  ↓
Returns: {
  session_id,
  conversation_history,
  user_context (name, phone, notes),
  reason
}
  ↓
Agent WebSocket connects: /ws/agent/{session_id}
```

### 3. Dual Audio Routing
```
During escalation:
  User audio ──→ Agent (direct)
  Agent audio ──→ User (direct)

VoiceSession paused:
  - STT still listening (transcribing for logs)
  - LLM NOT called
  - TTS NOT used
```

### 4. Agent Ends Call or Returns to AI
```
Agent clicks "End Call":
  → Normal call termination

Agent clicks "Return to AI":
  → EscalationManager.cancel_escalation()
  → VoiceSession.state = "listening"
  → AI resumes from where it left off
```

## LLM Prompt Engineering for Escalation

### Add to System Prompt:

```
You are a restaurant reservation assistant. You can help with:
- Checking availability
- Making reservations
- Answering menu questions
- Modifying existing bookings

If the user asks for:
- Complex special requests (large parties, custom menus)
- To speak with a manager/person
- Things you cannot help with
- Shows frustration (repeated corrections)

Respond with: <ESCALATE reason="user_requested|complex|frustrated">

Example:
User: "I need to talk to the manager about catering"
AI: "I'd be happy to connect you with our catering team. <ESCALATE reason="complex"> Let me get someone who can help you with that."
```

## Database Schema (Future)

### Table: `escalations`
```sql
CREATE TABLE escalations (
  id UUID PRIMARY KEY,
  session_id TEXT NOT NULL,
  conversation_id TEXT,
  reason TEXT NOT NULL,
  context JSONB,
  requested_at TIMESTAMP NOT NULL,
  assigned_at TIMESTAMP,
  resolved_at TIMESTAMP,
  agent_id TEXT,
  status TEXT NOT NULL -- pending|assigned|resolved|cancelled
);
```

## WebSocket Route Extension

**File:** `api/routes/voice_ws.py`

### New Endpoint: `/ws/agent/{session_id}`

```python
@router.websocket("/ws/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket for human agents to take over sessions.

    Flow:
    1. Agent connects with session_id
    2. Bridge audio: User ←→ Agent (direct)
    3. VoiceSession paused (AI silent)
    4. Agent can end call or return to AI
    """
    # Implementation details...
```

## Testing Scenarios

### Scenario 1: User Requests Human
```
User: "Can I talk to someone?"
AI: "Of course, let me connect you. <ESCALATE reason="user_requested">"
System: Adds to queue, plays hold music
Agent: Picks up call from dashboard
```

### Scenario 2: Complex Request
```
User: "I need to book a 50-person event with custom menu"
AI: "That sounds wonderful! Let me connect you with our events team who can help customize that. <ESCALATE reason="complex">"
```

### Scenario 3: User Frustration
```
User: "No no no, that's not what I said!" (3rd time)
AI: [Detects frustration in tone/repetition]
AI: "I apologize for the confusion. Let me connect you with someone who can better assist. <ESCALATE reason="frustrated">"
```

## Metrics to Track

1. **Escalation Rate** - % of calls that escalate
2. **Escalation Reasons** - Distribution (user_requested, complex, etc.)
3. **Time to Agent** - How long users wait
4. **Resolution Rate** - % resolved by agent vs abandoned
5. **Return to AI Rate** - % handed back to AI after agent help

## Future Enhancements

1. **Smart Routing** - Route to agents by specialty (reservations, catering, complaints)
2. **Priority Queue** - VIP customers jump the queue
3. **Agent Availability** - Check if agents online before offering escalation
4. **Callback Option** - "All agents busy, we'll call you back"
5. **AI Co-Pilot** - Agent sees AI suggestions while talking to user

## Summary

**Integration is clean:**
- VoiceSession gets 3 new fields + 1 new method
- EscalationManager is standalone service (zero coupling)
- LLM prompt instructs when to escalate
- Agent dashboard pulls from queue
- Dual audio routing during escalation
- AI can resume if agent hands back

**Key Insight:** Escalation is a **state transition**, not a separate system. VoiceSession already manages states (idle → listening → processing → speaking), we just add "escalated" state.
