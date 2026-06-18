# Phase 4 — Body Size Estimation & Fit Feedback (handoff)

Implemented by the scheduled task on 2026-06-18. **All changes are uncommitted**
in the working tree for review. Backend tests pass; the frontend compiles.

## What it does

Given a photo and the user's height (cm), estimate rough body measurements from
pose landmarks and recommend a garment size + fit label (Fits Well / Too Tight /
Too Loose) per garment in the catalog.

## Files

- `backend/app/measure.py` (new) — measurement + size-recommendation logic.
- `backend/app/main.py` — `POST /api/measure` (form: `photo`, `height_cm`) →
  measurements + per-garment recommendations for the whole catalog.
- `backend/app/pose.py` — already exposes shoulders/hips/knees/ankles (Phase 2).
- `backend/test_measure.py` (new) — synthetic full-body smoke test (passes).
- `frontend/lib/store.ts` — `FitLabel`, `Measurements`, `MeasureResult` types +
  `heightCm`, `measure`, `measureError` state.
- `frontend/lib/api.ts` — `requestMeasurements(photo, heightCm)`.
- `frontend/components/ResultView.tsx` — height (cm) input + measure call.
- `frontend/components/GarmentGrid.tsx` — fit badge + recommended size on cards.

## How it works (and key assumptions)

- **Pixel→cm scale**: full-body pixel span (head/nose → ankle midpoint) mapped to
  the entered height, with a documented factor for the head-above-nose portion.
  This is the single biggest source of error — accuracy depends on a full-body,
  front-facing, upright photo.
- **Measurements**: shoulder width, torso length, hip width, inseam, and a
  **waist circumference proxy** derived from hip width (elliptical approximation).
- **Fit logic**: compares the relevant body dimension to each size in the
  garment `size_chart` (`shoulder_cm` for tops, `waist_cm` for pants). Nearest
  size = recommendation; within tolerance (~±3 cm) = `fits_well`, else
  `too_tight`/`too_loose`. Returns `per_size_deltas` for transparency.

## How to run / test

```bash
# backend
python3 backend/test_measure.py          # smoke test
# (run server) uvicorn app.main:app --reload  from backend/
#   POST /api/measure  form: photo=<file>, height_cm=175

# frontend
cd frontend && npx next build            # compiles
# In the app: enter height under "Your photo", badges appear on garment cards.
```

## Limitations / follow-ups

- Single-photo pixel estimates are approximate (no depth, no camera intrinsics).
  UI labels this as approximate — keep that framing.
- Waist is a proxy from hip width, not a true measurement.
- Needs a full-body photo; if ankles/height are missing the API returns null
  measurements with a message (handled gracefully in the UI).
- Possible improvements: reference-object calibration, multi-pose averaging,
  per-garment ease/tolerance tuning, and surfacing measurements in the UI.
