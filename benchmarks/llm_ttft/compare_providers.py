"""
LLM Time-to-First-Token (TTFT) Benchmark

Compare TTFT across multiple LLM providers:
- OpenAI (GPT-4o, GPT-4o-mini, o1, etc.)
- Anthropic (Claude Sonnet, Haiku)
- Groq (Llama, Mixtral - blazing fast)
- Google (Gemini Pro/Flash)

Usage:
    uv run python benchmarks/llm_ttft/compare_providers.py

Results saved to: benchmarks/llm_ttft/results/ttft_results_{timestamp}.csv
"""

import asyncio
import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

# Provider SDK imports
from openai import AsyncOpenAI

# For Anthropic - will need: pip install anthropic
try:
    from anthropic import AsyncAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# For Groq - will need: pip install groq
try:
    from groq import AsyncGroq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

# For Google - will need: pip install google-generativeai
try:
    import google.generativeai as genai
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False


@dataclass
class TTFTResult:
    """Time-to-first-token measurement result."""
    provider: str
    model: str
    prompt_length: int
    ttft_ms: float
    total_tokens: int
    total_time_ms: float
    timestamp: str
    error: str | None = None


# Test prompts of varying complexity
TEST_PROMPTS = {
    "short": "What is 2+2?",
    "medium": "Explain the concept of async/await in Python in 2-3 sentences.",
    "long": """You are a voice AI assistant. A user just asked: "Can you help me book a flight from New York to San Francisco next Tuesday?"
    Please provide a helpful response that asks for necessary details like preferred time, airline preferences, and budget.""",
}


class ProviderBenchmark:
    """Base class for provider-specific benchmarks."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def measure_ttft(self, model: str, prompt: str) -> TTFTResult:
        """Measure TTFT for a given model and prompt."""
        raise NotImplementedError


class OpenAIBenchmark(ProviderBenchmark):
    """OpenAI TTFT benchmark."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = AsyncOpenAI(api_key=api_key)

    async def measure_ttft(self, model: str, prompt: str) -> TTFTResult:
        start_time = time.perf_counter()
        first_token_time = None
        total_tokens = 0

        try:
            stream = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=500,
            )

            async for chunk in stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()

                if chunk.choices[0].delta.content:
                    total_tokens += 1

            end_time = time.perf_counter()

            ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
            total_time_ms = (end_time - start_time) * 1000

            return TTFTResult(
                provider="openai",
                model=model,
                prompt_length=len(prompt),
                ttft_ms=round(ttft_ms, 2),
                total_tokens=total_tokens,
                total_time_ms=round(total_time_ms, 2),
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            return TTFTResult(
                provider="openai",
                model=model,
                prompt_length=len(prompt),
                ttft_ms=0,
                total_tokens=0,
                total_time_ms=0,
                timestamp=datetime.now().isoformat(),
                error=str(e),
            )


class AnthropicBenchmark(ProviderBenchmark):
    """Anthropic (Claude) TTFT benchmark."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package not installed. Run: uv add anthropic")
        self.client = AsyncAnthropic(api_key=api_key)

    async def measure_ttft(self, model: str, prompt: str) -> TTFTResult:
        start_time = time.perf_counter()
        first_token_time = None
        total_tokens = 0

        try:
            async with self.client.messages.stream(
                model=model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    total_tokens += 1

            end_time = time.perf_counter()

            ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
            total_time_ms = (end_time - start_time) * 1000

            return TTFTResult(
                provider="anthropic",
                model=model,
                prompt_length=len(prompt),
                ttft_ms=round(ttft_ms, 2),
                total_tokens=total_tokens,
                total_time_ms=round(total_time_ms, 2),
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            return TTFTResult(
                provider="anthropic",
                model=model,
                prompt_length=len(prompt),
                ttft_ms=0,
                total_tokens=0,
                total_time_ms=0,
                timestamp=datetime.now().isoformat(),
                error=str(e),
            )


class GroqBenchmark(ProviderBenchmark):
    """Groq TTFT benchmark (known for ultra-low latency)."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        if not HAS_GROQ:
            raise ImportError("groq package not installed. Run: uv add groq")
        self.client = AsyncGroq(api_key=api_key)

    async def measure_ttft(self, model: str, prompt: str) -> TTFTResult:
        start_time = time.perf_counter()
        first_token_time = None
        total_tokens = 0

        try:
            stream = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=500,
            )

            async for chunk in stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()

                if chunk.choices[0].delta.content:
                    total_tokens += 1

            end_time = time.perf_counter()

            ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
            total_time_ms = (end_time - start_time) * 1000

            return TTFTResult(
                provider="groq",
                model=model,
                prompt_length=len(prompt),
                ttft_ms=round(ttft_ms, 2),
                total_tokens=total_tokens,
                total_time_ms=round(total_time_ms, 2),
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            return TTFTResult(
                provider="groq",
                model=model,
                prompt_length=len(prompt),
                ttft_ms=0,
                total_tokens=0,
                total_time_ms=0,
                timestamp=datetime.now().isoformat(),
                error=str(e),
            )


# Provider configurations
PROVIDERS_TO_TEST = {
    "openai": {
        "enabled": True,
        "api_key_env": "OPENAI_API_KEY",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
        ],
    },
    "anthropic": {
        "enabled": False,  # Set to True when you add ANTHROPIC_API_KEY to .env
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-3-5-haiku-20241022",
        ],
    },
    "groq": {
        "enabled": False,  # Set to True when you add GROQ_API_KEY to .env
        "api_key_env": "GROQ_API_KEY",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
    },
}


async def run_benchmark(prompt_type: str = "medium", runs: int = 3):
    """
    Run TTFT benchmark across all enabled providers.

    Args:
        prompt_type: "short", "medium", or "long"
        runs: Number of times to run each test (for averaging)
    """
    prompt = TEST_PROMPTS[prompt_type]
    results = []

    print(f"\n{'='*80}")
    print(f"LLM Time-to-First-Token Benchmark")
    print(f"{'='*80}")
    print(f"Prompt type: {prompt_type}")
    print(f"Prompt length: {len(prompt)} chars")
    print(f"Runs per model: {runs}")
    print(f"{'='*80}\n")

    # OpenAI
    if PROVIDERS_TO_TEST["openai"]["enabled"]:
        api_key = os.getenv(PROVIDERS_TO_TEST["openai"]["api_key_env"])
        if api_key:
            benchmark = OpenAIBenchmark(api_key)
            for model in PROVIDERS_TO_TEST["openai"]["models"]:
                print(f"Testing OpenAI {model}...", end=" ", flush=True)
                for run in range(runs):
                    result = await benchmark.measure_ttft(model, prompt)
                    results.append(result)
                    if result.error:
                        print(f"❌ Error: {result.error}")
                    else:
                        print(f"✓ Run {run+1}: {result.ttft_ms}ms", end=" ", flush=True)
                print()

    # Anthropic
    if PROVIDERS_TO_TEST["anthropic"]["enabled"] and HAS_ANTHROPIC:
        api_key = os.getenv(PROVIDERS_TO_TEST["anthropic"]["api_key_env"])
        if api_key:
            benchmark = AnthropicBenchmark(api_key)
            for model in PROVIDERS_TO_TEST["anthropic"]["models"]:
                print(f"Testing Anthropic {model}...", end=" ", flush=True)
                for run in range(runs):
                    result = await benchmark.measure_ttft(model, prompt)
                    results.append(result)
                    if result.error:
                        print(f"❌ Error: {result.error}")
                    else:
                        print(f"✓ Run {run+1}: {result.ttft_ms}ms", end=" ", flush=True)
                print()

    # Groq
    if PROVIDERS_TO_TEST["groq"]["enabled"] and HAS_GROQ:
        api_key = os.getenv(PROVIDERS_TO_TEST["groq"]["api_key_env"])
        if api_key:
            benchmark = GroqBenchmark(api_key)
            for model in PROVIDERS_TO_TEST["groq"]["models"]:
                print(f"Testing Groq {model}...", end=" ", flush=True)
                for run in range(runs):
                    result = await benchmark.measure_ttft(model, prompt)
                    results.append(result)
                    if result.error:
                        print(f"❌ Error: {result.error}")
                    else:
                        print(f"✓ Run {run+1}: {result.ttft_ms}ms", end=" ", flush=True)
                print()

    # Save results
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"benchmarks/llm_ttft/results/ttft_results_{timestamp}.csv"

        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "provider", "model", "prompt_length", "ttft_ms",
                "total_tokens", "total_time_ms", "timestamp", "error"
            ])
            for result in results:
                writer.writerow([
                    result.provider,
                    result.model,
                    result.prompt_length,
                    result.ttft_ms,
                    result.total_tokens,
                    result.total_time_ms,
                    result.timestamp,
                    result.error or "",
                ])

        print(f"\n{'='*80}")
        print(f"✓ Results saved to: {output_file}")
        print_summary(results)
    else:
        print("\n⚠ No results to save. Check provider configuration and API keys.")


def print_summary(results: list[TTFTResult]):
    """Print a summary of TTFT results."""
    print(f"\n{'='*80}")
    print("TTFT Summary (averaged across runs)")
    print(f"{'='*80}")

    # Group by model
    model_results = {}
    for result in results:
        if result.error:
            continue
        key = f"{result.provider}/{result.model}"
        if key not in model_results:
            model_results[key] = []
        model_results[key].append(result.ttft_ms)

    # Calculate averages and print
    sorted_models = sorted(
        model_results.items(),
        key=lambda x: sum(x[1]) / len(x[1])  # Sort by avg TTFT
    )

    for model, ttfts in sorted_models:
        avg_ttft = sum(ttfts) / len(ttfts)
        min_ttft = min(ttfts)
        max_ttft = max(ttfts)
        print(f"{model:45} | Avg: {avg_ttft:6.1f}ms | Min: {min_ttft:6.1f}ms | Max: {max_ttft:6.1f}ms")

    print(f"{'='*80}\n")


async def main():
    """Run the benchmark."""
    # You can customize these parameters
    await run_benchmark(
        prompt_type="medium",  # "short", "medium", or "long"
        runs=3,  # Number of runs per model
    )


if __name__ == "__main__":
    asyncio.run(main())
