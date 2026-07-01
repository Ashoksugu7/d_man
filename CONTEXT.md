# Virtual Try-On — Project Context (handoff)

Paste-ready context for a new chat / new contributor. Snapshot of architecture,
status, conventions, and what's pending.

## What it is
A garment virtual try-on app. Monorepo: **Next.js frontend + FastAPI backend**.
Two modes:
- **HD Image Try-On** — upload a photo → garment composited onto the body.
- **Live Preview** — webcam + in-browser MediaPipe pose → real-time overlay.

Plus body size estimation and a standalone keypoint annotation tool for adding
garments.

## Environment
- Working dir: `/Users/sugumarm/Projects/virtual_try_on/d_man`
- macOS, Apple Silicon (M1 Pro). Backend venv: `.venv/bin/python`.
- Frontend: Next.js 16, React 18, Tailwind, Zustand.

## Layout
- `frontend/` — Next.js (App Router). Key files:
  `components/LivePreview.tsx`, `components/ResultView.tsx`,
  `components/GarmentGrid.tsx`, `components/Gallery.tsx`,
  `lib/liveFit.ts` (affine/EMA/category helpers), `lib/api.ts`,
  `lib/store.ts`, `lib/gallery.ts`.
- `backend/app/` — FastAPI:
  - `main.py` — endpoints: `POST /api/tryon/image`, `POST/GET /api/tryon/hd`,
    `POST /api/measure`, `GET /api/garments`, `GET /api/health`, results/static.
  - `pose.py` — MediaPipe Pose + heuristic fallback; returns shoulders, elbows,
    wrists, hips, knees, ankles, neck, nose.
  - `warp.py` — affine warp; category dispatch (top/pant/skirt/lehenga/saree);
    occlusion + lighting + opt-in TPS; `warp_lehenga`/`warp_saree` multi-piece.
  - `measure.py` — size estimation + fit recommendation.
  - `inference.py` — HD engine interface + engines (see below).
  - `jobs.py` — Celery task `run_hd_tryon` (+ eager mode for tests).
  - `preprocess.py` — MediaPipe person silhouette + clothing-region mask.
- `assets/` — `catalog.json` + `garments/` (PNGs + keypoint JSON). Generators:
  `generate_shirts.py`, `generate_pants.py`, `generate_indian.py`,
  `generate_saree.py`. **Most garments are flat cartoon placeholders.**
- `tools/annotate.html` — standalone keypoint annotation tool.
- Docs: `PHASE3_NOTES.md`, `PHASE4_NOTES.md`, `PHASE5_NOTES.md`,
  `PHASE6_NOTES.md`, `assets/GARMENT_IMAGES.md`, `DEPLOY.md`, `BROWSER_QA.md`,
  `task.md` (roadmap/checklist).

## Status (Phases 1–6 of the affine pipeline are done)
- **P1 static image** — affine warp; 4-point least-squares; normalized,
  resolution-independent keypoints.
- **P2 live AR** — MediaPipe WASM, EMA smoothing, FPS meter, pose-debug +
  annotation-debug overlays, mirror, camera starts without a garment. Live uses
  a **3-point** affine (canvas `setTransform` is 2x3 = exactly 3 correspondences).
- **P3 HD async** — Celery + Redis, job status UI + progress bar, localStorage
  result gallery. **Pluggable engines** via `HD_ENGINE`:
  - `catvton` (default; real local VTON; needs `CATVTON_REPO` cloned) ·
  - `replicate` (hosted IDM-VTON; needs `REPLICATE_API_TOKEN`; paid) ·
  - `local` (diffusers SD1.5-inpaint + IP-Adapter; runs on MPS; moderate) ·
  - `stub` (CPU; reuses affine; dev/test fallback) ·
  - `idm_vton` (GPU scaffold).
- **P4 size estimation** — `/api/measure` + height input + fit badges on cards.
- **P5 Indian attire** — categories: kurta, salwar/palazzo, dupatta, skirt,
  lehenga (2-piece), saree (3-piece, **image-mode only**). Annotation tool has
  per-category schemes, multi-piece builder, auto-guess, drag-to-edit,
  image/json/catalog export, `fullsleeve` category.
- **P6 realism (no-GPU)** — hand/arm occlusion (`TRYON_OCCLUDE`, default on),
  lighting match (`TRYON_LIGHTING`), TPS warp opt-in (`TRYON_TPS`), dupatta
  on/off toggle.

## CRITICAL LEARNING
Output quality is gated by **garment image quality, not the model**. The
placeholder cartoon garments produce smears/blobs through any engine. Realistic
results need **real product photos** (single garment, front-facing, plain/white
background) run through CatVTON or Replicate. Affine = approximate; diffusion =
realistic but GPU-bound. See `assets/GARMENT_IMAGES.md`.

## Constraints / gotchas
- **Python 3.14 is NOT supported** — mediapipe (3.9–3.12 only) and opencv-python
  have no 3.14 wheels. Run the backend on **Python 3.12**. `requirements.txt`
  documents this (it has a "not yet 3.14-compatible" section).
- macOS Celery worker must use `--pool=solo` with
  `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES PYTORCH_ENABLE_MPS_FALLBACK=1`
  (else SIGABRT fork crash from MediaPipe/Torch).
- Redis runs in Docker; backend run locally against it.

## Run
```bash
# backend (Python 3.12 venv)
cd backend && uvicorn app.main:app --reload --port 8000
# HD worker (for /api/tryon/hd)
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES PYTORCH_ENABLE_MPS_FALLBACK=1 \
  celery -A app.jobs.celery_app worker --pool=solo --loglevel=info
# frontend
cd frontend && npm run dev
```
Tests (all pass): `python backend/test_pipeline.py`,
`python backend/test_measure.py`, `python backend/test_hd_jobs.py`.

## GIT POLICY — IMPORTANT
**Do NOT commit.** The user reviews and commits themselves. All recent work is
uncommitted in the working tree. The `frontend/next-env.d.ts`, `tsconfig.json`,
and `package.json` edits are the user's/linter's — leave them as-is.

## Pending (mostly GPU / data / device dependent)
- Real diffusion fidelity; DensePose + SCHP parsing; <15s target; ONNX/TensorRT.
- Phase 6: side-turn (±30° yaw); cloth-fold sim; video try-on MVP; diverse-body
  validation; perf profiling.
- Saree: paired dataset + learned pallu warp.
- Infra: prod GPU env, logging/monitoring, CDN, staging deploy creds.
- Real garment images; manual cross-browser QA (Chrome/Safari/Firefox).
- Small no-GPU option offered: upgrade live overlay from 3-point to 4-point
  least-squares affine to match the HD fit (debug would then show 4 anchors).
