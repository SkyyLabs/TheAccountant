PYTHON ?= /opt/homebrew/bin/python3.12
VENV   := .venv
BIN    := $(VENV)/bin
HOST   := 127.0.0.1
PORT   ?= 8765

.PHONY: setup run dev test lint verify

setup: ## Create the venv on Python 3.12 and install backend dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e 'backend[dev]'

run: ## Serve the app on http://127.0.0.1:8765 (loopback only)
	cd backend && ../$(BIN)/uvicorn --factory app.main:create_app --host $(HOST) --port $(PORT)

dev: ## Backend with auto-reload
	cd backend && ../$(BIN)/uvicorn --factory app.main:create_app --host $(HOST) --port $(PORT) --reload

test: ## Backend tests
	$(BIN)/pytest backend

lint:
	$(BIN)/ruff check backend
	$(BIN)/ruff format --check backend

verify: lint test ## Full check sequence; CI runs exactly this
