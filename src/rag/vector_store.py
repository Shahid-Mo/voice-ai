"""Vector store for Hub & Spoke RAG."""
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .models import KnowledgeChunk, RetrievedChunk


@dataclass
class VectorIndex:
    """In-memory vector index for a tenant (or hub)."""
    tenant_id: str  # "hub" or "chicago"/"ny"/"sf"
    chunks: List[KnowledgeChunk] = field(default_factory=list)
    embeddings: np.ndarray = field(default_factory=lambda: np.array([]))
    
    def is_empty(self) -> bool:
        return len(self.chunks) == 0
    
    def add_chunk(self, chunk: KnowledgeChunk, embedding: List[float]):
        """Add a chunk with its embedding."""
        self.chunks.append(chunk)
        
        embedding_array = np.array(embedding).reshape(1, -1)
        if self.embeddings.size == 0:
            self.embeddings = embedding_array
        else:
            self.embeddings = np.vstack([self.embeddings, embedding_array])
    
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[RetrievedChunk]:
        """Search for similar chunks using cosine similarity."""
        if self.is_empty():
            return []
        
        query = np.array(query_embedding).reshape(1, -1)
        
        # Normalize for cosine similarity
        query_norm = query / np.linalg.norm(query)
        embeddings_norm = self.embeddings / np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        
        # Calculate similarities
        similarities = np.dot(embeddings_norm, query_norm.T).flatten()
        
        # Get top k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            chunk = self.chunks[idx]
            similarity = float(similarities[idx])
            source = "hub" if chunk.is_hub else "spoke"
            results.append(RetrievedChunk(chunk=chunk, similarity=similarity, source=source))
        
        return results


class HubSpokeVectorStore:
    """
    Multi-tenant vector store with hub + spoke architecture.
    
    Hub: Global knowledge (tenant_id=None, stored as "hub")
    Spokes: Location-specific knowledge (tenant_id=location)
    """
    
    def __init__(self):
        self.indices: Dict[str, VectorIndex] = {}
        self._dimension: Optional[int] = None
    
    def get_or_create_index(self, tenant_id: str) -> VectorIndex:
        """Get existing index or create new one."""
        if tenant_id not in self.indices:
            self.indices[tenant_id] = VectorIndex(tenant_id=tenant_id)
        return self.indices[tenant_id]
    
    def add_chunk(self, chunk: KnowledgeChunk, embedding: List[float]):
        """Add chunk to appropriate index."""
        # Hub chunks go to "hub" index, spoke chunks to their tenant index
        index_key = chunk.tenant_id or "hub"
        index = self.get_or_create_index(index_key)
        index.add_chunk(chunk, embedding)
        
        # Track dimension
        if self._dimension is None:
            self._dimension = len(embedding)
    
    def query_hub(self, query_embedding: List[float], top_k: int = 5) -> List[RetrievedChunk]:
        """Query only the hub (global knowledge)."""
        if "hub" not in self.indices:
            return []
        return self.indices["hub"].search(query_embedding, top_k)
    
    def query_spoke(self, tenant_id: str, query_embedding: List[float], top_k: int = 5) -> List[RetrievedChunk]:
        """Query specific spoke (location)."""
        if tenant_id not in self.indices:
            return []
        return self.indices[tenant_id].search(query_embedding, top_k)
    
    def query_hub_and_spoke(
        self,
        query_embedding: List[float],
        tenant_id: Optional[str] = None,
        top_k: int = 5,
        spoke_boost: float = 1.2  # Boost spoke results
    ) -> List[RetrievedChunk]:
        """
        Query both hub and spoke, merge results.
        
        Strategy:
        1. Always get top_k from hub (global fallback)
        2. If tenant_id provided, get top_k from spoke
        3. Merge with spoke boost (location-specific wins ties)
        4. Deduplicate by content similarity
        5. Return top_k merged
        """
        all_results = []
        
        # Query hub
        hub_results = self.query_hub(query_embedding, top_k=top_k)
        all_results.extend(hub_results)
        
        # Query spoke if tenant specified
        if tenant_id:
            spoke_results = self.query_spoke(tenant_id, query_embedding, top_k=top_k)
            # Boost spoke scores
            for r in spoke_results:
                r.similarity *= spoke_boost
            all_results.extend(spoke_results)
        
        # Sort by similarity
        all_results.sort(reverse=True)
        
        # Deduplicate by content similarity
        deduplicated = self._deduplicate(all_results, threshold=0.95)
        
        return deduplicated[:top_k]
    
    def _deduplicate(self, results: List[RetrievedChunk], threshold: float = 0.95) -> List[RetrievedChunk]:
        """Remove near-duplicate chunks based on content similarity."""
        if not results:
            return []
        
        kept = [results[0]]
        
        for candidate in results[1:]:
            is_duplicate = False
            for existing in kept:
                # Simple text similarity (can use embedding similarity)
                sim = self._text_similarity(candidate.chunk.content, existing.chunk.content)
                if sim > threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                kept.append(candidate)
        
        return kept
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Simple Jaccard similarity for deduplication."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        return {
            "total_indices": len(self.indices),
            "total_chunks": sum(len(idx.chunks) for idx in self.indices.values()),
            "hub_chunks": len(self.indices.get("hub", VectorIndex("hub")).chunks),
            "spoke_indices": [k for k in self.indices.keys() if k != "hub"],
            "spoke_chunks": {
                k: len(v.chunks) for k, v in self.indices.items() if k != "hub"
            },
            "dimension": self._dimension,
        }
