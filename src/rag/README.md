# Hub & Spoke RAG System for Voice AI

Multi-tenant RAG architecture for hotel chain with global knowledge (hub) and location-specific overlays (spokes).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER QUERY                                         │
│  "What's the check-in time in Chicago?"                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RETRIEVAL LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Step 1: Detect Tenant from Context                                          │
│          └── Caller ID, phone number, or explicit mention                    │
│                                                                             │
│  Step 2: Parallel Retrieval                                                  │
│          ├── Query HUB index (global knowledge)                              │
│          └── Query SPOKE index (location-specific, if tenant detected)       │
│                                                                             │
│  Step 3: Merge & Rank                                                        │
│          ├── Spoke chunks get priority (location-specific wins)              │
│          ├── Hub chunks fill gaps (global defaults)                          │
│          └── Deduplicate by semantic similarity                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESPONSE GENERATION                                  │
│                                                                             │
│  "Check-in at Hotel Transylvania Chicago is at 2:00 PM..."                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Model

### Hub (Global Knowledge)
- `id`: global_001, global_002, ...
- `tenant_id`: null (applies to all)
- `content`: Policy, amenities, brand info
- `category`: policy, amenities, dining, safety, etc.
- `metadata`: type, tags

### Spokes (Location-Specific)
- `id`: chicago_001, ny_001, sf_001, ...
- `tenant_id`: chicago, ny, sf
- `content`: Location-specific info
- `category`: Same as hub
- `metadata`: type, override_priority

## Override Rules

| Scenario | Example | Behavior |
|----------|---------|----------|
| Spoke overrides Hub | Check-in time | Use spoke value, ignore hub |
| Hub only | Cancellation policy | Use hub (no spoke conflict) |
| Spoke only | Local attractions | Use spoke |
| Both exist | Payment methods | Merge or spoke wins |

## Usage

```python
from rag.hub_spoke import HubSpokeRAG

# Initialize
rag = HubSpokeRAG()

# Query with tenant context
results = await rag.query(
    query="What's the check-in time?",
    tenant_id="chicago",  # From caller context
    top_k=5
)

# Returns merged results from hub + spoke
```

## Adding New Location (New Spoke)

1. Create `data/prod/spokes/newlocation.json`
2. Run ingestion: `python -m rag.ingest --tenant newlocation`
3. Vector DB automatically creates new spoke index

## Production Considerations

- **Vector DB**: PostgreSQL with pgvector OR ChromaDB for simplicity
- **Embeddings**: OpenAI text-embedding-3-small (cheap & fast)
- **Caching**: Redis for frequent queries
- **Monitoring**: Track retrieval latency, hit rates per tenant
