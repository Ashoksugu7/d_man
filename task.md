# Virtual Try-On — Task List

> Status: [ ] Todo | [x] Done | [~] In Progress | [-] Blocked

---

## Phase 1 — Static Image Try-On (Weeks 1–4)

### Setup
- [x] Initialize Next.js 14 project (App Router)
- [x] Initialize FastAPI backend project
- [x] Set up Docker + docker-compose (frontend + backend)
- [x] Configure local file storage for garment and result images (local disk)
- [x] Store garment metadata in a local JSON file (no DB for now)
- [x] Store try-on results in browser localStorage  <!-- result gallery, lib/gallery.ts -->
- [x] Set up CI/CD pipeline (GitHub Actions)

### Frontend
- [x] Build photo upload UI (drag & drop + file picker)
- [x] Build garment picker / catalog grid
- [x] Build result display page (before / after view)
- [x] Add download button for try-on result

### Backend
- [x] Create `POST /api/tryon/image` endpoint
- [x] Integrate MediaPipe Pose for keypoint extraction
- [ ] Build human parsing module (torso segmentation)
- [ ] Implement TPS (Thin Plate Spline) cloth warping  <!-- Sprint 1 uses affine; TPS later -->
- [x] Return warped garment overlay on user photo

### Garment Assets
- [~] Prepare 10–20 garment PNGs with transparent background  <!-- 5 placeholder shirts done -->
- [x] Annotate keypoints: collar, left/right shoulder, hem, sleeve ends
- [x] Add garment metadata to DB (name, category, size chart)  <!-- JSON catalog for now -->

---

## Phase 2 — Live AR Overlay (Weeks 5–8)

- [x] Integrate MediaPipe Pose WASM in browser (no server round-trip)
- [x] Build webcam feed component (WebRTC / getUserMedia)
- [x] Overlay garment on canvas in real-time (requestAnimationFrame loop)
- [x] Map garment anchor points to shoulder/hip/ankle landmarks
- [x] Add affine transform: scale + translate + slight rotation per frame
- [x] Add jitter reduction (EMA filter on landmarks)
- [x] Implement pants overlay (waist + ankle alignment)  <!-- 3 placeholder pants; category-aware live + HD -->
- [x] Target: ≥24 FPS on mid-range hardware  <!-- FPS meter added; lite model + rAF loop -->
- [~] Test across browsers (Chrome, Safari, Firefox)  <!-- checklist in BROWSER_QA.md; needs manual run on devices -->

---

## Phase 3 — HD Diffusion Try-On (Weeks 9–13)

- [ ] Set up GPU inference server (NVIDIA ≥8GB VRAM)  <!-- needs a GPU host -->
- [x] Integrate IDM-VTON or CatVTON model  <!-- ReplicateEngine: hosted IDM-VTON, works on any machine (HD_ENGINE=replicate + token); local GPU engine still a scaffold -->
- [ ] Integrate DensePose body mapping pipeline  <!-- documented in IDMVTONEngine guide -->
- [ ] Integrate SCHP for full human parsing (torso/legs isolation)  <!-- documented in IDMVTONEngine guide -->
- [x] Build async job queue with Celery + Redis
- [x] Create `POST /api/tryon/hd` endpoint (returns job ID)
- [x] Create `GET /api/tryon/hd/{job_id}` polling endpoint
- [x] Build job status UI (loading state + progress indicator)
- [x] Build try-on result gallery (user history)  <!-- localStorage; also covers Phase 1 localStorage item -->
- [ ] Target: <15 seconds inference time per image  <!-- depends on real model -->
- [ ] Export models to ONNX for speed optimization  <!-- depends on real model -->

<!-- Phase 3 async architecture (queue, endpoints, job UI, gallery) done with a
     CPU StubEngine so it runs/verifies without a GPU. Real diffusion model
     (IDM-VTON + DensePose + SCHP), <15s target, and ONNX are GPU-only and
     remain open. See PHASE3_NOTES.md. Uncommitted for review. -->

---

## Phase 4 — Body Size Estimation (Weeks 14–16)

- [x] Estimate shoulder width from pose landmarks (pixel ratio)
- [x] Estimate torso length, waist proxy, hip proxy
- [x] Add height input field (for calibration)
- [x] Build size recommendation logic (compare user measurements to garment size chart)
- [x] Show fit badge on garment cards: `Fits Well` / `Too Tight` / `Too Loose`
- [x] Update garment DB schema with size chart per item  <!-- size_chart already in catalog.json -->

<!-- Phase 4 implemented by scheduled task on 2026-06-18. See PHASE4_NOTES.md.
     Approximate (single photo + height calibration). Uncommitted for review. -->

---

## Phase 5 — Indian Attire (Weeks 17–22)

### Kurta
- [ ] Reuse shirt pipeline for kurta (front-facing)
- [ ] Add kurta keypoints (longer hem, side slits)

### Salwar / Palazzo
- [ ] Extend pants pipeline for salwar
- [ ] Handle wide-leg / palazzo shape warping

### Lehenga
- [ ] Two-piece warping: skirt + blouse separately
- [ ] Skirt: hip-to-hem warp; blouse: torso warp
- [ ] Handle flared skirt geometry

### Dupatta
- [ ] Drape overlay anchored at shoulders
- [ ] Static drape position for image mode
- [ ] Optional: toggle dupatta on/off in UI

### Saree (Image Mode Only)
- [ ] Research saree-specific body parsing approach
- [ ] Segment regions: blouse, drape front, pallu
- [ ] Implement pallu warp (learned warp preferred over geometric TPS)
- [ ] Collect / curate reference saree try-on dataset
- [ ] Run HD try-on pipeline for saree (no live mode yet)
- [ ] Validate output quality on diverse body types

---

## Phase 6 — Realism & Polish (Weeks 23–28)

- [ ] Hand/arm occlusion: mask hands over garment layer
- [ ] Side-turn tolerance: handle ±30° yaw without garment distortion
- [ ] Cloth fold simulation (leverage diffusion model outputs)
- [ ] Lighting adaptation: match garment brightness/shadow to scene
- [ ] Robustness testing on diverse body shapes and skin tones
- [ ] Video try-on MVP: temporal consistency across frames
- [ ] Performance profiling + GPU cost optimization
- [ ] Final QA pass across all garment categories

---

## Infrastructure & DevOps

- [ ] Dockerize all services (frontend, backend, inference, redis, postgres)
- [ ] Set up staging environment
- [ ] Set up production environment with GPU server
- [ ] Configure TensorRT for production inference acceleration
- [ ] Set up logging + monitoring (errors, inference time, job queue depth)
- [ ] Set up CDN for garment + result images

---

## Sprint 1 Checklist (Week 1–2 — No GPU Required)

- [x] Monorepo scaffold: Next.js + FastAPI + Docker
- [x] MediaPipe Pose working in browser (WASM)
- [x] Static garment overlay on uploaded photo (affine transform)
- [x] 5 shirt PNG assets with keypoints ready
- [x] Local demo running end-to-end
- [~] Deploy to staging  <!-- config + CI job ready (DEPLOY.md); needs provider creds -->

