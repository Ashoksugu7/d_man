# Phase 5 — Indian Attire (handoff)

Kurta, salwar/palazzo, dupatta, and lehenga (two-piece) added as new garment
**categories** on the existing affine pipeline (no GPU). Saree deferred (needs
real HD parsing). Placeholder assets generated; verified by rendering each onto
a synthetic figure. **All changes uncommitted** for review.

## What was added

- **assets/generate_indian.py** — placeholder PNGs + keypoints + catalog entries:
  `kurta_*` (long top), `salwar_*` / palazzo (wide pant), `dupatta_*`
  (translucent drape), `lehenga_rose` (two-piece: blouse + flared skirt).
- **backend/app/warp.py** — category-aware warp:
  - `category_kind()` → top | pant | skirt | lehenga.
  - Per-category fit (`_TOP_FIT` kurta/dupatta/blouse, `_PANT_FIT`
    salwar/palazzo), `SkirtFitParams` + `compute_affine_skirt` (waist→hips,
    flared hem), `warp_lehenga()` (skirt then blouse).
  - `affine_for` / `draw_debug` updated for the new kinds.
- **backend/app/main.py** — `_load_piece()` helper; lehenga loads blouse+skirt
  and calls `warp_lehenga`.
- **frontend/lib/liveFit.ts** — `kindFor`, `topHem` (kurta/dupatta hems),
  `skirtTargets`. **LivePreview** routes top/pant/skirt by kind (lehenga live =
  skirt piece).
- **tools/annotate.html** — new category options + keypoint schemes (dupatta =
  shoulders+hem, skirt = waist+hem; pants cover salwar/palazzo).

## How each maps

| Category | Kind | Warp |
|---|---|---|
| kurta | top | shoulders→shoulders, long hem (hem_extend 2.35) |
| dupatta | top | shoulders→shoulders, translucent (PNG alpha), hem ~1.75 |
| salwar/palazzo | pant | waist→hips, hems→ankles, widened |
| skirt | skirt | waist→hips, flared hem below knees |
| lehenga | lehenga | two-piece: flared skirt + cropped blouse on top |

## Limitations / follow-ups

- Affine only — no real drape/fold; placeholder cartoon assets (same caveat as
  every category: use **real garment photos** for good results — see
  `assets/GARMENT_IMAGES.md`). HD engines (CatVTON/Replicate) give realistic
  output for the single-piece categories.
- Lehenga in **HD** mode uses the skirt piece only (single-image engines);
  two-piece compositing is image/live only.
- Kurta side slits not modeled; dupatta on/off UI toggle not added; saree
  deferred (HD + saree-specific parsing).

## Saree (image-mode only)

A saree is a multi-region drape, modelled as **3 pieces** (placeholder):
`saree_*_blouse` (torso), `saree_*_drape` (lower wrap, skirt keypoints),
`saree_*_pallu` (diagonal sash, translucent). `assets/generate_saree.py`.

- **backend/app/warp.py** — `warp_saree()` composites drape → blouse → pallu;
  `compute_affine_pallu()` drapes the pallu over the **left shoulder** down to
  the right hip. `category_kind("saree")` → skirt (single-piece HD uses the
  drape).
- **backend/app/main.py** — saree loads its 3 pieces and calls `warp_saree`.
- **HD engines** map saree → `dresses` (CatVTON/Replicate full-body category).
- **Live is blocked** for saree (image-mode only) — LivePreview shows a note.
- **tools/annotate.html** — `pallu` scheme added; annotate a saree as 3 pieces
  (blouse / skirt / pallu).

### The real saree approach (deferred)
Geometric affine can't reproduce true saree drape/pleats/pallu folds. The real
path (GPU + data):
1. **Saree-specific parsing**: segment blouse / drape-front / pleats / pallu
   (fine-tune a human-parsing model — SCHP/Graphonomy — on saree images, since
   generic parsers don't have these labels).
2. **Learned warp** for the pallu/pleats instead of geometric TPS (the drape is
   non-rigid; a learned flow field handles folds far better).
3. **Dataset**: curate paired saree try-on images (in-shop drape ↔ worn) for
   fine-tuning a VTON model on the `dresses` setting.
4. **HD diffusion** (IDM-VTON/CatVTON `dresses`) for the final render; validate
   on diverse body types/skin tones.

## Verify
```bash
cd assets && python generate_indian.py           # (re)generate placeholders
# backend tests still green:
python backend/test_pipeline.py && python backend/test_measure.py && \
  python backend/test_hd_jobs.py
cd frontend && npx next build
```
Then in the app pick a kurta / salwar / dupatta / lehenga in either tab.
