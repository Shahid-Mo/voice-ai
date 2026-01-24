import time
import os
import numpy as np
from openai import OpenAI
from voice_ai.config import settings

# --- GROQ CONFIGURATION ---
CLIENT_CONFIG = {
    "api_key": settings.groq_api_key, 
    "base_url": "https://api.groq.com/openai/v1"
}

# The heavy hitters
MODELS = [
    "llama-3.1-8b-instant",      # The "Flash" (Expect 300+ t/s)
    "llama-3.3-70b-versatile"    # The "Brain" (Expect 80-100+ t/s)
]

PROMPTS = [
    "List 5 fun facts about space.",
    "Explain the concept of inflation in economics.",
    "Write a haiku about a rainy day in Tokyo.",
    "What are the main differences between Python and C++?",
    "Describe the plot of the movie 'The Matrix' in one sentence."
]

# Initialize Client
client = OpenAI(**CLIENT_CONFIG)

print(f"--- 🚀 GROQ SPEED TEST (PAID TIER) ---")

for model in MODELS:
    print(f"\n==========================================")
    print(f"🔥 MODEL: {model}")
    print(f"==========================================")
    
    ttft_results = []
    throughput_results = []

    # 1. WARMUP
    print(f"  [Warmup] Pinging server...")
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1
        )
    except Exception as e:
        print(f"  [Warmup Failed] {e}")
        continue

    # 2. BENCHMARK LOOP
    for i, prompt in enumerate(PROMPTS):
        start = time.perf_counter()
        first_token = None
        token_count = 0
        
        try:
            # Using standard chat.completions for maximum reliability
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=300 
            )
            
            for chunk in stream:
                # We check for content to ignore empty 'role' or 'usage' chunks
                if chunk.choices and chunk.choices[0].delta.content:
                    if first_token is None:
                        first_token = time.perf_counter()
                    token_count += 1
            
            end = time.perf_counter()
            
            if first_token:
                # TTFT (ms)
                ttft = (first_token - start) * 1000
                
                # Throughput (Tokens/sec)
                gen_time = end - first_token
                speed = (token_count - 1) / gen_time if gen_time > 0 else 0
                
                ttft_results.append(ttft)
                throughput_results.append(speed)
                print(f"  [Test {i+1}] TTFT: {ttft:.0f}ms | Speed: {speed:.1f} t/s")

        except Exception as e:
            print(f"  [Test {i+1} Failed] {e}")

    # 3. REPORT CARD
    if ttft_results:
        print(f"\n  📊 STATS FOR {model}:")
        print(f"  • Avg TTFT:    {np.mean(ttft_results):.2f} ms")
        print(f"  • P95 TTFT:    {np.percentile(ttft_results, 95):.2f} ms")
        print(f"  • Avg Speed:   {np.mean(throughput_results):.2f} tokens/s")
    else:
        print(f"  ❌ No Data Collected")

print("\n--- DONE ---")