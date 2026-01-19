"""Test OpenAI LLM provider."""
import asyncio

from voice_ai.providers.llm.openai import OpenAILLM
from voice_ai.providers.llm.base import Message


async def main():
    print("Testing OpenAI LLM")
    print("=" * 50)

    llm = OpenAILLM(model="gpt-4o-mini", temperature=0.7, max_tokens=100)

    # Test 1: Simple completion
    print("\nTest 1: Simple completion")
    messages = [
        Message(role="system", content="You are helpful. Keep responses under 50 words."),
        Message(role="user", content="Explain what a voice AI agent is in one sentence."),
    ]

    response = await llm.complete(messages)
    print(f"✓ Response: {response.content}")

    # Test 2: Streaming
    print("\nTest 2: Streaming completion")
    messages = [
        Message(role="system", content="You are helpful. Keep responses concise."),
        Message(role="user", content="List 3 benefits of voice AI in bullet points."),
    ]

    print("✓ Streaming: ", end="", flush=True)
    async for chunk in llm.stream_complete(messages):
        print(chunk, end="", flush=True)
    print()

    print("\n" + "=" * 50)
    print("✓ LLM test complete!")


if __name__ == "__main__":
    asyncio.run(main())
