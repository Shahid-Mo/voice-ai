# Voice AI Tutorial Series - Video Script

## Series Overview

This is not one video - it's a **comprehensive series** covering the entire Voice AI landscape. Each video builds on the previous, but can also stand alone.

**Series Goal:** Make the viewer an authority on Voice AI systems.

---

## Video Metadata

**Channel Positioning:**
- Deep technical content, not surface-level tutorials
- Production-grade code, not toy demos
- Real comparisons with data, not opinions

**Target Audience:**
- Backend developers exploring Voice AI
- Startup founders building voice products
- Engineers evaluating voice AI vendors
- Anyone wanting to understand the Voice AI stack

---

## VIDEO 1: The Voice AI Landscape (Foundation)

**Title:** "Voice AI in 2024: The Complete Architecture Guide (Build a Production System)"

**Length:** 40-50 minutes

### Hook (0:00 - 1:30)

**[SCREEN: Live demo - call the number, ask a question, get answer]**

> "I'm going to call this number and have a conversation with an AI. But here's what makes this different - I built every piece of this myself. The speech recognition, the AI brain, the voice synthesis - all modular, all swappable."

> "By the end of this series, you'll understand every component in the Voice AI stack, know which vendors to use when, and have built your own production system."

> "Let's start with the big picture."

### Section 1: The Voice AI Stack (1:30 - 8:00)

**[TABLET: Draw the full pipeline step by step - like your diagram]**

**Draw and explain:**
1. User speaks → Phone → PSTN to Internet Gateway
2. Gateway providers: Twilio, Telnyx, SignalWire, VAPI
3. Audio stream → STT (Deepgram, AssemblyAI)
4. Text → LLM (Groq, OpenAI, Gemini)
5. LLM can branch: RAG retrieval OR Function call (DB)
6. Response text → TTS (Cartesia, Deepgram, ElevenLabs)
7. Audio back to user

**Key insight to emphasize:**

> "Every box in this diagram is swappable. That's the architecture we're building - plug in any vendor, compare them, pick the best for your use case."

**[SCREEN: Show the architecture from VOICE-AI.md]**

### Section 2: Why Modular? (8:00 - 12:00)

**[TABLET: Draw vendor lock-in vs modular]**

**Talking points:**
- Vendor lock-in is real - APIs change, prices change
- Different use cases need different providers
- Testing and benchmarking requires abstraction
- Production systems need fallbacks

> "If Deepgram goes down, can you switch to AssemblyAI in 5 minutes? With our architecture, yes."

### Section 3: Project Setup (12:00 - 20:00)

**[SCREEN: VS Code + Terminal]**

**Show:**
- Project structure creation
- pyproject.toml setup
- Provider interfaces (abstract base classes)
- Config system with provider selection

**Code walkthrough:**
```python
# Show the abstract interfaces
# Show how config selects provider
# Show dependency injection pattern
```

> "This pattern - interface + implementations + config selection - is how production systems work. Not hardcoded vendor calls."

### Section 4: First Provider - STT with Deepgram (20:00 - 28:00)

**[SCREEN: Code]**

**Build live:**
- Deepgram SDK setup
- Implement STTProvider interface
- Handle streaming audio
- Test with audio file

**[TABLET: Draw streaming vs batch transcription]**

> "Streaming is critical for voice. You can't wait for someone to finish a 30-second sentence before starting transcription."

### Section 5: Second Provider - LLM with Groq (28:00 - 35:00)

**[SCREEN: Code]**

**Build live:**
- Groq SDK setup (Llama models)
- Implement LLMProvider interface
- Add function calling support
- Test completion

**Why Groq:**
> "Groq is insanely fast. For voice, latency is everything. We'll compare with OpenAI later, but Groq's speed is hard to beat."

### Section 6: Third Provider - TTS with Cartesia (35:00 - 42:00)

**[SCREEN: Code]**

**Build live:**
- Cartesia setup
- Implement TTSProvider interface
- Streaming synthesis
- Test audio output

**Play audio samples**

### Section 7: Wiring It Up (42:00 - 48:00)

**[SCREEN: Code]**

**Build:**
- Orchestrator service
- Pipeline: STT → LLM → TTS
- Test without phone (audio file in, audio file out)

**Demo the pipeline locally**

### Wrap Up (48:00 - 50:00)

**Recap:**
- Built modular provider system
- Implemented STT, LLM, TTS
- Next: Add phone integration, RAG, database actions

**Tease Video 2:**
> "Next time: We add the phone number and make our first real call. Plus, we'll set up RAG so our AI actually knows something useful."

---

## VIDEO 2: Phone Integration + RAG

**Title:** "Building a Voice AI Knowledge Agent (RAG + Phone Integration)"

**Length:** 45-55 minutes

### Outline

1. **Hook** - Make a real call, ask about "business hours", get answer from knowledge base
2. **VAPI Setup** - Phone number, webhook configuration
3. **Webhook Handler** - FastAPI endpoint for incoming calls
4. **The Full Loop** - Phone → STT → LLM → TTS → Phone
5. **RAG Setup** - PgVector, embeddings, retrieval
6. **Bitext Dataset** - Load customer support data
7. **RAG Integration** - Connect to LLM via function calling
8. **Demo** - Full knowledge agent working
9. **Troubleshooting** - Common issues and fixes

### Key Tablet Drawings

- Webhook request/response cycle
- RAG pipeline: Query → Embed → Search → Retrieve → Augment → Generate
- How LLM decides when to call RAG

---

## VIDEO 3: Actions & Database Writes

**Title:** "Voice AI That Takes Action (Phone Survey + Booking System)"

**Length:** 40-50 minutes

### Outline

1. **Hook** - Call, complete a survey, show data in database
2. **Beyond Retrieval** - RAG answers questions, but actions change state
3. **Function Calling Deep Dive** - How LLMs execute functions
4. **Use Case 1: Phone Survey**
   - Survey data model
   - Survey flow (questions, capture answers)
   - Write to PostgreSQL
   - Demo
5. **Use Case 2: Booking Agent**
   - Booking data model
   - Availability checking
   - Slot filling (date, time, name)
   - Confirmation flow
   - Demo
6. **Error Handling in Voice** - Can't show error messages!
7. **Multi-turn Conversations** - Context management

### Key Tablet Drawings

- Function calling flow
- Survey state machine
- Booking slot filling

---

## VIDEO 4: Provider Shootout

**Title:** "I Tested Every Voice AI Provider (STT, TTS, LLM Benchmarks)"

**Length:** 35-45 minutes

### Outline

1. **Hook** - Side-by-side audio comparison
2. **Methodology** - How we're testing (latency, accuracy, cost)
3. **STT Comparison**
   - Deepgram vs AssemblyAI vs Whisper
   - Latency benchmarks
   - Accuracy (WER) benchmarks
   - Cost breakdown
   - Verdict
4. **TTS Comparison**
   - Cartesia vs Deepgram vs ElevenLabs
   - Latency benchmarks
   - Quality comparison (play samples)
   - Cost breakdown
   - Verdict
5. **LLM Comparison (for Voice)**
   - Groq vs OpenAI vs Gemini
   - Latency is king
   - Function calling reliability
   - Cost breakdown
   - Verdict
6. **The Matrix** - When to use what
7. **Switching Providers** - Demo swapping in our modular system

### Key Visuals

- Benchmark charts (latency, cost)
- Audio waveform comparisons
- Decision matrix table

---

## VIDEO 5: AWS Deployment Deep Dive

**Title:** "Deploying Voice AI to Production (AWS EC2 + Fargate)"

**Length:** 50-60 minutes

### Outline

1. **Hook** - Call the deployed system from phone
2. **Why AWS?** - Options overview (EC2, Lambda, Fargate)
3. **EC2 Deployment**
   - Instance setup
   - Security groups
   - Caddy for HTTPS
   - systemd service
   - Domain + DNS
   - Demo
4. **Monitoring & Logging**
   - CloudWatch setup
   - What to monitor in voice systems
5. **Scaling with Fargate**
   - Why containers?
   - Dockerfile walkthrough
   - ECR push
   - ECS task definition
   - Fargate service
   - ALB setup
   - Auto-scaling config
6. **Cost Analysis** - EC2 vs Fargate vs Lambda
7. **Production Checklist** - What you need before going live

### Key Tablet Drawings

- AWS architecture diagram
- Scaling decision tree
- Request flow through ALB → Fargate

---

## VIDEO 6: Native Voice Models (The Future)

**Title:** "OpenAI Realtime vs Traditional Voice AI (Which Should You Use?)"

**Length:** 35-45 minutes

### Outline

1. **Hook** - Same conversation, two approaches, hear the difference
2. **The Paradigm Shift** - STT→LLM→TTS vs Speech-to-Speech
3. **OpenAI Realtime API**
   - How it works
   - Implementation
   - Demo
   - Pros and cons
4. **Gemini Live** (if available)
   - How it works
   - Implementation
   - Demo
5. **Comparison**
   - Latency
   - Quality
   - Cost
   - Flexibility (can you add RAG? function calling?)
6. **When to Use What**
   - Native for: simple assistants, low latency critical
   - Modular for: complex logic, RAG, custom integrations
7. **The Future** - Where voice AI is heading

### Key Tablet Drawings

- Traditional pipeline vs native model
- Latency comparison visualization

---

## Tablet Drawings Master List

| Drawing | Video | Purpose |
|---------|-------|---------|
| Full Voice AI Pipeline | V1 | Core architecture |
| Vendor Lock-in vs Modular | V1 | Why we build this way |
| Streaming vs Batch | V1 | STT explanation |
| Webhook Flow | V2 | VAPI integration |
| RAG Pipeline | V2 | Knowledge retrieval |
| Function Calling Flow | V3 | Actions explanation |
| Survey State Machine | V3 | Multi-turn logic |
| Booking Slot Filling | V3 | Complex conversation |
| AWS Architecture | V5 | Deployment |
| Scaling Decision Tree | V5 | When to scale how |
| Native vs Modular | V6 | Future comparison |

---

## Recurring Segments

### "The Real Talk" Moment
In each video, have a moment where you address common misconceptions or things tutorials don't tell you.

> "Here's what tutorials don't tell you about [X]..."

### Benchmark Corner
Show actual numbers, not opinions. Latency charts, cost tables, accuracy metrics.

### Code Quality Check
Periodically show why the code is production-grade, not tutorial-grade.

---

## Production Notes

**Recording setup:**
- Screen recording: OBS or similar
- Tablet: Drawing app visible
- Audio: Good mic, consistent volume
- Code: Large font, dark theme

**Editing:**
- Chapter markers for each section
- Speed up repetitive parts (typing, waiting)
- Slow down/zoom on important code
- Add diagrams as overlays when explaining

**Thumbnail style:**
- Architecture diagram element
- Bold text with key topic
- Consistent series branding

---

## Call to Action (Every Video)

1. Subscribe for the series
2. GitHub link in description
3. "What provider should I test next?" (engagement)
4. Community/Discord for questions

---

## Content Calendar (Suggested)

| Week | Video | Focus |
|------|-------|-------|
| 1 | Video 1 | Foundation + Architecture |
| 2 | Video 2 | Phone + RAG |
| 3 | Video 3 | Actions + DB |
| 4 | Video 4 | Provider Comparison |
| 5 | Video 5 | AWS Deployment |
| 6 | Video 6 | Native Voice Models |

Ship one video, gather feedback, adjust next video accordingly.
