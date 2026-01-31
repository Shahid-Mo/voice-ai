"""
Hub & Spoke RAG Engine

Multi-tenant retrieval that combines:
- Hub: Global knowledge (applies to all locations)
- Spokes: Location-specific knowledge (overrides hub)
"""
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models import KnowledgeChunk, RAGResult, RetrievedChunk
from .embeddings import EmbeddingProvider, MockEmbeddingProvider
from .vector_store import HubSpokeVectorStore


class HubSpokeRAG:
    """
    Production-ready Hub & Spoke RAG system.
    
    Usage:
        rag = HubSpokeRAG()
        await rag.ingest_all()
        
        results = await rag.query(
            "What's the check-in time?",
            tenant_id="chicago"
        )
    """
    
    def __init__(
        self,
        data_dir: str = "data/prod",
        use_mock_embeddings: bool = False
    ):
        self.data_dir = Path(data_dir)
        self.store = HubSpokeVectorStore()
        
        # Embedding provider
        if use_mock_embeddings:
            self.embeddings = MockEmbeddingProvider()
        else:
            self.embeddings = EmbeddingProvider()
        
        self._is_ingested = False
    
    async def ingest_all(self) -> Dict[str, int]:
        """
        Ingest all hub and spoke data.
        
        Returns:
            Dict mapping index name to chunk count
        """
        results = {}
        
        # Ingest hub
        hub_path = self.data_dir / "hub" / "global.json"
        if hub_path.exists():
            hub_count = await self._ingest_file(hub_path, tenant_id=None)
            results["hub"] = hub_count
        
        # Ingest spokes
        spokes_dir = self.data_dir / "spokes"
        if spokes_dir.exists():
            for spoke_file in spokes_dir.glob("*.json"):
                tenant_id = spoke_file.stem  # chicago, ny, sf
                count = await self._ingest_file(spoke_file, tenant_id=tenant_id)
                results[tenant_id] = count
        
        self._is_ingested = True
        return results
    
    async def _ingest_file(self, file_path: Path, tenant_id: Optional[str]) -> int:
        """Ingest a single JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Create chunks
        chunks = []
        for item in data:
            chunk = KnowledgeChunk(
                id=item["id"],
                content=item["content"],
                tenant_id=tenant_id,
                category=item.get("category", "general"),
                metadata=item.get("metadata", {})
            )
            chunks.append(chunk)
        
        # Embed and add to store
        texts = [c.content for c in chunks]
        embeddings = await self.embeddings.embed_batch(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
            self.store.add_chunk(chunk, embedding)
        
        return len(chunks)
    
    async def query(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        top_k: int = 5,
        include_hub: bool = True
    ) -> RAGResult:
        """
        Query the RAG system.
        
        Args:
            query: User question
            tenant_id: Location context (chicago, ny, sf) or None for hub only
            top_k: Number of results to return
            include_hub: Whether to include global knowledge
        
        Returns:
            RAGResult with merged context
        """
        start_time = time.perf_counter()
        
        if not self._is_ingested:
            raise RuntimeError("RAG not ingested. Call ingest_all() first.")
        
        # Embed query
        query_embedding = await self.embeddings.embed(query)
        
        # Retrieve
        if include_hub and tenant_id:
            # Hub + Spoke merge
            results = self.store.query_hub_and_spoke(
                query_embedding,
                tenant_id=tenant_id,
                top_k=top_k
            )
        elif tenant_id:
            # Spoke only
            results = self.store.query_spoke(tenant_id, query_embedding, top_k)
        else:
            # Hub only
            results = self.store.query_hub(query_embedding, top_k)
        
        # Build merged context
        context_parts = []
        for i, r in enumerate(results, 1):
            source_tag = f"[{r.source}]" if r.source == "hub" else f"[{r.chunk.tenant_id}]"
            context_parts.append(f"{i}. {source_tag} {r.chunk.content}")
        
        merged_context = "\n\n".join(context_parts)
        
        # Track sources
        retrieved_from = {"hub": 0, "spoke": 0}
        for r in results:
            if r.source == "hub":
                retrieved_from["hub"] += 1
            else:
                retrieved_from["spoke"] += 1
        
        latency = (time.perf_counter() - start_time) * 1000
        
        return RAGResult(
            query=query,
            tenant_id=tenant_id,
            chunks=results,
            merged_context=merged_context,
            latency_ms=latency,
            retrieved_from=retrieved_from
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics."""
        return self.store.get_stats()
    
    def format_for_llm(self, result: RAGResult, max_chunks: int = 5) -> str:
        """
        Format RAG result for LLM prompt.
        
        This creates a clear prompt context with source attribution.
        """
        lines = [
            "# Knowledge Base Context",
            f"Query: {result.query}",
            f"Location: {result.tenant_id or 'Global'}",
            "",
            "## Retrieved Information:",
            ""
        ]
        
        for i, r in enumerate(result.chunks[:max_chunks], 1):
            source = "Global Policy" if r.source == "hub" else f"{r.chunk.tenant_id.title()} Specific"
            lines.append(f"{i}. [{source}] {r.chunk.content}")
            lines.append(f"   (Category: {r.chunk.category}, Relevance: {r.similarity:.2f})")
            lines.append("")
        
        return "\n".join(lines)


# Convenience function for quick testing
async def demo_rag():
    """Demo the RAG system."""
    print("🚀 Initializing Hub & Spoke RAG...")
    
    # Use mock embeddings for demo (no API key needed)
    rag = HubSpokeRAG(use_mock_embeddings=True)
    
    # Ingest
    print("📚 Ingesting knowledge base...")
    stats = await rag.ingest_all()
    print(f"✅ Ingested: {stats}")
    
    # Demo queries
    queries = [
        ("What's the check-in time?", "chicago"),
        ("What's the check-in time?", "ny"),
        ("Do you allow pets?", None),  # Global query
        ("Tell me about parking", "sf"),
        ("What are your quiet hours?", "chicago"),
    ]
    
    for query, tenant in queries:
        print(f"\n{'='*60}")
        print(f"Q: {query}")
        print(f"Location: {tenant or 'Global'}")
        print('-'*60)
        
        result = await rag.query(query, tenant_id=tenant)
        
        print(f"Retrieved {len(result.chunks)} chunks in {result.latency_ms:.1f}ms")
        print(f"Sources: {result.retrieved_from}")
        print("\nTop results:")
        
        for r in result.chunks[:3]:
            source = "🌍 Hub" if r.source == "hub" else f"📍 {r.chunk.tenant_id}"
            print(f"  [{source}] {r.chunk.content[:100]}...")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_rag())
