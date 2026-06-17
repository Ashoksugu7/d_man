# Advanced Virtual Try-On — Project Plan

**Project:** Virtual Try-On Application  
**Date:** June 2026  
**Scope:** Image-based → Live AR → Indian attire → Saree

---

## 1. Vision

Build a virtual try-on platform that lets users see how garments look on them — starting with a realistic static image pipeline, then progressing to live AR overlay, and finally supporting complex Indian attire including sarees.

**Two end-user modes:**
- **Live Preview** — Real-time AR overlay via webcam (fast, mirror-like)
- **HD Try-On** — Capture one frame → backend generates a photorealistic result

---

## 2. System Architecture

### Frontend
| Component | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Camera access | WebRTC / MediaDevices API |
| Rendering | HTML5 Canvas + CSS transforms |
| 3D (later phases) | Three.js for avatar/body model |
| State management | Zustand |
| Styling | Tailwind CSS |

### Backend
| Component | Technology |
|---|---|
| API server | FastAPI (Python 3.11+) |
| Inference service | Separate microservice (FastAPI or Triton) |
| Garment metadata | PostgreSQL + S3/Cloud storage |
| User sessions | Redis |
| Task queue | Celery + Redis (for async HD try-on) |
| Container | Docker + docker-compose |

### AI / CV Layer
| Task | Tool |
|---|---|
| Pose estimation (live) | MediaPipe Pose |
| Body parsing / segmentation | SCHP / Graphonomy |
| Dense body mapping | DensePose (offline/HD mode) |
| Cloth warping | TPS (Thin Plate Spline) |
| Generative try-on | IDM-VTON / CatVTON / HR-VITON |
| ONNX export (speed) | ONNX Runtime |
| GPU acceleration | TensorRT (production) |
| Image processing | OpenCV |

### Infrastructure
```
User Browser
    │
    ▼
Next.js Frontend (Vercel / Nginx)
    │
    ├── WebSocket ──► Live Pose Service (MediaPipe)
    │
    └── REST API ──► FastAPI Backend
                        │
                        ├── Garment DB (PostgreSQL)
                        ├── Task Queue (Celery + Redis)
                        └── Inference Service
                                │
                                ├── Pose/Parse Models
                                ├── Warp Models
                                └── VTON Diffusion Models
```

---

## 3. Phased Roadmap

### Phase 1 — Static Image Try-On (Weeks 1–4)
**Goal:** User uploads photo → backend returns realistic try-on image for shirt/t-shirt/kurta.

**Deliverables:**
- Upload UI (photo + garment picker)
- Body detection pipeline (MediaPipe → keypoints)
- Human parsing (segment torso region)
- Simple TPS cloth warping onto torso
- FastAPI endpoint: `POST /api/tryon/image`
- Result display with download option

**Models:** MediaPipe Pose + basic TPS warping  
**Garments:** Shirt, T-shirt, Kurta (front-facing, PNG with alpha)  
**Success criteria:** Visually plausible overlay on 80%+ of test images

---

### Phase 2 — Live Shirt/Pant Overlay (Weeks 5–8)
**Goal:** Real-time webcam AR overlay for tops and bottoms.

**Deliverables:**
- Webcam feed with canvas overlay
- Real-time MediaPipe pose → shoulder/hip/ankle landmarks
- Garment anchor point mapping (shoulder width, torso length)
- Smooth transform with low-pass filtering (jitter reduction)
- Pants overlay: waist + inseam alignment
- WebSocket or requestAnimationFrame rendering loop
- FPS target: ≥24fps on mid-range hardware

**Technical notes:**
- Run MediaPipe in-browser (WASM) for live mode to avoid server round-trips
- Use affine transform (scale + translate + slight rotation) per frame
- No diffusion model in live mode — overlay only

---

### Phase 3 — HD Try-On with Diffusion Model (Weeks 9–13)
**Goal:** High-quality photorealistic try-on using generative AI.

**Deliverables:**
- Integrate IDM-VTON or CatVTON inference pipeline
- DensePose body mapping for cloth warping accuracy
- Full human parsing (SCHP) to isolate torso/legs
- Async job queue: user submits → gets job ID → polls for result
- Result gallery (user's try-on history)
- FastAPI endpoints: `POST /api/tryon/hd`, `GET /api/tryon/hd/{job_id}`

**Models:** IDM-VTON (recommended start) or CatVTON  
**GPU requirement:** NVIDIA GPU with ≥8GB VRAM for inference  
**Inference time target:** <15 seconds per image

---

### Phase 4 — Body Size Estimation & Fit Feedback (Weeks 14–16)
**Goal:** Give users size recommendations and fit feedback.

**Deliverables:**
- Shoulder width estimation from pose landmarks
- Torso length / waist / hip proxy measurements
- Garment metadata: size chart per item (S/M/L/XL dimensions)
- Fit score: `fits_well` / `too_tight` / `too_loose` label
- UI: size recommendation badge on garment cards

**Note:** Measurements are relative (pixel ratios), not absolute cm — calibrate with reference object or standard height input.

---

### Phase 5 — Indian Attire (Weeks 17–22)
**Goal:** Support Kurta, Salwar, Lehenga, Dupatta. Saree in image-only mode first.

**Garment progression:**
1. **Kurta** (similar to shirt — reuse Phase 1/2 pipeline)
2. **Salwar / Palazzo** (reuse pants pipeline)
3. **Lehenga** (skirt component + blouse — two-piece warping)
4. **Dupatta** (drape overlay, anchored at shoulders)
5. **Saree** (image-only HD try-on — see below)

**Saree-specific approach:**
- No live mode initially — too complex for real-time
- Use HD try-on pipeline with saree-specific parsing
- Segment: blouse region, drape front, pallu
- Consider reference dataset of saree try-on images for fine-tuning
- Pallu draping: use a learned warp rather than geometric TPS

---

### Phase 6 — Realism & Polish (Weeks 23–28)
**Goal:** Handle edge cases, improve visual quality.

**Deliverables:**
- Hand/arm occlusion handling (mask hands over garment)
- Side-turn support (±30° yaw tolerance)
- Cloth fold and shadow simulation (learned from diffusion model)
- Lighting adaptation (match garment lighting to scene)
- Multi-body-shape robustness (test on diverse body types)
- Video try-on MVP: temporal consistency across frames

---

## 4. Milestone Summary

| Milestone | Target | Deliverable |
|---|---|---|
| M1 | Week 4 | Static image try-on (shirt/kurta) working end-to-end |
| M2 | Week 8 | Live AR overlay — shirt + pant on webcam |
| M3 | Week 13 | HD diffusion try-on with async job pipeline |
| M4 | Week 16 | Fit estimation + size recommendation |
| M5 | Week 22 | Indian attire support including saree (image mode) |
| M6 | Week 28 | Realism pass + video try-on MVP |

---

## 5. Data & Garment Pipeline

### Garment asset requirements
- PNG with transparent background (alpha channel)
- Keypoint annotations: collar, left shoulder, right shoulder, hem, sleeve ends
- Size metadata: S/M/L/XL with shoulder width and length in cm
- Category tag: shirt / pant / kurta / lehenga / saree / etc.

### Garment database schema (simplified)
```sql
garments (
  id UUID,
  name TEXT,
  category TEXT,          -- shirt | pant | kurta | saree | ...
  image_url TEXT,         -- original garment PNG
  mask_url TEXT,          -- segmentation mask
  keypoints JSONB,        -- anchor points
  size_chart JSONB,       -- { S: { shoulder_cm, length_cm }, ... }
  created_at TIMESTAMP
)

tryon_jobs (
  id UUID,
  user_id UUID,
  garment_id UUID,
  input_image_url TEXT,
  result_image_url TEXT,
  status TEXT,            -- pending | processing | done | failed
  created_at TIMESTAMP
)
```

---

## 6. Key Technical Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Diffusion model too slow | High | Use ONNX/TensorRT; offer async queue; set user expectation |
| Saree draping quality poor | High | Start image-only; collect reference data; consider fine-tuning |
| Jitter in live mode | Medium | Landmark smoothing (Kalman filter or EMA) |
| Diverse body shapes underperform | Medium | Test dataset with varied body types; augment training |
| GPU cost at scale | Medium | Cache frequent try-on pairs; use spot instances |
| Video temporal consistency | High | Use frame-interpolation or latent consistency models |

---

## 7. Team & Roles (Suggested)

| Role | Responsibilities |
|---|---|
| ML Engineer | Model integration, inference pipeline, warping |
| Backend Engineer | FastAPI, job queue, DB, S3, APIs |
| Frontend Engineer | Next.js, WebRTC, Canvas rendering, UI |
| DevOps | Docker, GPU server setup, CI/CD |
| Product / Designer | Garment UX, size UI, user testing |

For a solo/small team: ML + Backend combined is feasible; frontend can use a UI template to start.

---

## 8. MVP Recommendation (Start Here)

If building solo or with a small team, ship this first:

**Scope:**
- Next.js frontend with camera + upload UI
- FastAPI backend with MediaPipe pose
- Shirt / T-shirt / Kurta only (front-facing)
- Live overlay mode (in-browser MediaPipe WASM)
- HD try-on mode with IDM-VTON (async)
- 10–20 garments in the catalog to start

**Avoid for MVP:**
- Pant (adds complexity)
- Indian attire (Phase 5)
- Video (Phase 6)
- Fit estimation (Phase 4)

Get user feedback on MVP before investing in Phase 3+.

---

## 9. Recommended First Sprint (Week 1–2)

1. Set up Next.js + FastAPI monorepo with Docker
2. Integrate MediaPipe Pose in browser (WASM)
3. Build garment overlay on static image (affine transform only)
4. Create garment PNG assets (5 shirts with keypoints)
5. Deploy to local + staging environment
6. Demo: upload photo → see shirt overlay

This gives a working demo in 2 weeks with no GPU required.
