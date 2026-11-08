PYTHON ?= /opt/homebrew/bin/python3.12
VENV   := .venv
BIN    := $(VENV)/bin
HOST   := 127.0.0.1
PORT   ?= 8765
NPM    := npm --prefix frontend

.PHONY: setup build run dev test lint verify

setup: ## Python 3.12 venv + backend deps + frontend deps
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e 'backend[dev]'
	$(NPM) ci --no-audit --no-fund

build: ## Build the UI into frontend/dist
	$(NPM) run build

run: build ## Build the UI and serve app + API on http://127.0.0.1:8765 (loopback only)
	cd backend && ../$(BIN)/uvicorn --factory app.main:create_app --host $(HOST) --port $(PORT)

dev: ## Backend with reload on :8765 + Vite dev server on :5173 (Ctrl+C stops both)
	trap 'kill 0' EXIT; \
	(cd backend && ../$(BIN)/uvicorn --factory app.main:create_app --host $(HOST) --port $(PORT) --reload) & \
	$(NPM) run dev

test: ## Backend tests
	$(BIN)/pytest backend

lint:
	$(BIN)/ruff check backend
	$(BIN)/ruff format --check backend

verify: lint test ## Full check sequence; CI runs exactly this
	$(NPM) run verify
