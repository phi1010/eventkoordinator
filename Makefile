.PHONY: install dev backend frontend help clean

help:
	@echo "Available commands:"
	@echo "  make install     - Install all dependencies"
	@echo "  make dev         - Start both backend and frontend (requires 2 terminals)"
	@echo "  make backend     - Start backend only (port 8000)"
	@echo "  make frontend    - Start frontend only (port 5173)"
	@echo "  make clean       - Remove cache and build files"
	@echo ""
	@echo "Quick start (in 2 terminals):"
	@echo "  Terminal 1: make backend"
	@echo "  Terminal 2: make frontend"
	@echo ""
	@echo "Then open: http://localhost:5173"

install:
	@echo "Installing dependencies..."
	uv sync
	npm install
	@echo "✓ Dependencies installed"

backend:
	@echo "Starting FastAPI backend on http://localhost:8000"
	@echo "API endpoint: http://localhost:8000/api/events"
	@echo "API docs: http://localhost:8000/docs"
	@echo ""
	python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	@echo "Starting Vite frontend on http://localhost:5173"
	npm run dev

dev:
	@echo "To run both services, open 2 terminals:"
	@echo "  Terminal 1: make backend"
	@echo "  Terminal 2: make frontend"

clean:
	@echo "Cleaning cache and build files..."
	rm -rf dist/
	rm -rf .venv/
	rm -rf node_modules/
	rm -rf __pycache__/
	rm -rf backend/__pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned"

