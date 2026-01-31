"""
RAG Tools for Voice AI Agent

These tools integrate the Hub & Spoke RAG with the reservation agent.
"""
from typing import Optional
from .hub_spoke import HubSpokeRAG


class RAGTools:
    """
    RAG tools for voice AI function calling.
    
    This provides a simple interface for the agent to query knowledge.
    """
    
    def __init__(self, rag: Optional[HubSpokeRAG] = None):
        if rag is None:
            # Lazy initialization - will ingest on first use
            self.rag = None
        else:
            self.rag = rag
    
    async def _ensure_rag(self):
        """Ensure RAG is initialized."""
        if self.rag is None:
            self.rag = HubSpokeRAG()
            await self.rag.ingest_all()
    
    async def query_knowledge(
        self,
        question: str,
        location: Optional[str] = None
    ) -> dict:
        """
        Tool: Query hotel knowledge base.
        
        Use this when guests ask about:
        - Policies (check-in, pets, cancellation)
        - Amenities (pool, spa, dining)
        - Location-specific info (parking, attractions)
        - General hotel information
        
        Args:
            question: Guest's question
            location: Optional location context (chicago, ny, sf)
        
        Returns:
            Dict with answer context and sources
        """
        await self._ensure_rag()
        
        # Map location variations
        location = self._normalize_location(location)
        
        # Query RAG
        result = await self.rag.query(
            query=question,
            tenant_id=location,
            top_k=5
        )
        
        # Build response
        if not result.chunks:
            return {
                "found": False,
                "answer": "I don't have specific information about that. Let me connect you with the front desk.",
                "sources": []
            }
        
        # Combine chunks into answer
        answer_parts = []
        sources = []
        
        for r in result.chunks[:3]:  # Top 3
            answer_parts.append(r.chunk.content)
            source_type = "global policy" if r.source == "hub" else f"{r.chunk.tenant_id} location"
            sources.append(f"{r.chunk.category} ({source_type})")
        
        answer = " ".join(answer_parts)
        
        return {
            "found": True,
            "answer": answer,
            "sources": sources,
            "location": location or "global",
            "retrieved_chunks": len(result.chunks),
            "latency_ms": round(result.latency_ms, 1)
        }
    
    def _normalize_location(self, location: Optional[str]) -> Optional[str]:
        """Normalize location string to tenant_id."""
        if not location:
            return None
        
        location = location.lower().strip()
        
        mappings = {
            "chicago": "chicago",
            "chi": "chicago",
            "windy city": "chicago",
            "new york": "ny",
            "nyc": "ny",
            "new york city": "ny",
            "san francisco": "sf",
            "sf": "sf",
            "bay area": "sf",
        }
        
        return mappings.get(location, location)


# Tool schema for OpenAI function calling
RAG_TOOL_SCHEMA = {
    "type": "function",
    "name": "query_knowledge",
    "description": """Query the hotel knowledge base for policies, amenities, and location-specific information.
    
Use this tool when guests ask about:
- Hotel policies (check-in/out times, cancellation, pets)
- Amenities (pool, gym, spa, WiFi)
- Room features and pricing
- Dining options and room service
- Location-specific info (parking, attractions, weather)
- Safety protocols and accessibility

The tool automatically retrieves both global policies and location-specific details based on context.""",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The guest's question about hotel policies, amenities, or location info"
            },
            "location": {
                "type": "string",
                "description": "Optional: The hotel location (chicago, ny, sf). If not provided, uses global knowledge.",
                "enum": ["chicago", "ny", "sf"]
            }
        },
        "required": ["question"]
    }
}


# Example usage for reservation agent
EXAMPLE_RAG_QUERIES = [
    {
        "question": "What time is check-in?",
        "location": "chicago"
    },
    {
        "question": "Do you allow pets?",
        "location": None  # Global query
    },
    {
        "question": "How much is parking?",
        "location": "ny"
    },
    {
        "question": "What's your cancellation policy?",
        "location": None
    }
]
