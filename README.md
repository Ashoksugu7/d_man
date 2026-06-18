# Virtual Try-On

A virtual try-on platform: upload a photo and see garments composited onto you
(HD image mode), or use a real-time webcam overlay (live mode). See
[`virtual_tryon_project_plan.md`](./virtual_tryon_project_plan.md) for the full
roadmap and [`task.md`](./task.md) for the task board.

## Sprint 1 status (Week 1–2) — ✅ complete

- Monorepo scaffold: Next.js 14 + FastAPI + Docker
- MediaPipe Pose in the browser (WASM) for the live overlay
- Static garment overlay on an uploaded photo (affine transform)
- 5 shirt PNG assets with keypoints
- Local end-to-end demo
- Staging config + CI ([`DEPLOY.md`](./DEPLOY.md))

## Layout

```
frontend/   Next.js 14 (App Router, Tailwind, Zustand) + MediaPipe WASM
backend/    FastAPI: pose (MediaPipe) → affine warp → composite
assets/     Garment PNGs + keypoint JSON + catalog.json (generate_shirts.py)
.github/    CI pipeline
```

## Run locally (Docker)

```bash
docker compose up --build
# frontend → http://localhost:3000
# backend  → http://localhost:8000  (/api/health, /api/garments)
```

## Run locally (no Docker)

```bash
# 1. Assets
cd assets && pip install pillow && python generate_shirts.py && cd ..

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# new terminal:

# 3. Frontend
cd frontend
npm install
npm run dev   # http://localhost:3000
```

## How the image pipeline works

1. `POST /api/tryon/image` receives the photo + `garment_id`.
2. MediaPipe Pose extracts shoulder/hip landmarks (heuristic fallback if
   MediaPipe is unavailable, so tests run anywhere).
3. A 2×3 affine transform maps the garment's shoulder/hem anchors onto the
   body landmarks (`backend/app/warp.py`).
4. The warped garment is alpha-composited and saved; the URL is returned.

TPS warping, human parsing, and diffusion try-on come in later phases.

## Test

```bash
python backend/test_pipeline.py   # synthetic person → overlay → assertion
```

## Image formats

PNG, JPEG, and **WebP** are supported for both uploaded photos and garment
assets (libwebp ships with Pillow and OpenCV). WebP garments may keep an alpha
channel for transparency. Results are PNG by default; pass `output_format=webp`
to `POST /api/tryon/image` for smaller WebP output.

## Replace placeholder garments

`assets/generate_shirts.py` produces simple flat-color shirts so the demo runs
end-to-end. Drop real transparent-background PNGs in `assets/garments/`, add
matching keypoint JSON (collar / shoulders / hem / sleeves) and a `catalog.json`
entry in the same format.

cd /Users/sugumarm/Projects/virtual_try_on/d_man/backend
./run_worker.sh
