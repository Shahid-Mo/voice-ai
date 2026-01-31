# Voice AI on AWS Lambda: Concrete Analysis

## Your Assumption: Is Lambda Good for Voice AI?

**15-minute timeout assumption:** ✅ Valid for most use cases
- Customer service: 5-10 min average (Zendesk reports 6 min avg)
- Restaurant reservations: 2-3 min
- Appointment booking: 3-5 min
- Surveys/polls: 2-4 min
- Support hotline: 8-12 min

**Edge cases that need longer (15+ min):**
- Therapy/counseling sessions (45-60 min)
- Sales discovery calls (30-45 min)
- Technical support escalations (20+ min)
- Legal consultations (30+ min)

**For 80-90% of voice AI use cases, Lambda's 15-minute limit is fine.**

---

## Lambda Specs: What You Actually Get

| Memory (MB) | vCPU | Network Bandwidth | Use Case |
|-------------|------|-------------------|----------|
| 128 MB | 0.083 vCPU | ~25 Mbps | ❌ Too weak for voice AI |
| 512 MB | 0.333 vCPU | ~100 Mbps | ⚠️ Minimal config |
| 1024 MB (1 GB) | 0.667 vCPU | ~500 Mbps | ✅ **Good baseline** |
| 1769 MB | 1.0 vCPU | ~1 Gbps | ✅ Comfortable |
| 3008 MB | 1.8 vCPU | ~2 Gbps | ✅ High concurrency |
| 10240 MB (max) | 6 vCPU | ~5 Gbps | Overkill for single call |

**Voice AI is I/O-bound, not CPU-bound.** Most of the work is coordinating network streams (STT, LLM, TTS), not computation.

---

## Concrete Math: Chunk Size Impact on Lambda

### Scenario: 10-minute customer service call

**Audio streaming parameters:**
- Duration: 600 seconds (10 minutes)
- Sample rate: 16,000 Hz
- Encoding: linear16 (2 bytes/sample)
- Data rate: 16,000 × 2 = 32,000 bytes/sec = 32 KB/s
- Total audio: 600 sec × 32 KB/s = 19,200 KB = **18.75 MB**

---

### Option 1: Small Chunks (2560 bytes = 80ms) - Deepgram Recommendation

**Network calls to Deepgram:**
```
Total audio: 19,200 KB = 19,660,800 bytes
Chunk size: 2560 bytes
Number of chunks: 19,660,800 / 2560 = 7,680 chunks
```

**Timing:**
```
Call duration: 600 seconds
Chunks sent: 7,680
Chunks per second: 7,680 / 600 = 12.8 chunks/sec
Time between chunks: 1000ms / 12.8 = 78ms ✅ (matches 80ms target)
```

**Lambda implications:**
- **Event loop cycles:** 7,680 (one per chunk)
- **HTTP requests to Deepgram:** 7,680 WebSocket frames
- **CPU overhead:** ~0.1-0.2ms per chunk × 7,680 = 768-1,536ms total
- **Network overhead:** Minimal (WebSocket keeps connection open)

**Lambda CPU usage:**
```
Total compute time: 600 seconds (call duration)
Active CPU: ~1.5 seconds (overhead)
CPU utilization: 1.5 / 600 = 0.25% of one vCPU

A 512 MB Lambda (0.333 vCPU) can easily handle this.
```

---

### Option 2: Medium Chunks (4096 bytes = 128ms) - Our Current Default

**Network calls to Deepgram:**
```
Total audio: 19,660,800 bytes
Chunk size: 4096 bytes
Number of chunks: 19,660,800 / 4096 = 4,800 chunks
```

**Timing:**
```
Chunks per second: 4,800 / 600 = 8 chunks/sec
Time between chunks: 1000ms / 8 = 125ms ✅ (matches 128ms target)
```

**Lambda implications:**
- **Event loop cycles:** 4,800 (37% fewer than small chunks)
- **HTTP requests:** 4,800 WebSocket frames
- **CPU overhead:** ~0.1-0.2ms per chunk × 4,800 = 480-960ms total
- **Network overhead:** Minimal

**Lambda CPU usage:**
```
Active CPU: ~1 second (overhead)
CPU utilization: 1 / 600 = 0.16% of one vCPU

Even less work than small chunks.
```

---

### Option 3: Large Chunks (8192 bytes = 256ms)

**Network calls to Deepgram:**
```
Number of chunks: 19,660,800 / 8192 = 2,400 chunks
Chunks per second: 2,400 / 600 = 4 chunks/sec
Time between chunks: 250ms
```

**Lambda implications:**
- **Event loop cycles:** 2,400 (68% fewer than small chunks)
- **CPU overhead:** ~0.5 seconds total
- **Turn detection lag:** 🔴 Slow - may miss quick pauses

---

## The Real Bottleneck: Network Latency, Not CPU

**Lambda networking:**
- Latency to AWS services (same region): 1-5ms
- Latency to Deepgram (external): 20-50ms (typical), up to 200ms (worst case)
- WebSocket overhead: ~1-2ms per frame

**The chunk size matters for turn detection, NOT Lambda performance.**

| Chunk Size | Turn Detection Delay | Lambda CPU Impact |
|------------|---------------------|-------------------|
| 2560 bytes (80ms) | 80-130ms | ✅ 0.25% vCPU |
| 4096 bytes (128ms) | 128-178ms | ✅ 0.16% vCPU |
| 8192 bytes (256ms) | 256-306ms | ✅ 0.08% vCPU |

**All three options use <1% of a single vCPU.** Lambda performance is not the constraint.

---

## Cost Analysis: Does Chunk Size Affect Lambda Bills?

**Lambda pricing (us-east-1, 2024):**
- Compute: $0.0000166667 per GB-second
- Requests: $0.20 per 1M requests (doesn't apply to streaming - one long invocation)

**10-minute call with 1024 MB Lambda:**
```
Duration: 600 seconds
Memory: 1 GB
GB-seconds: 600 × 1 = 600 GB-seconds
Cost: 600 × $0.0000166667 = $0.01 (one penny)
```

**Does chunk size change the cost?**
- ❌ No. Lambda charges by invocation duration, not by number of event loop cycles.
- Whether you send 2,400 chunks or 7,680 chunks, the invocation runs for 600 seconds.
- Cost: $0.01 regardless of chunk size.

**The real cost is in the AI services:**
- Deepgram STT: ~$0.0043/min = $0.043 for 10 min
- OpenAI GPT-4: ~$0.03-0.06 per 1K tokens (depends on conversation)
- Deepgram TTS: ~$0.015/min = $0.15 for 10 min
- **Total AI costs: ~$0.25-0.30 per 10-minute call**
- **Lambda cost: $0.01 (3% of total)**

Lambda is **not** the bottleneck.

---

## Can a Small Lambda Handle Voice AI?

**Baseline recommendation: 1024 MB (1 GB) Lambda**

Why?
- ✅ 0.667 vCPU (plenty for I/O coordination)
- ✅ ~500 Mbps network (handles 32 KB/s audio easily)
- ✅ $0.01 per 10-minute call
- ✅ Room for LLM streaming, TTS buffering, error handling

**Can you go smaller (512 MB)?**
- ⚠️ Possible but tight
- Network bandwidth: ~100 Mbps (still 300x more than needed for 32 KB/s audio)
- CPU: 0.333 vCPU (enough for I/O, but limited headroom)
- Risk: If you add complex logic (vector DB queries, multi-turn reasoning), you'll hit limits

**Can you go larger (1769 MB = 1 full vCPU)?**
- ✅ Good if you're doing local processing (transcoding, audio analysis)
- ✅ Better cold start times
- ✅ Only ~2x the cost ($0.02 per 10-min call)

---

## Lambda vs Alternatives for Voice AI

### AWS Lambda (Serverless)

**Pros:**
- ✅ Auto-scales (0 → 1000+ concurrent calls instantly)
- ✅ Pay-per-use (no idle servers)
- ✅ Integrated with AWS ecosystem (S3 for recordings, DynamoDB for state)
- ✅ Good for spiky traffic (support hotline with 10x traffic during incidents)

**Cons:**
- ❌ 15-minute timeout (hard limit)
- ❌ Cold starts (200-500ms first call)
- ❌ Limited observability (debugging WebSocket streams is hard)
- ❌ WebSocket management (need API Gateway WebSocket or custom solution)

**Cost: $0.01 per 10-min call (compute only)**

---

### ECS Fargate (Containers)

**Pros:**
- ✅ No timeout (run indefinitely)
- ✅ Full control over runtime
- ✅ Better for long therapy/counseling sessions (60+ min)
- ✅ Easier WebSocket management

**Cons:**
- ❌ You pay for idle capacity (even when no calls active)
- ❌ Manual scaling configuration
- ❌ More ops overhead (container orchestration)

**Cost: ~$0.04-0.08 per 10-min call** (assumes 0.25 vCPU task running 24/7 with 50% utilization)

---

### EC2 (Virtual Machines)

**Pros:**
- ✅ Full control (custom kernels, GPU if needed)
- ✅ Persistent connections
- ✅ No timeout

**Cons:**
- ❌ You manage everything (scaling, monitoring, patching)
- ❌ Pay for idle capacity
- ❌ Over-engineering for most voice AI use cases

**Cost: $0.05-0.10 per 10-min call** (t3.small instance, amortized)

---

### Twilio Media Streams / VAPI (Managed Platforms)

**Pros:**
- ✅ Built for voice (PSTN integration, call routing)
- ✅ No infrastructure management
- ✅ Built-in call recording, logging, compliance

**Cons:**
- ❌ Vendor lock-in
- ❌ Higher costs (markup on AI services)
- ❌ Less flexibility

**Cost: $0.50-1.00 per 10-min call** (includes platform fees)

---

## Recommendation: Lambda is Good for Voice AI

**Use Lambda if:**
- ✅ Calls are <15 minutes (90% of use cases)
- ✅ Traffic is spiky (support hotlines, outbound campaigns)
- ✅ You want zero ops overhead
- ✅ You're integrating with AWS services (S3, DynamoDB, EventBridge)

**Use Fargate/ECS if:**
- ⚠️ Calls are >15 minutes (therapy, long sales calls)
- ⚠️ You need persistent connections/state
- ⚠️ You have steady, predictable traffic (24/7 customer service)

**Use dedicated platforms (Twilio, VAPI) if:**
- ⚠️ You need PSTN integration (phone numbers, call routing)
- ⚠️ You want compliance/recording built-in
- ⚠️ You're willing to pay for convenience

---

## Concrete Answer to Your Question

> "Can one small tiny Lambda instance handle this?"

**Yes, with caveats:**

| Lambda Config | Verdict | Notes |
|---------------|---------|-------|
| 128 MB | ❌ No | Too weak, will hit CPU/network limits |
| 512 MB | ⚠️ Barely | Works but no headroom for complexity |
| **1024 MB** | ✅ **Yes** | **Recommended baseline** |
| 1769 MB | ✅ Yes | Better cold starts, more headroom |

**The chunk size (2560 vs 4096 vs 8192) has negligible impact on Lambda performance.**
- All use <1% of one vCPU
- All cost the same (~$0.01 per 10-min call)
- The difference is in **turn detection latency**, not Lambda capacity

**Choose chunk size based on user experience, not Lambda limits:**
- 2560 bytes (80ms): Best turn detection, Deepgram recommended
- 4096 bytes (128ms): Slightly slower turn detection, still fine
- 8192 bytes (256ms): Noticeably laggy for interruptions

---

## What Actually Matters for Lambda Voice AI

**Not a bottleneck:**
- ✅ CPU (voice AI is I/O-bound)
- ✅ Chunk size (all options use <1% vCPU)
- ✅ Cost (Lambda is 3% of total costs)

**Real bottlenecks:**
- 🔴 **Network latency** (Lambda → Deepgram → OpenAI → Deepgram → Lambda)
- 🔴 **LLM response time** (GPT-4 takes 500ms-2s to generate first token)
- 🔴 **Turn detection accuracy** (did the user actually stop talking?)
- 🔴 **15-minute timeout** (if calls exceed this, Lambda is wrong choice)

**Optimize for the 80/20:**
1. Use 1024 MB Lambda (costs $0.01, eliminates worry)
2. Use 2560-byte chunks (Deepgram's recommendation)
3. Focus on LLM prompt optimization (bigger impact than infrastructure)
4. Monitor P95 latency (network variance matters more than average)

---

## TL;DR

- **Lambda is a good choice for voice AI** (auto-scaling, pay-per-use, <15 min calls)
- **1024 MB Lambda can easily handle voice AI** (I/O-bound, not CPU-bound)
- **Chunk size doesn't affect Lambda performance** (all options use <1% vCPU)
- **Choose chunk size for turn detection, not Lambda capacity:** Use 2560 bytes (Deepgram's rec)
- **Real costs are AI services ($0.25/call), not Lambda ($0.01/call)**
- **15-minute limit is fine for 90% of use cases** (customer service, booking, surveys)

If you need >15-minute calls, use ECS Fargate. Otherwise, Lambda is the right tool.
