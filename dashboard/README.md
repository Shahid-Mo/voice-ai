# Black Lotus Dashboard

Staff dashboard for managing voice AI reservation requests.

## Quick Start

You need **two terminals** - one for the API, one for the dashboard.

### Terminal 1: Start the API (Port 8000)

```bash
# From project root
uv run scripts/start_api.py
```

You should see:
```
🚀 Starting Black Lotus Reservation API
API will be available at: http://localhost:8000
```

### Terminal 2: Start the Dashboard (Port 5173)

```bash
# From project root
cd dashboard
npm run dev
```

You should see:
```
VITE v7.3.1  ready in 638 ms
➜  Local:   http://localhost:5173/
```

### Open Dashboard

Go to: **http://localhost:5173**

---

## Architecture

```
┌─────────────────┐      HTTP/REST       ┌─────────────────┐
│   Dashboard     │ ◄──────────────────► │  Reservation    │
│  (SvelteKit)    │   Port 8000          │   API (FastAPI) │
│   Port 5173     │                      │   Port 8000     │
└─────────────────┘                      └────────┬────────┘
                                                  │
                                                  ▼
                                         ┌─────────────────┐
                                         │   PostgreSQL    │
                                         │    Database     │
                                         └─────────────────┘
```

## Dashboard Features

- **Auto-refresh**: Updates every 5 seconds
- **Filter tickets**: pending, approved, rejected, all
- **Approve/Reject**: Staff actions on pending tickets
- **Sync status**: Shows if ERP data is fresh/stale
- **Manual sync**: Trigger ERP sync from UI

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/tickets` | List all tickets |
| GET | `/tickets/{id}` | Get specific ticket |
| POST | `/tickets` | Create ticket (voice AI) |
| POST | `/tickets/{id}/approve` | Approve ticket |
| POST | `/tickets/{id}/reject` | Reject ticket |
| GET | `/sync/status` | Check sync status |
| POST | `/sync` | Trigger ERP sync |

## Troubleshooting

### "Failed to fetch tickets" in browser console

**Problem**: API is not running on port 8000

**Fix**:
```bash
# Check if API is running
curl http://localhost:8000/health

# If no response, start it:
uv run scripts/start_api.py
```

### Dashboard shows "No pending tickets" but should have data

**Problem**: Database might be empty

**Fix**: Run the test script to seed tickets:
```bash
uv run scripts/test_agent_tools.py
```

### CORS errors in browser

The API already has CORS configured for `*`. If you see CORS errors, check that you're accessing the dashboard via `http://localhost:5173` (not `127.0.0.1` or other variations).
