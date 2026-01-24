import time
import numpy as np
from openai import OpenAI
from voice_ai.config import settings

# --- CONFIGURATION ---
MODELS_TO_TEST = ["gpt-4.1","gpt-4o-mini","gpt-4.1-nano","gpt-5-nano"] 
# Winner *** gpt-4.1-nano ***
PROMPTS = [
    "List 5 fun facts about space.",
    "Explain the concept of inflation in economics.",
    "Write a haiku about a rainy day in Tokyo.",
    "What are the main differences between Python and C++?",
    "Describe the plot of the movie 'The Matrix' in one sentence."
]

WARMUP_PROMPT = "Say hello."
MAX_TOKENS = 100 

client = OpenAI(api_key=settings.openai_api_key)

# --- MAIN BENCHMARK LOOP ---
for model in MODELS_TO_TEST:
    print(f"\n==========================================")
    print(f"🤖 BENCHMARKING MODEL: {model}")
    print(f"==========================================")
    
    ttft_results = []
    throughput_results = []

    # 1. Warmup (Using your API)
    print(f"  [Warmup] Pinging server...")
    try:
        # We don't need to track time for warmup, just fire it
        with client.responses.stream(
            model=model,
            input=[{"role": "user", "content": WARMUP_PROMPT}],
        ) as stream:
            for event in stream:
                pass # Just consume the stream
    except Exception as e:
        print(f"  [Warmup Failed] {e}")
        continue

    # 2. Actual Testing
    for i, prompt in enumerate(PROMPTS):
        start_time = time.perf_counter()
        first_token_time = None
        token_count = 0
        
        try:
            with client.responses.stream(
                model=model,
                input=[{"role": "user", "content": prompt}],
            ) as stream:
                
                for event in stream:
                    # We only care about the text delta for metrics
                    if event.type == "response.output_text.delta":
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        
                        # Rough estimation: counts chunks. 
                        # For perfect accuracy you'd count actual tokens, but this is standard for stream benchmarking
                        token_count += 1 
                    
                    elif event.type == "response.error":
                         print(f"  [Error Event] {event.error}")

            end_time = time.perf_counter()
            
            # Calculations
            if first_token_time:
                ttft = (first_token_time - start_time) * 1000 # ms
                generation_time = end_time - first_token_time
                
                # Avoid div by zero
                tps = (token_count - 1) / generation_time if generation_time > 0 else 0
                
                ttft_results.append(ttft)
                throughput_results.append(tps)
                
                print(f"  [Test {i+1}] TTFT: {ttft:.0f}ms | Speed: {tps:.1f} chunks/s")
            
        except Exception as e:
            print(f"  [Test {i+1}] Failed: {e}")

    # 3. Model Report
    if ttft_results:
        mean_ttft = np.mean(ttft_results)
        sem_ttft = np.std(ttft_results) / np.sqrt(len(ttft_results))
        
        print(f"\n  📊 RESULTS FOR {model}:")
        print(f"  • Avg TTFT:    {mean_ttft:.2f} ms  (±{sem_ttft:.2f})")
        print(f"  • Avg Speed:   {np.mean(throughput_results):.2f} chunks/sec")
        print(f"  • P95 Latency: {np.percentile(ttft_results, 95):.2f} ms")
    else:
        print(f"  ❌ No data collected for {model}")

print("\n--- ALL BENCHMARKS COMPLETE ---")