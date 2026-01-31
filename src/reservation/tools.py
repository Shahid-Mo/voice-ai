"""LLM Tool Functions - these are called by the Voice AI."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ShadowInventory, ReservationTicket, TicketStatus,
    AvailabilityQuery, AvailabilityResponse, RoomType
)
from .sync import ERPSyncService


async def query_room_inventory(
    session: AsyncSession,
    check_in: str,
    check_out: str,
    guests: int,
    sync_service: ERPSyncService
) -> dict:
    """
    Tool: Check room availability from shadow database.
    
    Why this matters:
    - Real-time response to caller
    - No ERP load (reads from cache)
    - Can handle concurrent calls
    
    Args:
        session: Database session
        check_in: Check-in date (YYYY-MM-DD)
        check_out: Check-out date (YYYY-MM-DD)
        guests: Number of guests (1-4)
        sync_service: For checking cache freshness
    
    Returns:
        Dict with available rooms and metadata for LLM
    """
    # Parse dates
    check_in_date = date.fromisoformat(check_in)
    check_out_date = date.fromisoformat(check_out)
    nights = (check_out_date - check_in_date).days
    
    if nights <= 0:
        return {
            "error": "Check-out must be after check-in",
            "available_rooms": []
        }
    
    # Check cache freshness
    last_sync = await sync_service.get_last_sync(session)
    cache_fresh = sync_service.is_cache_fresh(last_sync, max_age_minutes=120)
    
    # Query availability for date range
    available_rooms = []
    
    for room_type in RoomType:
        # Check if room type is available for ALL nights
        result = await session.execute(
            select(ShadowInventory).where(
                and_(
                    ShadowInventory.room_type == room_type,
                    ShadowInventory.date >= check_in_date,
                    ShadowInventory.date < check_out_date,
                    ShadowInventory.is_available == True
                )
            )
        )
        inventory_items = result.scalars().all()
        
        # Must have availability for every night
        if len(inventory_items) == nights:
            # Get average rate
            avg_rate = sum(item.rate for item in inventory_items) / nights
            total_estimate = sum(item.rate for item in inventory_items)
            
            # Get amenities (from first item's room type)
            amenities = _get_amenities(room_type)
            
            available_rooms.append({
                "room_type": room_type.value,
                "available": True,
                "rate_per_night": round(avg_rate, 2),
                "total_nights": nights,
                "total_estimate": round(total_estimate, 2),
                "amenities": amenities
            })
    
    # Build LLM-friendly response
    response = {
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "available_rooms": available_rooms,
        "cache_info": {
            "fresh": cache_fresh,
            "last_sync": last_sync.last_sync_at.isoformat() if last_sync else None,
            "warning": None if cache_fresh else "Data may be stale - confirming with staff"
        }
    }
    
    return response


async def create_reservation_ticket(
    session: AsyncSession,
    guest_name: str,
    phone_number: str,
    check_in: str,
    check_out: str,
    room_type: str,
    guests: int,
    special_requests: str = "",
    call_transcript: str = ""
) -> dict:
    """
    Tool: Create a ticket for human staff review.
    
    Why this matters:
    - Protects ERP from direct writes
    - Creates audit trail
    - Allows human judgment (overbooking, VIP handling)
    
    Args:
        session: Database session
        guest_name: Guest's full name
        phone_number: Callback number
        check_in: Check-in date (YYYY-MM-DD)
        check_out: Check-out date (YYYY-MM-DD)
        room_type: Room type requested
        guests: Number of guests
        special_requests: Any special requests
        call_transcript: Full conversation log
    
    Returns:
        Dict with ticket info and friendly message for voice AI
    """
    # Generate ticket ID
    result = await session.execute(
        select(ReservationTicket).order_by(ReservationTicket.id.desc()).limit(1)
    )
    last_ticket = result.scalar_one_or_none()
    next_num = 1 if not last_ticket else last_ticket.id + 1
    ticket_id = f"LOTUS-{next_num:04d}"
    
    # Create ticket
    ticket = ReservationTicket(
        ticket_id=ticket_id,
        guest_name=guest_name,
        phone_number=phone_number,
        check_in=date.fromisoformat(check_in),
        check_out=date.fromisoformat(check_out),
        room_type=room_type,
        guests=guests,
        special_requests=special_requests or None,
        call_transcript=call_transcript or None,
        status=TicketStatus.PENDING
    )
    
    session.add(ticket)
    await session.commit()
    
    # Build friendly response for voice AI to read
    nights = (ticket.check_out - ticket.check_in).days
    
    message = (
        f"Thank you {guest_name}! I've submitted your reservation request as ticket {ticket_id}. "
        f"You requested a {room_type} room for {nights} night{'s' if nights > 1 else ''} "
        f"from {check_in} to {check_out}. "
        f"Our front desk team will review and confirm within 30 minutes, "
        f"and call you back at {phone_number} to finalize payment. "
    )
    
    if special_requests:
        message += f"I've noted your special request: {special_requests}. "
    
    message += "Is there anything else I can help you with?"
    
    return {
        "ticket_id": ticket_id,
        "status": "pending",
        "message": message,
        "expected_response_time": "30 minutes",
        "next_steps": "Staff will call to confirm and collect payment"
    }


async def check_ticket_status(
    session: AsyncSession,
    ticket_id: str
) -> dict:
    """
    Tool: Check status of an existing ticket.
    Used when caller asks "What's the status of my reservation?"
    """
    result = await session.execute(
        select(ReservationTicket).where(ReservationTicket.ticket_id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        return {
            "found": False,
            "message": f"I couldn't find a ticket with ID {ticket_id}. Please double-check the number."
        }
    
    status_messages = {
        TicketStatus.PENDING: f"Ticket {ticket_id} is still being reviewed by our staff. You should receive a callback soon.",
        TicketStatus.APPROVED: f"Great news! Ticket {ticket_id} has been approved. Our staff will call you shortly to collect payment information.",
        TicketStatus.REJECTED: f"I see ticket {ticket_id} could not be approved as requested. Our staff will call you to discuss alternatives."
    }
    
    return {
        "found": True,
        "ticket_id": ticket.ticket_id,
        "status": ticket.status.value,
        "guest_name": ticket.guest_name,
        "check_in": ticket.check_in.isoformat(),
        "check_out": ticket.check_out.isoformat(),
        "room_type": ticket.room_type.value,
        "message": status_messages.get(ticket.status, "Status unknown.")
    }


def _get_amenities(room_type: RoomType) -> List[str]:
    """Get amenities for room type."""
    amenities_map = {
        RoomType.STANDARD: ["WiFi", "TV", "Coffee Maker"],
        RoomType.DELUXE: ["WiFi", "TV", "Coffee Maker", "City View", "Complimentary Breakfast"],
        RoomType.SUITE: ["WiFi", "TV", "Coffee Maker", "City View", "Complimentary Breakfast", "Living Room", "Mini Bar"],
    }
    return amenities_map.get(room_type, ["WiFi"])
