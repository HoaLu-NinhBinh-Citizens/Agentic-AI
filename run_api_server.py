#!/usr/bin/env python3
"""Run the CARV API server for frontend dashboard integration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.application.api.app.api_server import run_server

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CARV API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8766, help="Port to bind to")
    args = parser.parse_args()
    
    print(f"Starting CARV API Server at http://{args.host}:{args.port}")
    print(f"WebSocket endpoint: ws://{args.host}:{args.port}/ws/stream")
    run_server(host=args.host, port=args.port)
