"""Data models for Hub & Spoke RAG."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class KnowledgeChunk:
    """A single chunk of knowledge (from hub or spoke)."""
    id: str
    content: str
    tenant_id: Optional[str]  # None for hub, "chicago"/"ny"/"sf" for spokes
    category: str  # policy, amenities, dining, safety, about, loyalty
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    @property
    def is_hub(self) -> bool:
        """True if this is a hub (global) chunk."""
        return self.tenant_id is None
    
    @property
    def is_spoke(self) -> bool:
        """True if this is a spoke (location-specific) chunk."""
        return self.tenant_id is not None
    
    def to_vector_doc(self) -> Dict[str, Any]:
        """Convert to vector DB document format."""
        return {
            "id": self.id,
            "content": self.content,
            "tenant_id": self.tenant_id or "hub",
            "category": self.category,
            "metadata": self.metadata,
        }


@dataclass
class RetrievedChunk:
    """A chunk retrieved from vector DB with similarity score."""
    chunk: KnowledgeChunk
    similarity: float  # Cosine similarity score
    source: str  # "hub" or "spoke"
    
    def __lt__(self, other):
        """Sort by similarity descending."""
        return self.similarity > other.similarity


@dataclass
class RAGResult:
    """Final RAG result after hub+spoke merging."""
    query: str
    tenant_id: Optional[str]
    chunks: List[RetrievedChunk]
    merged_context: str  # Formatted context for LLM
    latency_ms: float
    retrieved_from: Dict[str, int]  # {"hub": 3, "spoke": 2}
    
    def to_prompt_context(self, max_chars: int = 2000) -> str:
        """Format for LLM prompt."""
        return self.merged_context[:max_chars]


@dataclass
class IngestionRecord:
    """Track what was ingested."""
    tenant_id: str
    file_path: str
    chunks_count: int
    ingested_at: datetime
    status: str  # "success", "failed", "partial"
    errors: List[str] = field(default_factory=list)
