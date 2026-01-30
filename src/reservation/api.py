"""FastAPI backend for Black Lotus reservation system."""
from datetime import date
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import init_db, close_db, get_session
from .models import (
    ReservationTicket, TicketStatus, SyncStatus,
    AvailabilityQuery, TicketCreate
)
from .tools import query_room_inventory, create_reservation_ticket, check_ticket_status
from .sync import ERPSyncService
from .mock_erp import MockERPClient


# Create app
app = FastAPI(
    title="Black Lotus Reservation API",
    description="Voice AI reservation system with ERP protection",
    version="1.0.0"
)

# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global sync service (initialized on startup)
sync_service: Optional[ERPSyncService] = None


@app.on_event("startup")
async def startup():
    """Initialize database and sync service."""
    await init_db()
    
    global sync_service
    erp_client = MockERPClient(failure_rate=0.1)  # 10% chance of failure for demo
    sync_service = ERPSyncService(erp_client)
    
    # Do initial sync
    async for session in get_session():
        await sync_service.sync_inventory(session, days_ahead=30)
        break


@app.on_event("shutdown")
async def shutdown():
    await close_db()


# =============================================================================
# INVENTORY ENDPOINTS (Read-only, used by voice AI)
# =============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "black-lotus-api"}


@app.get("/availability")
async def get_availability(
    check_in: date,
    check_out: date,
    guests: int = 2,
    session: AsyncSession = Depends(get_session)
):
    """
    Check room availability for given dates.
    Returns available room types with rates.
    """
    result = await query_room_inventory(
        session=session,
        check_in=check_in.isoformat(),
        check_out=check_out.isoformat(),
        guests=guests,
        sync_service=sync_service
    )
    return result


@app.get("/inventory")
async def get_inventory(
    room_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: AsyncSession = Depends(get_session)
):
    """Get raw inventory data (for debugging/admin)."""
    query = select(ReservationTicket)
    
    result = await session.execute(query)
    items = result.scalars().all()
    
    return {"inventory": items}


# =============================================================================
# TICKET ENDPOINTS (Human review workflow)
# =============================================================================

@app.get("/tickets")
async def list_tickets(
    status: Optional[TicketStatus] = None,
    session: AsyncSession = Depends(get_session)
) -> List[ReservationTicket]:
    """List all tickets, optionally filtered by status."""
    query = select(ReservationTicket)
    
    if status:
        query = query.where(ReservationTicket.status == status)
    
    query = query.order_by(ReservationTicket.created_at.desc())
    
    result = await session.execute(query)
    return result.scalars().all()


@app.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific ticket by ID."""
    result = await session.execute(
        select(ReservationTicket).where(ReservationTicket.ticket_id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    return ticket


@app.post("/tickets")
async def create_ticket(
    data: TicketCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new reservation ticket (called by voice AI)."""
    result = await create_reservation_ticket(
        session=session,
        guest_name=data.guest_name,
        phone_number=data.phone_number,
        check_in=data.check_in.isoformat(),
        check_out=data.check_out.isoformat(),
        room_type=data.room_type,
        guests=data.guests,
        special_requests=data.special_requests,
        call_transcript=data.call_transcript
    )
    return result


@app.post("/tickets/{ticket_id}/approve")
async def approve_ticket(
    ticket_id: str,
    staff_name: str = "Staff",
    session: AsyncSession = Depends(get_session)
):
    """Approve a ticket (staff action)."""
    from datetime import datetime
    
    result = await session.execute(
        select(ReservationTicket).where(ReservationTicket.ticket_id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket.status = TicketStatus.APPROVED
    ticket.reviewed_at = datetime.now(timezone.utc)
    ticket.reviewed_by = staff_name
    
    await session.commit()
    
    return {
        "ticket_id": ticket_id,
        "status": "approved",
        "message": f"Ticket {ticket_id} approved. Guest will be contacted for payment."
    }


@app.post("/tickets/{ticket_id}/reject")
async def reject_ticket(
    ticket_id: str,
    reason: str = "",
    staff_name: str = "Staff",
    session: AsyncSession = Depends(get_session)
):
    """Reject a ticket (staff action)."""
    from datetime import datetime
    
    result = await session.execute(
        select(ReservationTicket).where(ReservationTicket.ticket_id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket.status = TicketStatus.REJECTED
    ticket.reviewed_at = datetime.now(timezone.utc)
    ticket.reviewed_by = staff_name
    ticket.staff_notes = reason
    
    await session.commit()
    
    return {
        "ticket_id": ticket_id,
        "status": "rejected",
        "message": f"Ticket {ticket_id} rejected."
    }


# =============================================================================
# SYNC ENDPOINTS (ERP protection layer)
# =============================================================================

@app.post("/sync")
async def trigger_sync(
    days: int = 30,
    session: AsyncSession = Depends(get_session)
):
    """Manually trigger ERP sync (for demo/testing)."""
    status = await sync_service.sync_inventory(session, days_ahead=days)
    return {
        "synced": status.status == "success",
        "records_synced": status.records_synced,
        "duration_seconds": status.sync_duration_seconds,
        "last_sync": status.last_sync_at,
        "error": status.error_message
    }


@app.get("/sync/status")
async def get_sync_status(
    session: AsyncSession = Depends(get_session)
):
    """Get last sync status."""
    status = await sync_service.get_last_sync(session)
    
    if not status:
        return {"synced": False, "message": "No sync has been performed yet"}
    
    is_fresh = sync_service.is_cache_fresh(status, max_age_minutes=120)
    
    return {
        "synced": status.status == "success",
        "fresh": is_fresh,
        "last_sync": status.last_sync_at,
        "records_synced": status.records_synced,
        "duration_seconds": status.sync_duration_seconds,
        "error": status.error_message
    }


# =============================================================================
# VOICE AI TOOL ENDPOINTS (Direct function calls)
# =============================================================================

@app.post("/tools/query_inventory")
async def tool_query_inventory(
    query: AvailabilityQuery,
    session: AsyncSession = Depends(get_session)
):
    """Direct tool endpoint for voice AI to query inventory."""
    return await query_room_inventory(
        session=session,
        check_in=query.check_in.isoformat(),
        check_out=query.check_out.isoformat(),
        guests=query.guests,
        sync_service=sync_service
    )


@app.post("/tools/create_ticket")
async def tool_create_ticket(
    data: TicketCreate,
    session: AsyncSession = Depends(get_session)
):
    """Direct tool endpoint for voice AI to create ticket."""
    return await create_reservation_ticket(
        session=session,
        guest_name=data.guest_name,
        phone_number=data.phone_number,
        check_in=data.check_in.isoformat(),
        check_out=data.check_out.isoformat(),
        room_type=data.room_type,
        guests=data.guests,
        special_requests=data.special_requests,
        call_transcript=data.call_transcript
    )


@app.get("/tools/ticket_status/{ticket_id}")
async def tool_ticket_status(
    ticket_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Direct tool endpoint for voice AI to check ticket status."""
    return await check_ticket_status(session, ticket_id)
