# Live AR — Cross-Browser QA Checklist (Phase 2)

The live overlay depends on `getUserMedia` (camera) and the MediaPipe
`tasks-vision` WASM pose model, both of which vary by browser. Run this
checklist on real devices before shipping.

## Matrix

| Browser | Desktop | Mobile | Notes |
|---|---|---|---|
| Chrome | ☐ | ☐ | Reference target. GPU delegate works. |
| Safari | ☐ | ☐ | iOS: camera needs HTTPS + a user gesture; check WASM SIMD. |
| Firefox | ☐ | ☐ | Verify GPU delegate; falls back to CPU if unsupported. |
| Edge | ☐ | — | Chromium — usually mirrors Chrome. |

## Per-browser steps

1. Open the app over **HTTPS** (or `localhost`). Camera is blocked on plain
   HTTP on every browser except `localhost`.
2. Go to **Live Preview**, pick a top, **Start camera**, grant permission.
3. Confirm: webcam feed visible, **green landmark dots** on shoulders/hips
   (tick *Show landmarks*), shirt tracks movement, **FPS ≥ 24**.
4. Pick a **pant** (full body in frame) → waistband sits at hips, legs map to
   ankles; dots show hips + ankles.
5. Toggle **Mirror** — overlay and video stay aligned.
6. Step out of frame → "step back" hint appears; step back in → recovers.
7. **Stop camera** → tracks released (camera indicator off).

## Known browser gotchas

- **iOS Safari**: `getUserMedia` requires HTTPS and a direct user tap; the
  `<video>` must be `playsInline muted` (already set). Autoplay otherwise fails.
- **GPU delegate**: if `delegate: "GPU"` fails on a device, switch to
  `delegate: "CPU"` in `LivePreview.tsx` (lower FPS but broad support).
- **Permissions**: a previously denied camera permission must be reset in site
  settings; the prompt won't reappear automatically.
- **Performance**: low-end mobiles may dip below 24 FPS with the lite model;
  consider reducing the requested capture resolution.

## Result

Record device, OS, browser version, and observed FPS for each cell. File any
failures against the live-overlay component.
