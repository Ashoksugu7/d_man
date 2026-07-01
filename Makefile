# Virtual Try-On — dev shortcuts.
# Backend runs on Python 3.12 (mediapipe/opencv have no 3.14 wheels).
# Requires Redis for the HD worker (e.g. `docker run -p 6379:6379 redis:7`).

VENV ?= .venv312/bin
BACKEND := backend
FRONTEND := frontend
# macOS fork-safe flags for the Celery worker
WORKER_ENV := OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES PYTORCH_ENABLE_MPS_FALLBACK=1

.PHONY: help install seed api worker web dev test build

help:
	@echo "make install   # backend + frontend deps"
	@echo "make seed      # seed garment DB from catalog.json"
	@echo "make api       # FastAPI on :8000"
	@echo "make worker    # Celery HD worker (macOS-safe)"
	@echo "make web       # Next.js dev on :3000"
	@echo "make dev       # api + worker + web together"
	@echo "make test      # backend smoke tests"
	@echo "make build     # frontend production build"

install:
	cd $(BACKEND) && ../$(VENV)/pip install -r requirements.txt
	cd $(FRONTEND) && npm install

seed:
	cd $(BACKEND) && ../$(VENV)/python scripts/seed_garments.py

api:
	cd $(BACKEND) && ../$(VENV)/uvicorn app.main:app --reload --port 8000

worker:
	cd $(BACKEND) && $(WORKER_ENV) ../$(VENV)/celery -A app.jobs.celery_app worker --pool=solo --loglevel=info

web:
	cd $(FRONTEND) && npm run dev

# Run all three together (needs a shell with job control).
dev:
	@echo "Starting api + worker + web (Ctrl-C to stop all)…"
	@( $(MAKE) api & $(MAKE) worker & $(MAKE) web & wait )

test:
	cd $(BACKEND) && ../$(VENV)/python test_pipeline.py && \
	  ../$(VENV)/python test_measure.py && \
	  CELERY_TASK_ALWAYS_EAGER=1 ../$(VENV)/python test_hd_jobs.py

build:
	cd $(FRONTEND) && npm run build
