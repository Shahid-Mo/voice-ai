"""
Ingestion Pipeline for Hub & Spoke RAG

Add new locations (spokes) or update existing knowledge.
"""
import json
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from .hub_spoke import HubSpokeRAG
from .models import IngestionRecord


class IngestionPipeline:
    """Pipeline for ingesting new knowledge into RAG."""
    
    def __init__(self, data_dir: str = "data/prod"):
        self.data_dir = Path(data_dir)
        self.rag = HubSpokeRAG(data_dir=data_dir)
    
    async def ingest_spoke(self, tenant_id: str, file_path: Optional[str] = None) -> IngestionRecord:
        """
        Ingest a new spoke (location).
        
        Args:
            tenant_id: Location identifier (e.g., "boston", "miami")
            file_path: Optional path to JSON file. If not provided, looks in data/prod/spokes/
        """
        record = IngestionRecord(
            tenant_id=tenant_id,
            file_path=file_path or f"data/prod/spokes/{tenant_id}.json",
            chunks_count=0,
            ingested_at=datetime.now(),
            status="pending"
        )
        
        try:
            # Determine file path
            if file_path is None:
                file_path = self.data_dir / "spokes" / f"{tenant_id}.json"
            else:
                file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"Spoke file not found: {file_path}")
            
            # Validate JSON structure
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Validate required fields
            for i, item in enumerate(data):
                if "id" not in item or "content" not in item:
                    raise ValueError(f"Item {i} missing required fields (id, content)")
                
                # Ensure tenant_id matches
                if "tenant_id" in item and item["tenant_id"] != tenant_id:
                    print(f"⚠️  Warning: Overriding tenant_id in {item['id']}")
                    item["tenant_id"] = tenant_id
            
            # Ingest
            chunks_count = await self.rag._ingest_file(file_path, tenant_id=tenant_id)
            
            record.chunks_count = chunks_count
            record.status = "success"
            record.file_path = str(file_path)
            
            print(f"✅ Ingested {chunks_count} chunks for {tenant_id}")
            
        except Exception as e:
            record.status = "failed"
            record.errors.append(str(e))
            print(f"❌ Failed to ingest {tenant_id}: {e}")
        
        return record
    
    async def ingest_hub(self, file_path: Optional[str] = None) -> IngestionRecord:
        """Ingest/update hub (global) knowledge."""
        record = IngestionRecord(
            tenant_id="hub",
            file_path=file_path or "data/prod/hub/global.json",
            chunks_count=0,
            ingested_at=datetime.now(),
            status="pending"
        )
        
        try:
            if file_path is None:
                file_path = self.data_dir / "hub" / "global.json"
            else:
                file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"Hub file not found: {file_path}")
            
            chunks_count = await self.rag._ingest_file(file_path, tenant_id=None)
            
            record.chunks_count = chunks_count
            record.status = "success"
            
            print(f"✅ Ingested {chunks_count} hub chunks")
            
        except Exception as e:
            record.status = "failed"
            record.errors.append(str(e))
            print(f"❌ Failed to ingest hub: {e}")
        
        return record
    
    async def full_reindex(self) -> dict:
        """Reindex all hub and spoke data."""
        print("🔄 Starting full reindex...")
        
        results = {
            "hub": None,
            "spokes": []
        }
        
        # Ingest hub
        hub_result = await self.ingest_hub()
        results["hub"] = hub_result
        
        # Ingest all spokes
        spokes_dir = self.data_dir / "spokes"
        if spokes_dir.exists():
            for spoke_file in spokes_dir.glob("*.json"):
                tenant_id = spoke_file.stem
                result = await self.ingest_spoke(tenant_id)
                results["spokes"].append(result)
        
        # Print summary
        print("\n" + "="*60)
        print("📊 INGESTION SUMMARY")
        print("="*60)
        
        total_chunks = results["hub"].chunks_count if results["hub"].status == "success" else 0
        total_chunks += sum(r.chunks_count for r in results["spokes"] if r.status == "success")
        
        print(f"Hub: {results['hub'].chunks_count} chunks ({results['hub'].status})")
        print(f"Spokes: {len(results['spokes'])} locations")
        for r in results["spokes"]:
            print(f"  - {r.tenant_id}: {r.chunks_count} chunks ({r.status})")
        print(f"\nTotal: {total_chunks} chunks indexed")
        
        return results


def create_spoke_template(tenant_id: str, output_dir: str = "data/prod/spokes"):
    """
    Create a template JSON file for a new spoke location.
    
    Usage:
        python -m rag.ingest --create-template boston
    """
    output_path = Path(output_dir) / f"{tenant_id}.json"
    
    if output_path.exists():
        print(f"⚠️  File already exists: {output_path}")
        return
    
    template = [
        {
            "id": f"{tenant_id}_001",
            "tenant_id": tenant_id,
            "content": f"Hotel Transylvania {tenant_id.title()} is located at [ADDRESS]. The phone number is [PHONE].",
            "category": "about",
            "metadata": {"type": "contact_address"}
        },
        {
            "id": f"{tenant_id}_002",
            "tenant_id": tenant_id,
            "content": "Check-in is at [TIME] and check-out is at [TIME].",
            "category": "policy",
            "metadata": {"type": "check_in_out_times"}
        },
        {
            "id": f"{tenant_id}_003",
            "tenant_id": tenant_id,
            "content": "This location has [NUMBER] rooms including [ROOM TYPES].",
            "category": "about",
            "metadata": {"type": "rooms_inventory"}
        },
        {
            "id": f"{tenant_id}_004",
            "tenant_id": tenant_id,
            "content": "Typical pricing ranges from $[MIN] to $[MAX] per night.",
            "category": "policy",
            "metadata": {"type": "pricing"}
        },
        {
            "id": f"{tenant_id}_005",
            "tenant_id": tenant_id,
            "content": "Nearby attractions include [ATTRACTIONS].",
            "category": "about",
            "metadata": {"type": "local_attractions"}
        }
    ]
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(template, f, indent=2)
    
    print(f"✅ Created template: {output_path}")
    print(f"📝 Edit this file and run: python -m rag.ingest --spoke {tenant_id}")


async def main():
    parser = argparse.ArgumentParser(description="RAG Ingestion Pipeline")
    parser.add_argument("--hub", action="store_true", help="Ingest hub (global) knowledge")
    parser.add_argument("--spoke", type=str, help="Ingest spoke by tenant_id (e.g., boston)")
    parser.add_argument("--reindex", action="store_true", help="Full reindex of all data")
    parser.add_argument("--create-template", type=str, help="Create template for new location")
    parser.add_argument("--file", type=str, help="Specific file to ingest")
    
    args = parser.parse_args()
    
    if args.create_template:
        create_spoke_template(args.create_template)
        return
    
    pipeline = IngestionPipeline()
    
    if args.reindex:
        await pipeline.full_reindex()
    elif args.hub:
        result = await pipeline.ingest_hub(args.file)
        print(f"Status: {result.status}, Chunks: {result.chunks_count}")
    elif args.spoke:
        result = await pipeline.ingest_spoke(args.spoke, args.file)
        print(f"Status: {result.status}, Chunks: {result.chunks_count}")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
