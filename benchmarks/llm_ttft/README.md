# LLM Time-to-First-Token (TTFT) Benchmarks

Compare TTFT performance across multiple LLM providers to find the fastest option for voice AI applications.

## Quick Start

```bash
# 1. Add API keys to .env
echo "ANTHROPIC_API_KEY=your_key_here" >> .env
echo "GROQ_API_KEY=your_key_here" >> .env

# 2. Install optional provider SDKs (as needed)
uv add anthropic  # For Claude
uv add groq       # For Groq (ultra-low latency)

# 3. Run the benchmark
uv run python benchmarks/llm_ttft/compare_providers.py
```

## Configuration

Edit `compare_providers.py` to enable/disable providers:

```python
PROVIDERS_TO_TEST = {
    "openai": {
        "enabled": True,  # Already configured
        ...
    },
    "anthropic": {
        "enabled": True,  # Set to True after adding API key
        ...
    },
    "groq": {
        "enabled": True,  # Set to True after adding API key
        ...
    },
}
```

## Customization

```python
# In main() function
await run_benchmark(
    prompt_type="medium",  # "short", "medium", or "long"
    runs=5,                # Increase for more reliable averages
)
```

## Results

Results are saved to `results/ttft_results_{timestamp}.csv` with:
- Provider and model name
- TTFT in milliseconds
- Total tokens generated
- Total completion time
- Timestamp

## Adding More Providers

1. Create a new `XyzBenchmark` class
2. Implement `measure_ttft()` method
3. Add to `PROVIDERS_TO_TEST` config
4. Install SDK with `uv add xyz-sdk`

## Why TTFT Matters for Voice AI

In voice conversations, users notice delays > 300ms. TTFT directly impacts perceived responsiveness:
- **< 200ms**: Feels instant
- **200-500ms**: Acceptable
- **> 500ms**: Noticeable lag

Choose the fastest provider that meets your quality requirements.
