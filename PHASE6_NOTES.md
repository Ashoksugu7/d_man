# Phase 6 — Realism & Polish (no-GPU slice, handoff)

CPU-only realism improvements added and verified. **Uncommitted** for review.
Remaining Phase 6 items (side-turn, cloth folds, diverse-body validation, video,
perf) are GPU/data-dependent and not done.

## What was added

- **Hand/arm occlusion** (`warp.py: forearm_occlusion_mask`) — builds a mask of
  the forearms + hands (elbow→wrist + hand blob, from new pose landmarks) and
  removes garment alpha there, so folded arms stay *in front* of the garment
  instead of being painted over. On by default (`TRYON_OCCLUDE`, form param
  `occlude`). Verified: folded forearms render over the shirt.
- **Lighting adaptation** (`warp.py: match_lighting`) — scales the garment
  region's brightness toward the scene's level under it (clamped 0.7–1.3) so a
  flat garment looks less pasted. Opt-in (`TRYON_LIGHTING`, form param
  `lighting`, UI "Match lighting").
- **TPS warp for tops** (`warp.py: tps_refine_top`) — optional Thin-Plate-Spline
  refinement on the affine result that bends sleeves toward the elbows and seats
  the collar at the neck (uses the new elbow landmarks). Opt-in (`TRYON_TPS`,
  form param `tps`, UI "TPS warp"); affine stays the stable default. Wrapped in
  try/except so it can never break a render.
- **Dupatta on/off** — live overlay "Show dupatta" checkbox to toggle the drape.
- **pose.py** — now also returns elbows + wrists (for occlusion + TPS).

## Toggles

| Feature | Env | API form field | UI |
|---|---|---|---|
| Occlusion | `TRYON_OCCLUDE` (default on) | `occlude` | (on by default) |
| Lighting | `TRYON_LIGHTING` (default off) | `lighting` | "Match lighting" |
| TPS (tops) | `TRYON_TPS` (default off) | `tps` | "TPS warp (tops)" |
| Dupatta show/hide | — | — | live "Show dupatta" |

## Caveats
- These polish the **affine** result; they don't make placeholder/cartoon
  garments realistic (use real images + HD engines for that).
- Occlusion mask is geometric (elbow→wrist); it approximates, not segments.
- TPS bends toward elbows — best with a clean front pose; opt-in by design.

## Verify
```bash
python backend/test_pipeline.py && python backend/test_measure.py && \
  python backend/test_hd_jobs.py        # all pass
cd frontend && npx next build           # compiles
```
In the HD Image tab: toggle "Match lighting" / "TPS warp"; occlusion is automatic.
