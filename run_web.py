"""
Convenience script to run the web panel.

Usage:
    python run_web.py                    # default: localhost:8000
    python run_web.py --port 9000        # custom port
    python run_web.py --host 0.0.0.0     # expose to network

Or directly via uvicorn:
    uvicorn web.app:app --reload --port 8000
"""
from __future__ import annotations

import argparse
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run YT Anomaly Bot Web Panel")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    print(f"\n🚀  Web panel starting at http://{args.host}:{args.port}")
    print(f"📊  Dashboard: http://{args.host}:{args.port}/")
    print(f"📖  API docs:  http://{args.host}:{args.port}/api/docs\n")

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
