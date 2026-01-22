"""OpenAI LLM provider using Responses API."""

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from voice_ai.config import settings


class OpenAILLM:
    """
    OpenAI LLM provider using the Responses API.

    The Responses API provides better conversation state management:
    - Create persistent conversations with create_conversation()
    - Pass conversation_id to automatically manage context
    - No need to manually track message history
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-5-nano",
        temperature: float = 1.0,
        max_tokens: int | None = None,
    ):
        """
        Initialize OpenAI LLM provider.

        Args:
            api_key: OpenAI API key (defaults to settings.openai_api_key)
            model: Model to use (default: gpt-4o-mini)
            temperature: Sampling temperature (0-2, default: 1.0)
            max_tokens: Max tokens to generate (None = model default)
        """
        self.api_key = api_key or settings.openai_api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._client = AsyncOpenAI(api_key=self.api_key)

    async def create_conversation(self) -> str:
        """
        Create a new persistent conversation.

        Returns:
            conversation_id: The ID of the created conversation

        Example:
            conversation_id = await llm.create_conversation()
            async for chunk in llm.stream_complete(
                input="Hello!",
                conversation_id=conversation_id
            ):
                print(chunk, end="")
        """
        conversation = await self._client.conversations.create()
        return conversation.id

    async def stream_complete(
        self,
        input: str | list[dict[str, str]],
        conversation_id: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a completion using OpenAI Responses API.

        Args:
            input: User message (string) or conversation history (list of dicts)
            conversation_id: Attach to persistent conversation for automatic state

        Yields:
            Text chunks as they are generated

        Example:
            async for chunk in llm.stream_complete("Tell me a story", conv_id):
                print(chunk, end="", flush=True)
        """
        params: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "input": input,
        }

        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        if conversation_id:
            params["conversation"] = conversation_id

        # Use SDK's stream context manager for proper event handling
        async with self._client.responses.stream(**params) as stream:
            async for event in stream:
                # Yield text deltas for voice output
                if event.type == "response.output_text.delta":
                    yield event.delta
                # Handle refusals (safety system blocked the request)
                elif event.type == "response.refusal.delta":
                    # For voice AI, you might want to yield a fallback phrase
                    pass
                # Handle errors
                elif event.type == "response.error":
                    # Could raise exception or yield error message
                    pass
