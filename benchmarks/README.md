# MCP vs Native Function Latency Benchmark

Benchmark comparing latency of **Native FastAPI** vs **MCP (Model Context Protocol)** for Voice AI applications.

## Quick Start

```bash
# 1. Start the benchmark environment
cd benchmarks
docker-compose -f docker-compose.mcp-benchmark.yml up -d

# 2. Wait for services to be ready (check with: docker-compose ps)

# 3. Run the benchmark
uv run benchmark_latency.py --iterations 100 --warmup 10

# 4. Clean up
docker-compose -f docker-compose.mcp-benchmark.yml down
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Benchmark     │────▶│   Native API    │────▶│   PostgreSQL    │
│     Script      │     │   Port 8000     │     │   Port 5432     │
│                 │     │                 │     │                 │
│                 │────▶│   MCP Server    │────▶│                 │
│                 │     │   Port 8080     │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        │ Measures latency for identical operations
        ▼
┌─────────────────┐
│   Results       │
│   - p50, p95    │
│   - p99         │
│   - std dev     │
└─────────────────┘
```

## What We're Measuring

| Operation | Native | MCP | Notes |
|-----------|--------|-----|-------|
| `list_tickets` | FastAPI endpoint | `execute_sql` tool | Full table scan |
| `get_ticket` | FastAPI endpoint | `execute_sql` tool | Indexed lookup |
| `sync_status` | FastAPI endpoint | `execute_sql` tool | Single row |

## The Protocol Difference

### Native (Direct HTTP)
```
Voice AI → HTTP GET /tickets → FastAPI → SQL → Response
```

### MCP (Model Context Protocol)
```
Voice AI → HTTP POST /tools/call → MCP Server → SQL → Response
         (JSON-RPC envelope)       (tool dispatch)
```

MCP adds:
- JSON-RPC encoding overhead
- Tool discovery/dispatch
- Session management
- Protocol abstraction

## Expected Results

| Metric | Native | MCP | Overhead |
|--------|--------|-----|----------|
| Mean Latency | ~20-40ms | ~50-80ms | +30-40ms |
| P95 Latency | ~30-50ms | ~70-100ms | +40-50ms |

## Options

```bash
# Full benchmark (all operations, 100 iterations)
uv run benchmark_latency.py

# Quick test (fewer iterations)
uv run benchmark_latency.py --iterations 20 --warmup 5

# Specific operations only
uv run benchmark_latency.py --operations list_tickets

# Save results to file
uv run benchmark_latency.py --output results.json
```

## Interpreting Results

### For Voice AI

| Total Latency | Quality | Recommendation |
|---------------|---------|----------------|
| < 150ms | Excellent | ✅ Either protocol works |
| 150-300ms | Good | ⚠️ Native preferred for voice |
| > 300ms | Poor | ❌ Optimize before production |

**Note**: These are tool execution latencies only. Add ~100-200ms for LLM processing and TTS to get total voice response time.

## Troubleshooting

### Services not starting
```bash
# Check logs
docker-compose -f docker-compose.mcp-benchmark.yml logs -f

# Restart
docker-compose -f docker-compose.mcp-benchmark.yml down
docker-compose -f docker-compose.mcp-benchmark.yml up -d
```

### Connection refused
Wait for services to be fully ready:
```bash
# Check health
curl http://localhost:8000/health
curl http://localhost:8080/health
```

## Results Format

The benchmark saves results as JSON:

```json
{
  "config": {
    "iterations": 100,
    "timestamp": "2026-01-31T10:00:00"
  },
  "results": {
    "list_tickets": {
      "native": {
        "mean_ms": 25.4,
        "p95_ms": 35.2,
        "p99_ms": 42.1
      },
      "mcp": {
        "mean_ms": 58.7,
        "p95_ms": 72.3,
        "p99_ms": 89.5
      }
    }
  }
}
```

## Video Content Ideas

### Hook
"I added 50ms to every voice interaction - here's when it's worth it"

### Key Points
1. Show raw latency numbers side-by-side
2. Explain why MCP is slower (protocol overhead)
3. Demonstrate the trade-off: speed vs isolation
4. Give specific recommendations for voice AI

### Visual
- Split-screen latency graphs
- Animation of request flow
- Summary table with recommendations
