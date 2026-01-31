"""
Hub & Spoke RAG for Voice AI

Multi-tenant retrieval system with:
- Hub: Global knowledge (applies to all locations)
- Spokes: Location-specific knowledge (overrides hub)

Usage:
    from rag import HubSpokeRAG, RAGTools
    
    # Initialize
    rag = HubSpokeRAG()
    await rag.ingest_all()
    
    # Query
    results = await rag.query(
        "What's the check-in time?",
        tenant_id="chicago"
    )
    
    # Use with voice agent
    tools = RAGTools(rag)
    answer = await tools.query_knowledge(
        question="Do you allow pets?",
        location="ny"
    )
"""

from .hub_spoke import HubSpokeRAG, demo_rag
from .tools import RAGTools, RAG_TOOL_SCHEMA
from .models import KnowledgeChunk, RAGResult, RetrievedChunk

__all__ = [
    "HubSpokeRAG",
    "RAGTools",
    "RAG_TOOL_SCHEMA",
    "KnowledgeChunk",
    "RAGResult",
    "RetrievedChunk",
    "demo_rag",
]
