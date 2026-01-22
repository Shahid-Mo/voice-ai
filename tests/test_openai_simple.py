"""
Simple async test for OpenAI LLM using Conversations API.

Run: uv run python tests/test_openai_simple.py
Requires: OPENAI_API_KEY in .env
"""

import asyncio

from voice_ai.providers.llm.openai import OpenAILLM


async def main():
    """Test Conversations API for automatic state management using streaming."""
    print("Testing OpenAI LLM with Conversations API (streaming)...\n")

    # Initialize LLM
    llm = OpenAILLM(model="gpt-5-nano")

    # Create a persistent conversation
    print("Creating conversation...")
    conversation_id = await llm.create_conversation()
    print(f"✓ Created conversation: {conversation_id}\n")

    # First turn - tell the LLM something
    print("Turn 1: Telling LLM my favorite color...")
    print("Assistant: ", end="", flush=True)
    response1_text = ""
    async for chunk in llm.stream_complete(
        input="My favorite color is blue.",
        conversation_id=conversation_id,
    ):
        print(chunk, end="", flush=True)
        response1_text += chunk
    print("\n")

    # Second turn - ask about it (LLM should remember)
    print("Turn 2: Asking what my favorite color is...")
    print("Assistant: ", end="", flush=True)
    response2_text = ""
    async for chunk in llm.stream_complete(
        input="What is my favorite color?",
        conversation_id=conversation_id,
    ):
        print(chunk, end="", flush=True)
        response2_text += chunk
    print("\n")

    # Verify the LLM remembered
    if "blue" in response2_text.lower():
        print("✓ Success! LLM remembered the conversation context.")
    else:
        print("✗ LLM did not remember the context.")

    print(f"\nConversation ID: {conversation_id}")


if __name__ == "__main__":
    asyncio.run(main())
