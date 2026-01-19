"""OpenAI LLM provider using Responses API."""

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from voice_ai.config import settings
from voice_ai.providers.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    Tool,
    ToolCall,
)


class OpenAILLM(LLMProvider):
    """
    OpenAI LLM provider using the Responses API.

    The Responses API provides better conversation state management:
    - Use previous_response_id to chain responses
    - Use conversation_id for persistent conversations
    - Automatic context management
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
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

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert our Message format to OpenAI format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _convert_tools(self, tools: list[Tool] | None) -> list[dict[str, Any]] | None:
        """Convert our Tool format to OpenAI Responses API format."""
        if not tools:
            return None

        # Responses API format (same as Chat Completions)
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": True,  # Enable strict schema validation
            }
            for tool in tools
        ]

    def _extract_tool_calls(self, output: list[Any]) -> list[ToolCall]:
        """Extract tool calls from Responses API output."""
        tool_calls = []

        for item in output:
            # Check if this item has tool_calls
            if hasattr(item, "tool_calls") and item.tool_calls:
                for tc in item.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=json.loads(tc.function.arguments),
                        )
                    )

        return tool_calls

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        store: bool = False,
    ) -> LLMResponse:
        """
        Generate a completion using OpenAI Responses API.

        Args:
            messages: Conversation history
            tools: Optional list of tools the LLM can call
            previous_response_id: Chain to previous response for context
            conversation_id: Attach to persistent conversation
            store: Whether to store response for 30 days

        Returns:
            LLMResponse with content or tool calls
        """
        # Build request parameters
        params: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
        }

        # Add input - can be string or array
        if len(messages) == 1:
            params["input"] = messages[0].content
        else:
            params["input"] = self._convert_messages(messages)

        # Add optional parameters
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        if tools:
            params["tools"] = self._convert_tools(tools)

        if previous_response_id:
            params["previous_response_id"] = previous_response_id

        if conversation_id:
            params["conversation"] = conversation_id

        if store:
            params["store"] = True

        # Make request
        response = await self._client.responses.create(**params)

        # Extract content and tool calls
        content = getattr(response, "output_text", None)
        tool_calls = self._extract_tool_calls(response.output)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=getattr(response, "finish_reason", None),
            response_id=response.id,
            conversation_id=getattr(response, "conversation_id", None),
        )

    async def stream_complete(
        self,
        messages: list[Message],
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        store: bool = False,
    ) -> AsyncIterator[str]:
        """
        Stream a completion using OpenAI Responses API.

        Args:
            messages: Conversation history
            previous_response_id: Chain to previous response for context
            conversation_id: Attach to persistent conversation
            store: Whether to store response for 30 days

        Yields:
            Text chunks as they are generated
        """
        # Build request parameters
        params: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "stream": True,
        }

        # Add input
        if len(messages) == 1:
            params["input"] = messages[0].content
        else:
            params["input"] = self._convert_messages(messages)

        # Add optional parameters
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        if previous_response_id:
            params["previous_response_id"] = previous_response_id

        if conversation_id:
            params["conversation"] = conversation_id

        if store:
            params["store"] = True

        # Stream response
        stream = await self._client.responses.create(**params)

        async for chunk in stream:
            # Debug: Check what attributes the chunk has
            # print(f"\nChunk type: {type(chunk)}, attrs: {dir(chunk)}")

            # Try different ways to extract content from streaming chunks
            # Responses API might use different structure than Chat Completions

            # Try 1: Delta with content (Chat Completions style)
            if hasattr(chunk, "delta") and hasattr(chunk.delta, "content"):
                if chunk.delta.content:
                    yield chunk.delta.content
                    continue

            # Try 2: Direct content attribute
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content
                continue

            # Try 3: Choices array (Chat Completions style)
            if hasattr(chunk, "choices") and chunk.choices:
                if hasattr(chunk.choices[0], "delta"):
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        yield delta.content
                        continue
