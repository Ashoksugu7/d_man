# Virtual Try-On

Try garments on a photo (HD image mode) or a live webcam overlay. Supports
shirts, t-shirts, full-sleeve shirts, pants, and Indian attire (kurta, salwar/
palazzo, dupatta, lehenga, saree). Garments live in a database and are managed
through an in-app annotator. Body size estimation gives fit recommendations.

## Features
- **HD Image Try-On** — upload a photo → garment composited on the body; async
  pipeline with pluggable engines (see below) + a result gallery.
- **Live Preview** — in-browser MediaPipe pose → real-time garment overlay
  (EMA-smoothed, FPS meter, pose + fit debug overlays).
- **Garment service** — Postgres-backed catalog; CRUD + image upload +
  keypoint annotation via API and the in-app **/manage** page (create, edit,
  archive).
- **Size estimation** — height-calibrated measurements → per-garment fit badges.
- **Realism (CPU)** — hand/arm occlusion, lighting match, optional TPS warp.

## Layout
```
frontend/   Next.js (App Router, Tailwind, Zustand) + MediaPipe WASM
              app/page.tsx (try-on), app/manage (garment manager)
backend/    FastAPI: pose (MediaPipe) → affine/category warp → composite
              app/db.py, models.py, garments_repo.py, garments_api.py (DB service)
              app/inference.py, jobs.py (HD engines + Celery)
assets/     Garment images + keypoint JSON + catalog.json (generated cache)
tools/      annotate.html (standalone annotator; superseded by /manage)
```

## HD engines (`HD_ENGINE`)
| value | where | notes |
|---|---|---|
| `catvton` (default) | MPS/CUDA | real VTON; needs `CATVTON_REPO` |
| `replicate` | cloud | hosted IDM-VTON; needs `REPLICATE_API_TOKEN` (paid) |
| `local` | MPS/CUDA | diffusers SD1.5-inpaint + IP-Adapter |
| `stub` | CPU | affine composite; instant, for wiring/tests |

## Requirements
- **Python 3.12** for the backend (mediapipe/opencv have no 3.14 wheels yet).
- Node 18+ for the frontend.
- **PostgreSQL** (garment DB) and **Redis** (HD job queue).

## Run (local)
```bash
cp backend/.env.example backend/.env      # adjust DATABASE_URL etc.
make install                              # backend + frontend deps
make seed                                 # import catalog.json → DB
make api                                  # FastAPI :8000
make worker                               # Celery HD worker (separate terminal)
make web                                  # Next.js :3000
# or: make dev   (runs all three)
```
Backend auto-creates the `vton_*` tables and seeds from `catalog.json` on start.

## Add a garment
Open **http://localhost:3000/manage** → New garment → upload a real product
image (plain/transparent background) → **Guess** keypoints then drag to adjust →
Create. It’s written to the DB and appears in the try-on grid immediately.
(Real garment photos matter — see `assets/GARMENT_IMAGES.md`.)

## Tests
```bash
make test    # backend smoke tests (pipeline, measure, HD jobs)
```

## More docs
`GARMENT_SERVICE_PLAN.md` (DB service phases), `PHASE3_NOTES.md`–`PHASE6_NOTES.md`,
`CONTEXT.md` (handoff), `BROWSER_QA.md`, `DEPLOY.md`, `task.md` (roadmap).
