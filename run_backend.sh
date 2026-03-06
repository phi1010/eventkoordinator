#!/bin/bash
# Start the FastAPI backend server

cd "$(dirname "$0")"
uv run python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

