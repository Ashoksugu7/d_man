// Shared helpers for the live AR overlay (Phase 2).
// Keep these framework-free so they're easy to unit-test.

export type Pt = { x: number; y: number };

// Fit factors — mirror backend/app/warp.py FitParams so live and HD modes agree.
export const FIT = {
  shoulderWiden: 1.18, // MediaPipe shoulder joint -> garment seam
  hipWiden: 1.1,
  hemExtend: 1.3, // how far below shoulders the hem sits (1.0 = at hips)
  neckLift: 0.06, // raise garment by this fraction of shoulder->hip length
};

// Pant fit factors — mirror backend/app/warp.py PantFitParams.
export const PANT_FIT = {
  waistWiden: 1.12,
  waistLift: 0.1, // raise waistband above hips (fraction of hip->ankle length)
  ankleExtend: 1.02,
};

export type Kind = "top" | "pant";
export function kindFor(category?: string): Kind {
  const c = (category || "").toLowerCase();
  if (["pant", "trouser", "trousers"].includes(c)) return "pant";
  return "top"; // shirt, tshirt, fullsleeve, ...
}
export const topHem = (_category?: string) => FIT.hemExtend;

// MediaPipe Pose landmark indices we use.
export const LM = {
  leftShoulder: 11,
  rightShoulder: 12,
  leftElbow: 13,
  rightElbow: 14,
  leftWrist: 15,
  rightWrist: 16,
  leftHip: 23,
  rightHip: 24,
  leftKnee: 25,
  rightKnee: 26,
  leftAnkle: 27,
  rightAnkle: 28,
} as const;

/**
 * One Euro filter (Casiez et al.) for a single scalar signal.
 *
 * Adaptive low-pass: when the signal is slow (standing still) the cutoff is
 * low, so sensor jitter is smoothed away almost entirely; when the signal
 * moves fast the cutoff rises, so there is no visible lag. This is the
 * standard filter for stabilizing pose/hand landmarks.
 */
class OneEuro1D {
  private xPrev: number | null = null;
  private dxPrev = 0;
  private tPrev = 0;

  constructor(
    private minCutoff: number,
    private beta: number,
    private dCutoff: number
  ) {}

  private alpha(cutoff: number, dt: number) {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }

  filter(x: number, tSec: number): number {
    if (this.xPrev == null) {
      this.xPrev = x;
      this.tPrev = tSec;
      return x;
    }
    const dt = Math.max(1e-3, tSec - this.tPrev);
    this.tPrev = tSec;
    const dx = (x - this.xPrev) / dt;
    const aD = this.alpha(this.dCutoff, dt);
    this.dxPrev = aD * dx + (1 - aD) * this.dxPrev;
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dxPrev);
    const a = this.alpha(cutoff, dt);
    this.xPrev = a * x + (1 - a) * this.xPrev;
    return this.xPrev;
  }

  reset() {
    this.xPrev = null;
    this.dxPrev = 0;
  }
}

/**
 * One-Euro smoother for a set of named 2D points, plus a GROUP deadband:
 * if no point moved more than `deadbandPx` since the last released output,
 * the entire previous output is returned unchanged. Holding all points
 * together (instead of per-point) means the garment can neither drift nor
 * change shape from sub-pixel landmark noise while the user stands still.
 *
 * Tuning: raise `minCutoff` if the overlay lags; lower it if it still
 * jitters. `beta` controls how quickly smoothing releases during motion.
 */
export class OneEuroSmoother {
  private fx = new Map<string, OneEuro1D>();
  private fy = new Map<string, OneEuro1D>();
  private held: Record<string, Pt> | null = null;

  constructor(
    private minCutoff = 0.8,
    private beta = 0.008,
    private dCutoff = 1.0,
    private deadbandPx = 2.0
  ) {}

  reset() {
    this.fx.clear();
    this.fy.clear();
    this.held = null;
  }

  smooth(points: Record<string, Pt>, tMs?: number): Record<string, Pt> {
    const t =
      (tMs ??
        (typeof performance !== "undefined" ? performance.now() : Date.now())) /
      1000;
    const cand: Record<string, Pt> = {};
    for (const k of Object.keys(points)) {
      let fx = this.fx.get(k);
      let fy = this.fy.get(k);
      if (!fx || !fy) {
        fx = new OneEuro1D(this.minCutoff, this.beta, this.dCutoff);
        fy = new OneEuro1D(this.minCutoff, this.beta, this.dCutoff);
        this.fx.set(k, fx);
        this.fy.set(k, fy);
      }
      cand[k] = { x: fx.filter(points[k].x, t), y: fy.filter(points[k].y, t) };
    }
    // group hold: release only when SOME point really moved
    const h = this.held;
    if (h && Object.keys(cand).every((k) =>
      h[k] && Math.hypot(cand[k].x - h[k].x, cand[k].y - h[k].y) < this.deadbandPx
    )) {
      return { ...h };
    }
    this.held = cand;
    return { ...cand };
  }
}

/**
 * Solve the 2x3 affine matrix [a,c,e; b,d,f] mapping src[i] -> dst[i] for 3
 * correspondences. Canvas usage: ctx.setTransform(a,b,c,d,e,f).
 * Maps image coords -> canvas coords: x' = a*x + c*y + e, y' = b*x + d*y + f.
 */
export function solveAffine3(src: [Pt, Pt, Pt], dst: [Pt, Pt, Pt]) {
  const [s0, s1, s2] = src;
  // Determinant of the source triangle.
  const det =
    s0.x * (s1.y - s2.y) - s0.y * (s1.x - s2.x) + (s1.x * s2.y - s2.x * s1.y);
  if (Math.abs(det) < 1e-6) return null;

  // Barycentric-style solution for the two rows independently.
  const solveRow = (d0: number, d1: number, d2: number) => {
    const A =
      (d0 * (s1.y - s2.y) + d1 * (s2.y - s0.y) + d2 * (s0.y - s1.y)) / det;
    const C =
      (d0 * (s2.x - s1.x) + d1 * (s0.x - s2.x) + d2 * (s1.x - s0.x)) / det;
    const E =
      (d0 * (s1.x * s2.y - s2.x * s1.y) +
        d1 * (s2.x * s0.y - s0.x * s2.y) +
        d2 * (s0.x * s1.y - s1.x * s0.y)) / det;
    return [A, C, E] as const;
  };

  const [a, c, e] = solveRow(dst[0].x, dst[1].x, dst[2].x);
  const [b, d, f] = solveRow(dst[0].y, dst[1].y, dst[2].y);
  return { a, b, c, d, e, f };
}

/**
 * Given smoothed body landmarks (pixel coords) build the 3 destination points
 * (right shoulder, left shoulder, hem midpoint) the garment maps onto.
 */
export function bodyTargets(
  b: { rightShoulder: Pt; leftShoulder: Pt; rightHip: Pt; leftHip: Pt },
  hemExtend: number = FIT.hemExtend
) {
  const shMid = mid(b.rightShoulder, b.leftShoulder);
  const hipMid = mid(b.rightHip, b.leftHip);
  const torso = sub(hipMid, shMid);
  const lift = scale(torso, FIT.neckLift);

  const rs = sub(add(shMid, scale(sub(b.rightShoulder, shMid), FIT.shoulderWiden)), lift);
  const ls = sub(add(shMid, scale(sub(b.leftShoulder, shMid), FIT.shoulderWiden)), lift);
  const hemMid = sub(add(shMid, scale(torso, hemExtend)), lift);
  return { rs, ls, hemMid };
}

/**
 * Pant destination points: waistband (at hips, lifted) + ankle midpoint.
 */
export function pantTargets(b: {
  rightHip: Pt;
  leftHip: Pt;
  rightAnkle: Pt;
  leftAnkle: Pt;
}) {
  const hipMid = mid(b.rightHip, b.leftHip);
  const ankleMid = mid(b.rightAnkle, b.leftAnkle);
  const leg = sub(ankleMid, hipMid);
  const lift = scale(leg, PANT_FIT.waistLift);

  const rw = sub(add(hipMid, scale(sub(b.rightHip, hipMid), PANT_FIT.waistWiden)), lift);
  const lw = sub(add(hipMid, scale(sub(b.leftHip, hipMid), PANT_FIT.waistWiden)), lift);
  const ankle = add(hipMid, scale(leg, PANT_FIT.ankleExtend));
  return { rw, lw, ankle };
}

const mid = (a: Pt, b: Pt): Pt => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const sub = (a: Pt, b: Pt): Pt => ({ x: a.x - b.x, y: a.y - b.y });
const add = (a: Pt, b: Pt): Pt => ({ x: a.x + b.x, y: a.y + b.y });
const scale = (a: Pt, s: number): Pt => ({ x: a.x * s, y: a.y * s });
