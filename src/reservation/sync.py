"""ERP Sync Service - protects the legacy ERP from voice AI load."""
import time
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ShadowInventory, SyncStatus
from .mock_erp import MockERPClient, ERPConnectionError


class ERPSyncService:
    """
    Hourly batch sync from ERP to Shadow DB.
    This is the critical protection layer:
    - Reads ERP in bulk (efficient)
    - One connection per hour vs. one per call
    - Handles ERP downtime gracefully (uses stale cache)
    """
    
    def __init__(self, erp_client: MockERPClient):
        self.erp = erp_client
    
    async def sync_inventory(
        self, 
        session: AsyncSession,
        days_ahead: int = 90
    ) -> SyncStatus:
        """
        Sync next N days of inventory from ERP to shadow DB.
        
        Args:
            session: Database session
            days_ahead: How many days to sync (default 90)
        
        Returns:
            SyncStatus record
        """
        start_time = time.time()
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        try:
            # Step 1: Bulk read from ERP (single efficient query)
            erp_data = await self.erp.get_inventory_bulk(start_date, end_date)
            
            # Step 2: Clear old data and insert fresh (simple approach for demo)
            # In production: use UPSERT to minimize writes
            await session.execute(delete(ShadowInventory))
            
            for item in erp_data:
                session.add(item)
            
            await session.commit()
            
            # Step 3: Record sync status
            duration = time.time() - start_time
            status = SyncStatus(
                last_sync_at=datetime.utcnow(),
                records_synced=len(erp_data),
                sync_duration_seconds=round(duration, 2),
                status="success"
            )
            session.add(status)
            await session.commit()
            
            return status
            
        except ERPConnectionError as e:
            # Graceful degradation: continue with stale cache
            duration = time.time() - start_time
            status = SyncStatus(
                last_sync_at=datetime.utcnow(),
                records_synced=0,
                sync_duration_seconds=round(duration, 2),
                status="failed",
                error_message=str(e)
            )
            session.add(status)
            await session.commit()
            
            # In production: alert ops team here
            return status
    
    async def get_last_sync(self, session: AsyncSession) -> Optional[SyncStatus]:
        """Get the most recent sync status."""
        result = await session.execute(
            select(SyncStatus).order_by(SyncStatus.last_sync_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
    
    def is_cache_fresh(self, sync_status: Optional[SyncStatus], max_age_minutes: int = 120) -> bool:
        """Check if cache is fresh enough to use."""
        if not sync_status:
            return False
        age = datetime.utcnow() - sync_status.last_sync_at
        return age < timedelta(minutes=max_age_minutes)
