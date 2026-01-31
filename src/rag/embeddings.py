"""Embedding provider for RAG."""
import os
from typing import List
import openai


class EmbeddingProvider:
    """OpenAI embedding provider with caching."""
    
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._cache = {}  # Simple in-memory cache
        
        # Model dimensions
        self.dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
    
    async def embed(self, text: str) -> List[float]:
        """Embed single text with caching."""
        # Check cache
        cache_key = hash(text)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Call OpenAI
        response = await self.client.embeddings.create(
            model=self.model,
            input=text[:8000],  # Truncate if too long
            encoding_format="float"
        )
        
        embedding = response.data[0].embedding
        
        # Cache it
        self._cache[cache_key] = embedding
        return embedding
    
    async def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Embed multiple texts efficiently."""
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            response = await self.client.embeddings.create(
                model=self.model,
                input=[t[:8000] for t in batch],
                encoding_format="float"
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            results.extend(batch_embeddings)
        
        return results
    
    def get_dimension(self) -> int:
        """Get embedding dimension for current model."""
        return self.dimensions.get(self.model, 1536)


class MockEmbeddingProvider:
    """Mock for testing without API calls."""
    
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self._cache = {}
    
    async def embed(self, text: str) -> List[float]:
        """Deterministic fake embedding."""
        import random
        # Seed with text hash for determinism
        random.seed(hash(text))
        return [random.uniform(-1, 1) for _ in range(self.dimension)]
    
    async def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Batch mock embeddings."""
        return [await self.embed(t) for t in texts]
    
    def get_dimension(self) -> int:
        return self.dimension
