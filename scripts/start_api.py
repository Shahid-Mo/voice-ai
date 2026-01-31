#!/usr/bin/env python3
"""
Start the Reservation API server.

This is the backend for the dashboard. Must be running on port 8000
for the dashboard to display ticket data.

Usage:
    uv run scripts/start_api.py

Then open dashboard in another terminal:
    cd dashboard && npm run dev
"""
import sys
sys.path.insert(0, '/Users/shahid/dev/Projects/voice_ai/src')

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Black Lotus Reservation API")
    print("=" * 60)
    print()
    print("API will be available at: http://localhost:8000")
    print()
    print("Endpoints:")
    print("  - GET  /health           Health check")
    print("  - GET  /tickets          List all tickets")
    print("  - POST /tickets          Create new ticket")
    print("  - POST /tickets/{id}/approve   Approve ticket")
    print("  - POST /tickets/{id}/reject    Reject ticket")
    print("  - GET  /sync/status      Check ERP sync status")
    print("  - POST /sync             Trigger ERP sync")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    uvicorn.run(
        "reservation.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["/Users/shahid/dev/Projects/voice_ai/src"]
    )
