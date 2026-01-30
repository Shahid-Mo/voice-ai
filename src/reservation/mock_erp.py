"""Mock ERP client - simulates the legacy hotel system."""
from datetime import date, timedelta
from random import choice, randint, uniform
from typing import List

from .models import ShadowInventory, RoomType


class MockERPClient:
    """
    Simulates a legacy hotel ERP that:
    - Can't handle real-time queries
    - Requires batch access only
    - Goes down sometimes (for demo purposes)
    """
    
    ROOM_CONFIG = {
        RoomType.STANDARD: {"count": 10, "base_rate": 129.00},
        RoomType.DELUXE: {"count": 6, "base_rate": 189.00},
        RoomType.SUITE: {"count": 3, "base_rate": 299.00},
    }
    
    AMENITIES = {
        RoomType.STANDARD: ["WiFi", "TV", "Coffee Maker"],
        RoomType.DELUXE: ["WiFi", "TV", "Coffee Maker", "City View", "Breakfast"],
        RoomType.SUITE: ["WiFi", "TV", "Coffee Maker", "City View", "Breakfast", "Living Room", "Mini Bar"],
    }
    
    def __init__(self, failure_rate: float = 0.0):
        """
        Args:
            failure_rate: 0.0-1.0 chance of simulated ERP failure
        """
        self.failure_rate = failure_rate
    
    async def get_inventory_bulk(
        self, 
        start_date: date, 
        end_date: date
    ) -> List[ShadowInventory]:
        """
        Bulk fetch inventory - simulates the ONLY way to read ERP.
        This is called hourly by the sync service, not per-call.
        """
        import random
        
        # Simulate ERP being down occasionally
        if random.random() < self.failure_rate:
            raise ERPConnectionError("ERP is down for maintenance (simulated)")
        
        inventory = []
        current = start_date
        
        while current <= end_date:
            for room_type, config in self.ROOM_CONFIG.items():
                # Generate type-level availability (simplified)
                # In reality, each room number would be tracked
                available_count = config["count"]
                
                # Simulate some bookings (randomly reduce availability)
                booked = randint(0, config["count"] // 3)
                is_available = (available_count - booked) > 0
                
                # Dynamic pricing simulation
                base_rate = config["base_rate"]
                # Weekend premium
                if current.weekday() >= 5:
                    base_rate *= 1.3
                # Seasonal variation
                base_rate *= uniform(0.9, 1.2)
                
                inventory.append(ShadowInventory(
                    room_type=room_type,
                    date=current,
                    is_available=is_available,
                    rate=round(base_rate, 2),
                    # room_number is None = aggregate availability
                ))
            
            current += timedelta(days=1)
        
        return inventory


class ERPConnectionError(Exception):
    """Simulated ERP connection failure."""
    pass
