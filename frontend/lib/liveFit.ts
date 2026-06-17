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

// MediaPipe Pose landmark indices we use.
export const LM = {
  leftShoulder: 11,
  rightShoulder: 12,
  leftHip: 23,
  rightHip: 24,
  leftAnkle: 27,
  rightAnkle: 28,
} as const;

/**
 * Exponential moving average smoother for a set of named 2D points.
 * Reduces per-frame jitter in pose landmarks. alpha in (0,1]: higher = more
 * responsive, lower = smoother.
 */
export class EMASmoother {
  private prev: Record<string, Pt> = {};
  constructor(private alpha = 0.4) {}

  reset() {
    this.prev = {};
  }

  smooth(points: Record<string, Pt>): Record<string, Pt> {
    const out: Record<string, Pt> = {};
    for (const k of Object.keys(points)) {
      const p = points[k];
      const prev = this.prev[k];
      out[k] = prev
        ? { x: this.alpha * p.x + (1 - this.alpha) * prev.x,
            y: this.alpha * p.y + (1 - this.alpha) * prev.y }
        : p;
      this.prev[k] = out[k];
    }
    return out;
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
export function bodyTargets(b: {
  rightShoulder: Pt;
  leftShoulder: Pt;
  rightHip: Pt;
  leftHip: Pt;
}) {
  const shMid = mid(b.rightShoulder, b.leftShoulder);
  const hipMid = mid(b.rightHip, b.leftHip);
  const torso = sub(hipMid, shMid);
  const lift = scale(torso, FIT.neckLift);

  const rs = sub(add(shMid, scale(sub(b.rightShoulder, shMid), FIT.shoulderWiden)), lift);
  const ls = sub(add(shMid, scale(sub(b.leftShoulder, shMid), FIT.shoulderWiden)), lift);
  const hemMid = sub(add(shMid, scale(torso, FIT.hemExtend)), lift);
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
