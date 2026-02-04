# Quick Start - Testing Voice AI with Twilio

## Prerequisites
- Twilio account with a phone number
- Deepgram API key
- OpenAI API key
- ngrok installed (`brew install ngrok` on Mac)

---

## Step 1: Check your .env file

Make sure `.env` has:
```bash
DEEPGRAM_API_KEY=your_deepgram_key_here
OPENAI_API_KEY=your_openai_key_here
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

---

## Step 2: Start the FastAPI server

**Terminal #1:**
```bash
uv run uvicorn voice_ai.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Keep this terminal running!

---

## Step 3: Start ngrok (expose your local server)

**Terminal #2:**
```bash
ngrok http 8000
```

You'll see something like:
```
Forwarding   https://abc123-456-xyz.ngrok-free.app -> http://localhost:8000
```

**Copy the HTTPS URL** (the one with `https://...ngrok-free.app`)

Example: `https://1234-56-789-012.ngrok-free.app`

Keep this terminal running too!

---

## Step 4: Configure Twilio

### Option A: Twilio Console (Web)
1. Go to https://console.twilio.com/
2. Navigate to **Phone Numbers** → **Manage** → **Active numbers**
3. Click on your phone number
4. Scroll down to **Voice Configuration**
5. Under "A CALL COMES IN":
   - Set to: **Webhook**
   - URL: `https://YOUR_NGROK_URL/incoming-call`
   - Method: **HTTP POST**

   Example:
   ```
   https://1234-56-789-012.ngrok-free.app/incoming-call
   ```

6. Click **Save**

### Option B: Twilio CLI
```bash
twilio phone-numbers:update <YOUR_TWILIO_NUMBER> \
  --voice-url="https://YOUR_NGROK_URL/incoming-call"
```

---

## Step 6: Test it!

**Call your Twilio number from your phone**

You should hear:
> "Welcome to Hotel Continental. I am John, your virtual assistant. How may I help you today?"

Then you can talk to the AI!

---

## Checking logs

### FastAPI server (Terminal #1) should show:
```
INFO:     Twilio call connected
INFO:     Stream started: MZ...
INFO:     📞 Stream SID: MZ...
INFO:     🎙️  Sending greeting: 'Welcome to Hotel Continental...'
INFO:     ✓ Greeting sent
INFO:     🎤 Ready - listening for audio
```

### ngrok (Terminal #2) should show:
```
POST /incoming-call              200 OK
GET  /ws/twilio                  101 Switching Protocols
```

---

## Troubleshooting

### Connection refused
**Solution**: Make sure FastAPI server (Terminal #1) is running

### No greeting heard
**Solution**:
1. Check FastAPI logs for errors
2. Verify Deepgram API key is valid
3. Check ngrok is forwarding correctly

### Twilio: "Application error has occurred"
**Solution**:
1. Verify ngrok URL in Twilio includes `/incoming-call`
2. Make sure ngrok is running
3. Check FastAPI logs

### ngrok URL keeps changing
**Solution**:
- Free ngrok URLs change on restart
- Update Twilio webhook each time you restart ngrok
- OR: Get ngrok paid plan for static domain

---

## Quick Commands

```bash
# Terminal 1: Start server
uv run uvicorn voice_ai.main:app --reload

# Terminal 2: Start ngrok
ngrok http 8000

# Configure Twilio with:
https://YOUR_NGROK_URL/incoming-call
```

---

## Customizing the Greeting

Edit `src/voice_ai/api/routes/voice_ws.py` line 150:
```python
greeting = "Your custom message here"
```

Change voice (line 155):
```python
model="aura-2-arcas-en",  # Male voice
# or
model="aura-2-thalia-en",  # Female voice (default)
```

Available voices:
- `aura-2-thalia-en` - Female, friendly
- `aura-2-arcas-en` - Male, professional
- `aura-2-luna-en` - Female, warm
- `aura-2-stella-en` - Female, clear

---

## Stopping

Press `Ctrl+C` in both terminals to stop the server and ngrok.
