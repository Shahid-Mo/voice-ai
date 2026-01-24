from voice_ai.config import settings
from openai import OpenAI

client = OpenAI(api_key=settings.openai_api_key)

print("--- STREAMING STARTED ---")

# 1. Remove 'text_format' to default to plain text
# 2. Use a prompt that forces long output (to create the time delay)
with client.responses.stream(
    model="gpt-4o",  # or your specific model
    input=[
        {
            "role": "user", 
            "content": "Tell me a long, 500-word story about a cyberpunk hacker."
        },
    ],
) as stream:
    for event in stream:
        # The event types might differ slightly based on your exact SDK version/beta,
        # but usually 'response.output_text.delta' is what carries the streaming tokens.
        if event.type == "response.output_text.delta":
            # flush=True is critical to force the text to appear character-by-character
            print(event.delta, end="", flush=True)
            
        elif event.type == "response.output_text.done":
            print("\n(Generation logic finished)")
            
        elif event.type == "response.done":
            print("\n--- COMPLETED ---")

final_response = stream.get_final_response()