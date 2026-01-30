"""Seed script to populate demo data."""
import asyncio
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from .db import init_db, async_session
from .models import ShadowInventory, RoomType
from .mock_erp import MockERPClient
from .sync import ERPSyncService


async def seed_database():
    """Populate shadow DB with sample inventory."""
    print("🌱 Initializing database...")
    await init_db()
    
    async with async_session() as session:
        print("🔄 Syncing from mock ERP...")
        erp = MockERPClient(failure_rate=0.0)  # No failures for seeding
        sync_service = ERPSyncService(erp)
        
        status = await sync_service.sync_inventory(session, days_ahead=60)
        
        if status.status == "success":
            print(f"✅ Seeded {status.records_synced} inventory records")
            print(f"   Sync took {status.sync_duration_seconds:.2f}s")
        else:
            print(f"❌ Sync failed: {status.error_message}")


if __name__ == "__main__":
    asyncio.run(seed_database())
