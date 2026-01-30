"""SQLModel definitions for Black Lotus reservation system."""
from datetime import datetime, date, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine
from enum import Enum


class RoomType(str, Enum):
    STANDARD = "standard"
    DELUXE = "deluxe"
    SUITE = "suite"


class TicketStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ============================================================================
# SHADOW INVENTORY (ERP cache)
# ============================================================================

class ShadowInventory(SQLModel, table=True):
    """Cached room availability from ERP. Read-only for voice AI."""
    __tablename__ = "shadow_inventory"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    room_type: RoomType
    room_number: Optional[str] = None  # NULL = type-level availability
    date: date
    is_available: bool = True
    rate: float
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        json_schema_extra = {
            "example": {
                "room_type": "deluxe",
                "date": "2026-02-01",
                "is_available": True,
                "rate": 189.00
            }
        }


# ============================================================================
# RESERVATION TICKETS (Human review queue)
# ============================================================================

class ReservationTicket(SQLModel, table=True):
    """Tickets for human staff review. Created by voice AI."""
    __tablename__ = "reservation_tickets"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: str = Field(index=True, unique=True)  # Human-readable: LOTUS-001
    
    # Guest info (from voice call)
    guest_name: str
    phone_number: str
    
    # Reservation details
    check_in: date
    check_out: date
    room_type: RoomType
    guests: int
    special_requests: Optional[str] = None
    
    # Call metadata
    source: str = "voice_ai"
    call_transcript: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Staff workflow
    status: TicketStatus = TicketStatus.PENDING
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    staff_notes: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticket_id": "LOTUS-001",
                "guest_name": "Sarah Chen",
                "phone_number": "+1-555-987-6543",
                "check_in": "2026-02-01",
                "check_out": "2026-02-03",
                "room_type": "deluxe",
                "guests": 2,
                "status": "pending"
            }
        }


# ============================================================================
# SYNC STATUS (ERP protection layer)
# ============================================================================

class SyncStatus(SQLModel, table=True):
    """Tracks last ERP sync. Used for stale data warnings."""
    __tablename__ = "sync_status"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    last_sync_at: datetime
    records_synced: int
    sync_duration_seconds: float
    status: str  # 'success', 'partial', 'failed'
    error_message: Optional[str] = None


# ============================================================================
# API REQUEST/RESPONSE MODELS
# ============================================================================

class AvailabilityQuery(SQLModel):
    """Query params for checking availability."""
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=4)


class AvailabilityResponse(SQLModel):
    """Response for availability query."""
    room_type: RoomType
    available: bool
    rate_per_night: float
    total_nights: int
    total_estimate: float
    amenities: list[str]


class TicketCreate(SQLModel):
    """Create ticket from voice AI."""
    guest_name: str
    phone_number: str
    check_in: date
    check_out: date
    room_type: RoomType
    guests: int
    special_requests: Optional[str] = None
    call_transcript: Optional[str] = None


class TicketResponse(SQLModel):
    """Ticket response with computed fields."""
    ticket_id: str
    guest_name: str
    phone_number: str
    check_in: date
    check_out: date
    room_type: RoomType
    guests: int
    status: TicketStatus
    special_requests: Optional[str]
    created_at: datetime
    message: str  # Friendly message for voice AI to read
