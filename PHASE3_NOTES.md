# Phase 3 — HD Diffusion Try-On (handoff)

Implemented the **full async architecture** (queue, endpoints, job-status UI,
result gallery) with a **CPU stub engine** so it runs and is verified today
without a GPU. The real diffusion model sits behind a clean interface and is the
only remaining GPU-dependent work. **All changes uncommitted** for review.

## What works now (verified)
- `POST /api/tryon/hd` enqueues a Celery job, returns `{job_id}`.
- `GET /api/tryon/hd/{job_id}` reports `status` + `progress` + result URL.
- Celery worker runs the job: pose → inference engine → saved result.
- Frontend: **HD render** button with a live progress bar (polls the job), and a
  **result gallery** (history) persisted in `localStorage`.
- `backend/test_hd_jobs.py` runs the whole task in eager mode (no Redis) — PASS.

## Files
- `backend/app/inference.py` — `InferenceEngine` interface; `StubEngine`
  (default, reuses the affine warp + light finishing); `IDMVTONEngine` (GPU
  stub with a step-by-step integration guide). Selected by `HD_ENGINE` env.
- `backend/app/jobs.py` — Celery app + `run_hd_tryon` task with progress
  reporting. Eager mode (`CELERY_TASK_ALWAYS_EAGER=1`) uses an in-memory result
  backend so it runs with no broker.
- `backend/app/main.py` — the two HD endpoints + an uploads dir.
- `backend/requirements.txt` — `celery`, `redis` added.
- `docker-compose.yml` — `redis` + `worker` services, shared result/upload
  volumes, `HD_ENGINE` env on the worker.
- Frontend: `lib/api.ts` (`submitHdJob`/`pollHdJob`), `lib/gallery.ts`
  (localStorage history), `components/Gallery.tsx`, `components/ResultView.tsx`
  (HD button + progress), `app/page.tsx` (gallery wired in).

## Run it
```bash
# with Docker (recommended — brings up redis + worker)
docker compose up --build      # backend :8000, worker, redis, frontend :3000

# or locally, 3 terminals from backend/ (venv):
redis-server                                   # 1) broker
celery -A app.jobs.celery_app worker --loglevel=info   # 2) worker
uvicorn app.main:app --reload                  # 3) API
# frontend: npm run dev
```
Test (no Redis needed): `python backend/test_hd_jobs.py`

## Remaining (GPU-only)
1. Implement `IDMVTONEngine` (see the guide in `inference.py`): load the
   pipeline once, compute DensePose + SCHP parsing + garment mask, run
   inference, return a BGR image. Set `HD_ENGINE=idm_vton`.
2. Provision a GPU host (≥8GB VRAM) and give the `worker` container GPU access.
3. Hit the <15s/image target; export to ONNX / TensorRT.

## Notes / decisions
- Stub engine intentionally reuses the affine pipeline so the async flow is
  testable and the UX is real; output quality is the affine look until the
  diffusion model is plugged in.
- Uploaded photos are stored under `backend/storage/uploads/` (gitignored) and
  shared with the worker via a compose volume. Add a retention/cleanup job for
  production.
- Job state uses Celery's result backend; for a multi-replica API add a shared
  Redis (already the default broker/back-end).
