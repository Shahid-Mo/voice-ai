"""Reservation Agent with function calling using OpenAI Responses API."""
import json
import logging
from typing import Callable

from voice_ai.providers.llm.openai import OpenAILLM

logger = logging.getLogger(__name__)


# Tool definitions for OpenAI function calling (Responses API format)
TOOLS = [
    {
        "type": "function",
        "name": "query_room_inventory",
        "description": "Check room availability for given dates. Returns available room types with rates and amenities. Use this when guests ask about availability or pricing.",
        "parameters": {
            "type": "object",
            "properties": {
                "check_in": {
                    "type": "string",
                    "description": "Check-in date in YYYY-MM-DD format (e.g., 2026-02-15)"
                },
                "check_out": {
                    "type": "string",
                    "description": "Check-out date in YYYY-MM-DD format (e.g., 2026-02-18)"
                },
                "guests": {
                    "type": "integer",
                    "description": "Number of guests (1-4)",
                    "minimum": 1,
                    "maximum": 4
                }
            },
            "required": ["check_in", "check_out", "guests"]
        }
    },
    {
        "type": "function",
        "name": "create_reservation_ticket",
        "description": "Create a reservation ticket for human staff review. Use this ONLY when the guest explicitly wants to book a room and has provided all required information: name, phone, dates, room type, and number of guests.",
        "parameters": {
            "type": "object",
            "properties": {
                "guest_name": {
                    "type": "string",
                    "description": "Guest's full name"
                },
                "phone_number": {
                    "type": "string",
                    "description": "Guest's phone number for callback (e.g., +1-555-123-4567)"
                },
                "check_in": {
                    "type": "string",
                    "description": "Check-in date in YYYY-MM-DD format"
                },
                "check_out": {
                    "type": "string",
                    "description": "Check-out date in YYYY-MM-DD format"
                },
                "room_type": {
                    "type": "string",
                    "enum": ["standard", "deluxe", "suite"],
                    "description": "Room type requested by guest"
                },
                "guests": {
                    "type": "integer",
                    "description": "Number of guests"
                },
                "special_requests": {
                    "type": "string",
                    "description": "Any special requests from the guest (optional)"
                }
            },
            "required": ["guest_name", "phone_number", "check_in", "check_out", "room_type", "guests"]
        }
    },
    {
        "type": "function",
        "name": "check_ticket_status",
        "description": "Check the status of an existing reservation ticket by ID. Use this when guests ask about their existing reservation.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The ticket ID (e.g., LOTUS-001)"
                }
            },
            "required": ["ticket_id"]
        }
    }
]


class ReservationAgent:
    """
    Agent that handles reservation conversations with database tool use.
    
    Uses OpenAI Responses API with function calling:
    1. Define tools (query_inventory, create_ticket, check_status)
    2. Send user input to model with tools
    3. Execute any function calls
    4. Return results to model for final response
    """
    
    def __init__(self):
        self.llm = OpenAILLM()
        self.tools: dict[str, Callable] = {}
        self.conversation_id: str | None = None
        
    def register_tool(self, name: str, handler: Callable):
        """Register a tool handler function."""
        self.tools[name] = handler
        logger.info(f"Registered tool: {name}")
        
    async def initialize(self):
        """Create a new conversation."""
        self.conversation_id = await self.llm.create_conversation()
        logger.info(f"Agent initialized with conversation: {self.conversation_id}")
        
    async def process(self, user_input: str) -> str:
        """
        Process user input with potential tool calls.
        
        Flow:
        1. Send input to model with available tools
        2. If tool calls returned, execute them
        3. Send tool results back to model
        4. Return final text response
        """
        from datetime import date
        
        # Build input list for Responses API
        input_list = [
            {
                "role": "system",
                "content": f"""You are a helpful hotel reservation assistant for Black Lotus Hotel.

Your job is to help guests with:
1. Checking room availability for specific dates
2. Creating reservation requests (these go to human staff for review)
3. Checking status of existing reservations

Key policies:
- Always confirm dates and guest count before checking availability
- Standard rooms fit 1-2 guests, Deluxe 2-3, Suite up to 4
- You CANNOT complete bookings directly - you only create tickets for staff review
- Staff will call back within 30 minutes to confirm and collect payment
- Be warm, professional, and efficient

Current date: {date.today().isoformat()}"""
            },
            {
                "role": "user",
                "content": user_input
            }
        ]
        
        # Step 1: Call model with tools (don't use conversation_id for tool calling flow)
        logger.info(f"Sending to model: {user_input[:60]}...")
        response = await self.llm._client.responses.create(
            model=self.llm.model,
            tools=TOOLS,
            input=input_list,
        )
        
        # Check if we got function calls
        function_calls = [item for item in response.output if item.type == "function_call"]
        
        if not function_calls:
            # No tools needed, return direct response
            logger.info("No function calls, returning direct response")
            return response.output_text
        
        logger.info(f"Model requested {len(function_calls)} function call(s)")
        
        # Step 2 & 3: Execute function calls and collect results
        # Build continuation input with tool calls and results
        continuation_input = []
        
        # Add the assistant's function call items only
        for item in response.output:
            if item.type == "function_call":
                continuation_input.append({
                    "type": item.type,
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments,
                })
        
        # Execute tools and add results
        for call in function_calls:
            func_name = call.name
            func_args = json.loads(call.arguments)
            
            logger.info(f"Executing: {func_name}({func_args})")
            
            if func_name in self.tools:
                try:
                    result = await self.tools[func_name](**func_args)
                    result_json = json.dumps(result)
                    logger.info(f"Tool result: {result_json[:200]}...")
                except Exception as e:
                    logger.error(f"Tool {func_name} failed: {e}")
                    result_json = json.dumps({"error": str(e)})
            else:
                logger.error(f"Tool {func_name} not registered")
                result_json = json.dumps({"error": f"Tool {func_name} not available"})
            
            # Add function result
            continuation_input.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": result_json
            })
        
        # Step 4: Call model again with tool results
        logger.info("Sending tool results back to model")
        final_response = await self.llm._client.responses.create(
            model=self.llm.model,
            tools=TOOLS,
            input=continuation_input,
        )
        
        return final_response.output_text
