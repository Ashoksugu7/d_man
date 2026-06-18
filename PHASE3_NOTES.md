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

## The models, in plain terms (why each exists)

- **IDM-VTON / CatVTON** — diffusion *virtual try-on* models. Given a person
  photo + a garment image, they *generate* a new photo of that person wearing
  the garment (correct drape, folds, shadows) instead of pasting a flat image.
  They're alternatives; CatVTON is lighter, IDM-VTON higher fidelity.
- **DensePose** — preprocessing: labels every body pixel with its location on a
  3D body surface (a UV map) so the model knows the body's shape/orientation.
- **SCHP / human parsing** — preprocessing: segments the person into regions
  (torso, arms, hair, …) so the model knows where the garment goes and what to
  keep (face, hands).

Pipeline: `photo → DensePose + parsing → (+ garment) → IDM-VTON/CatVTON → result`.

## Engines (HD_ENGINE)

| HD_ENGINE  | Where it runs        | Needs                       | Notes |
|------------|----------------------|-----------------------------|-------|
| `stub`     | CPU (default)        | nothing                     | Reuses the affine warp; for dev/testing the pipeline. |
| `replicate`| Cloud (hosted)       | `REPLICATE_API_TOKEN`, `pip install replicate` | **Recommended for Macs / no GPU.** Real IDM-VTON output, paid per call. |
| `local`    | Local MPS/CUDA/CPU   | torch + diffusers (+downloads) | **Runs on Apple Silicon.** diffusers SD1.5-inpaint + IP-Adapter; mask from MediaPipe (no detectron2). Moderate quality. |
| `catvton`  | Local MPS/CUDA/CPU   | torch + diffusers + CatVTON repo | **Real VTON, Mac-runnable.** True garment transfer; uses our MediaPipe mask (no detectron2). Best local quality. |
| `idm_vton` | Local GPU            | torch + weights + parsing   | Official-pipeline scaffold; CUDA-first, hard on Mac. |

### Use the hosted (Replicate) engine — easiest real HD, any machine
```bash
pip install -r backend/requirements-hd.txt        # installs `replicate`
export REPLICATE_API_TOKEN=<your token>           # replicate.com/account
export HD_ENGINE=replicate
# restart the API + worker; click "HD render" — output comes from IDM-VTON.
```
Optional: `REPLICATE_IDM_VTON_VERSION` (pin a version), `HD_STEPS`, `HD_SEED`.
The engine encodes the person + garment, calls `cuuupid/idm-vton`, maps our
category → `upper_body|lower_body|dresses`, and downloads the result. It needs
no DensePose/SCHP locally — the hosted model does all preprocessing.

### Local engine on a Mac (Apple Silicon) — `HD_ENGINE=local`
A real, fully-local diffusion try-on that runs on the Mac GPU (MPS). It uses a
Stable-Diffusion-1.5 **inpainting** pipeline + **IP-Adapter** (conditions on the
garment image), and builds the clothing mask from **MediaPipe** (`preprocess.py`)
so it needs **no detectron2 / DensePose / SCHP** — that's what makes it
Mac-installable.

```bash
# from backend/, in your venv
pip install -r requirements-hd.txt        # torch, diffusers, transformers, ...
export HD_ENGINE=local
# start worker with the macOS fork-safe flags (see below) + the API, then
# click "HD render". First run downloads ~2-3GB of weights (SD1.5 + IP-Adapter).
```

macOS worker (avoid the SIGABRT fork crash — torch/mediapipe + fork):
```bash
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES PYTORCH_ENABLE_MPS_FALLBACK=1 \
  celery -A app.jobs.celery_app worker --pool=solo --loglevel=info
```
`PYTORCH_ENABLE_MPS_FALLBACK=1` lets any op MPS doesn't support fall back to CPU
instead of erroring.

Tunables (env): `HD_STEPS` (default 30), `HD_GUIDANCE` (7.0),
`HD_IPADAPTER_SCALE` (0.7 — higher = follow the garment more),
`HD_BASE_MODEL`, `HD_SEED`.

How it works: `photo → MediaPipe mask (torso/legs) → SD1.5 inpaint the masked
region, IP-Adapter conditioned on the garment → result`. Expect tens of seconds
per image on MPS (slower than CUDA). Quality is moderate — a pragmatic local
path, not full IDM-VTON fidelity. If results are weak, raise
`HD_IPADAPTER_SCALE` toward 0.9 and `HD_STEPS` toward 40.

**Unverified here:** I can't run torch/weights in this environment, so the local
engine ships for you to run. I validated the wiring, device auto-detection, the
mask builder (visualized), and that the base app is unaffected. First run will
confirm the diffusers/IP-Adapter calls on your machine.

Intel Macs: no usable GPU — CPU-only diffusion is impractically slow.

### CatVTON — real local try-on (recommended local path) — `HD_ENGINE=catvton`
The `local` IP-Adapter engine only *style-conditions* — it can't drape a
specific garment (it invents a shirt or pastes the flat image). **CatVTON** is a
true VTON diffusion model that actually transfers the garment. It's still
Mac-runnable because we feed it **our MediaPipe mask** and import only
`CatVTONPipeline` (diffusers-only) — never their `AutoMasker` (detectron2/
DensePose).

```bash
bash backend/scripts/setup_catvton.sh          # clones the CatVTON repo
pip install -r backend/requirements-hd.txt
export CATVTON_REPO=~/CatVTON                   # path printed by the script
export HD_ENGINE=catvton
# worker (macOS fork-safe) + API, then "HD render"
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES PYTORCH_ENABLE_MPS_FALLBACK=1 \
  celery -A app.jobs.celery_app worker --pool=solo --loglevel=info
```
First run downloads `zhengchong/CatVTON` + the SD-1.5 inpaint base (~few GB).
Tunables: `CATVTON_VERSION` (vitonhd|dresscode|mix), `HD_STEPS` (50),
`HD_GUIDANCE` (2.5 — CatVTON uses low CFG), `HD_HEIGHT`/`HD_WIDTH` (512×384).

How it differs from `local`: CatVTON concatenates person+garment in the model so
it reproduces the actual garment (pattern, cut), not a generic shirt. Quality is
much closer to IDM-VTON. Use **real garment cut-outs** (front-facing, plain
background), not the flat placeholder PNGs, for good results.

**Unverified here:** no GPU/torch/weights in my environment, so the CatVTON
engine ships for you to run. I matched it to CatVTON's published `CatVTONPipeline`
inference API ([inference.py](https://github.com/Zheng-Chong/CatVTON)) and verified
wiring, mask building, device detection, and that the base app is unaffected. If
the repo's current API differs, the failure point will be the `CatVTONPipeline(...)`
construction or its `__call__` — share the traceback and I'll adjust.

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
