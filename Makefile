PYTHON ?= /opt/homebrew/bin/python3.12
VENV   := .venv
BIN    := $(VENV)/bin
HOST   := 127.0.0.1
PORT   ?= 8765
NPM    := npm --prefix frontend
# CI installs dev only; the Mac adds ocr (Docling + macOS Vision OCR, pulls torch).
EXTRAS ?= dev,ocr

.PHONY: setup models build run dev test test-models lint verify

setup: ## Python 3.12 venv + backend deps + frontend deps
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e 'backend[$(EXTRAS)]'
	$(NPM) ci --no-audit --no-fund

models: ## One-time download of the Docling layout and table models (the only internet use)
	HF_HUB_DISABLE_TELEMETRY=1 $(BIN)/docling-tools models download layout tableformer -o models/docling

build: ## Build the UI into frontend/dist
	$(NPM) run build

run: build ## Build the UI and serve app + API on http://127.0.0.1:8765 (loopback only)
	cd backend && ../$(BIN)/uvicorn --factory app.main:create_app --host $(HOST) --port $(PORT)

dev: ## Backend with reload on :8765 + Vite dev server on :5173 (Ctrl+C stops both)
	trap 'kill 0' EXIT; \
	(cd backend && ../$(BIN)/uvicorn --factory app.main:create_app --host $(HOST) --port $(PORT) --reload) & \
	$(NPM) run dev

test: ## Backend tests (excludes tests that need the Docling models)
	$(BIN)/pytest backend -m "not models"

test-models: ## Backend tests that run Docling; needs `make models` first
	$(BIN)/pytest backend -m models

lint:
	$(BIN)/ruff check backend
	$(BIN)/ruff format --check backend

verify: lint test ## Full check sequence; CI runs exactly this
	$(NPM) run verify
