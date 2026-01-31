#!/usr/bin/env python3
"""
Test script for Reservation Agent with function calling.

This demonstrates custom function approach (teachable moment part 1).
Run this to verify the agent can query the DB and create tickets.
"""
import asyncio
import sys
sys.path.insert(0, '/Users/shahid/dev/Projects/voice_ai/src')

from datetime import date, timedelta

from voice_ai.services.reservation_agent import ReservationAgent
from reservation.tools import query_room_inventory, create_reservation_ticket, check_ticket_status
from reservation.db import init_db, close_db, async_session
from reservation.sync import ERPSyncService
from reservation.mock_erp import MockERPClient


class ToolRegistry:
    """Wraps DB tools with session management."""
    
    def __init__(self):
        self.session = None
        self.sync_service = None
        
    async def setup(self):
        """Initialize DB and create session."""
        await init_db()
        
        # Create session directly (no generator break issues)
        self.session = async_session()
        await self.session.__aenter__()
        
        # Setup sync service
        erp_client = MockERPClient(failure_rate=0.0)
        self.sync_service = ERPSyncService(erp_client)
        
        print("✓ Database connected (using pre-seeded data)")
        
    async def teardown(self):
        """Close session and cleanup."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
        await close_db()
        
    async def query_room_inventory(self, check_in: str, check_out: str, guests: int):
        """Tool wrapper: Check room availability."""
        return await query_room_inventory(
            session=self.session,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            sync_service=self.sync_service
        )
        
    async def create_reservation_ticket(
        self,
        guest_name: str,
        phone_number: str,
        check_in: str,
        check_out: str,
        room_type: str,
        guests: int,
        special_requests: str = ""
    ):
        """Tool wrapper: Create reservation ticket."""
        return await create_reservation_ticket(
            session=self.session,
            guest_name=guest_name,
            phone_number=phone_number,
            check_in=check_in,
            check_out=check_out,
            room_type=room_type,
            guests=guests,
            special_requests=special_requests,
            call_transcript="[Test conversation]"
        )
        
    async def check_ticket_status(self, ticket_id: str):
        """Tool wrapper: Check ticket status."""
        return await check_ticket_status(self.session, ticket_id)


async def test_conversation():
    """Run a test conversation with the agent."""
    print("=" * 60)
    print("🧪 Testing Reservation Agent with Custom Functions")
    print("=" * 60)
    
    registry = ToolRegistry()
    await registry.setup()
    
    try:
        agent = ReservationAgent()
        await agent.initialize()
        
        agent.register_tool("query_room_inventory", registry.query_room_inventory)
        agent.register_tool("create_reservation_ticket", registry.create_reservation_ticket)
        agent.register_tool("check_ticket_status", registry.check_ticket_status)
        
        check_in = (date.today() + timedelta(days=7)).isoformat()
        check_out = (date.today() + timedelta(days=10)).isoformat()
        
        # TEST 1: Check availability
        print()
        print("-" * 60)
        print("TEST 1: Check availability")
        print("-" * 60)
        
        user_input = f"What rooms do you have available from {check_in} to {check_out} for 2 guests?"
        print(f"\nUser: {user_input}")
        
        response = await agent.process(user_input)
        print(f"\nAI: {response}")
        
        # TEST 2: Create a reservation
        print()
        print("-" * 60)
        print("TEST 2: Create a reservation")
        print("-" * 60)
        
        user_input = (
            f"I'd like to book a deluxe room from {check_in} to {check_out} "
            f"for 2 guests. My name is John Doe and my phone is +1-555-123-4567."
        )
        print(f"\nUser: {user_input}")
        
        response = await agent.process(user_input)
        print(f"\nAI: {response}")
        
        # Extract ticket ID for next test
        import re
        ticket_match = re.search(r'LOTUS-\d+', response)
        if ticket_match:
            ticket_id = ticket_match.group()
            
            # TEST 3: Check ticket status
            print()
            print("-" * 60)
            print("TEST 3: Check ticket status")
            print("-" * 60)
            
            user_input = f"What's the status of my reservation {ticket_id}?"
            print(f"\nUser: {user_input}")
            
            response = await agent.process(user_input)
            print(f"\nAI: {response}")
        
        print()
        print("=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    finally:
        # Always cleanup, even if tests fail
        await registry.teardown()


async def interactive_mode():
    """Run interactive chat with the agent."""
    print("=" * 60)
    print("🎙️ Interactive Reservation Agent (Custom Functions)")
    print("=" * 60)
    print("Type 'quit' to exit\n")
    
    registry = ToolRegistry()
    await registry.setup()
    
    try:
        agent = ReservationAgent()
        await agent.initialize()
        
        agent.register_tool("query_room_inventory", registry.query_room_inventory)
        agent.register_tool("create_reservation_ticket", registry.create_reservation_ticket)
        agent.register_tool("check_ticket_status", registry.check_ticket_status)
        
        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in ('quit', 'exit', 'q'):
                break
                
            if not user_input:
                continue
                
            print("\nAI: ", end="", flush=True)
            response = await agent.process(user_input)
            print(response)
        
        print("\nGoodbye!")
        
    finally:
        await registry.teardown()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Reservation Agent")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    args = parser.parse_args()
    
    if args.interactive:
        asyncio.run(interactive_mode())
    else:
        asyncio.run(test_conversation())
