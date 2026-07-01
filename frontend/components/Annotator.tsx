"use client";

import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import { Scheme } from "@/lib/annotation";
import { solveAffine3 } from "@/lib/liveFit";

type Pt = { x: number; y: number };
export type AnnotatorHandle = {
  getKeypoints: () => {
    keypoints_norm: Record<string, [number, number]>;
    keypoints_px: Record<string, [number, number]>;
    canvas: [number, number];
  } | null;
};

type Props = {
  scheme: Scheme;
  /** New garment: a File. Editing: an image URL. */
  imageSrc: File | string | null;
  /** Editing: initial normalized keypoints to preload. */
  initialNorm?: Record<string, [number, number]>;
};

/** Canvas keypoint annotator: click to place, drag to reposition, G to guess. */
const Annotator = forwardRef<AnnotatorHandle, Props>(function Annotator(
  { scheme, imageSrc, initialNorm },
  ref
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [pts, setPts] = useState<Record<string, Pt>>({}); // image-pixel coords
  const [dims, setDims] = useState<[number, number]>([0, 0]);
  const scaleRef = useRef(1);
  const dragRef = useRef<string | null>(null);

  useImperativeHandle(ref, () => ({
    getKeypoints: () => {
      const [w, h] = dims;
      if (!w || !h) return null;
      const norm: Record<string, [number, number]> = {};
      const px: Record<string, [number, number]> = {};
      for (const n of scheme.order) {
        const p = pts[n];
        if (!p) return null; // incomplete
        px[n] = [Math.round(p.x), Math.round(p.y)];
        norm[n] = [+(p.x / w).toFixed(4), +(p.y / h).toFixed(4)];
      }
      return { keypoints_norm: norm, keypoints_px: px, canvas: [w, h] };
    },
  }));

  // Load image (File or URL)
  useEffect(() => {
    if (!imageSrc) return;
    const url = typeof imageSrc === "string" ? imageSrc : URL.createObjectURL(imageSrc);
    const im = new Image();
    if (typeof imageSrc === "string") im.crossOrigin = "anonymous";
    im.onload = () => {
      imgRef.current = im;
      setDims([im.naturalWidth, im.naturalHeight]);
      // preload initial keypoints (edit mode)
      if (initialNorm) {
        const p: Record<string, Pt> = {};
        for (const n of scheme.order) {
          const v = initialNorm[n];
          if (v) p[n] = { x: v[0] * im.naturalWidth, y: v[1] * im.naturalHeight };
        }
        setPts(p);
      } else {
        setPts({});
      }
    };
    im.src = url;
    return () => { if (typeof imageSrc !== "string") URL.revokeObjectURL(url); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageSrc, scheme]);

  // Draw
  useEffect(() => {
    const cv = canvasRef.current, im = imgRef.current;
    if (!cv || !im || !dims[0]) return;
    const maxW = cv.parentElement?.clientWidth || 400;
    const scale = Math.min(1, maxW / dims[0]);
    scaleRef.current = scale;
    cv.width = Math.round(dims[0] * scale);
    cv.height = Math.round(dims[1] * scale);
    const ctx = cv.getContext("2d")!;
    // checkerboard
    const s = 12;
    for (let y = 0; y < cv.height; y += s)
      for (let x = 0; x < cv.width; x += s) {
        ctx.fillStyle = ((x / s + y / s) % 2) ? "#fff" : "#ececf0";
        ctx.fillRect(x, y, s, s);
      }
    ctx.drawImage(im, 0, 0, cv.width, cv.height);
    for (const n of scheme.order) {
      const p = pts[n]; if (!p) continue;
      const x = p.x * scale, y = p.y * scale;
      ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fillStyle = "#2563eb"; ctx.fill();
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = "#1d4ed8"; ctx.font = "11px system-ui";
      ctx.fillText(n, x + 7, y - 6);
    }
  }, [pts, dims, scheme]);

  // Live warp preview: overlay the garment on a sample body using the current
  // keypoints, so annotation quality is visible as you place/drag points.
  useEffect(() => {
    const pc = previewRef.current, im = imgRef.current;
    if (!pc) return;
    const W = pc.width, H = pc.height;
    const ctx = pc.getContext("2d")!;
    ctx.clearRect(0, 0, W, H);
    // sample body silhouette
    ctx.fillStyle = "#e5e7eb";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#c8ccd2";
    ctx.beginPath(); ctx.arc(W * 0.5, H * 0.12, W * 0.09, 0, 7); ctx.fill(); // head
    ctx.beginPath();
    ctx.moveTo(W * 0.34, H * 0.22); ctx.lineTo(W * 0.66, H * 0.22);
    ctx.lineTo(W * 0.60, H * 0.58); ctx.lineTo(W * 0.40, H * 0.58); ctx.closePath(); ctx.fill(); // torso
    ctx.fillRect(W * 0.41, H * 0.58, W * 0.07, H * 0.4); // legs
    ctx.fillRect(W * 0.52, H * 0.58, W * 0.07, H * 0.4);

    if (!im) return;
    const has = (k: string) => scheme.order.includes(k) && !!pts[k];
    const mid = (a: Pt, b: Pt): Pt => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    let src: [Pt, Pt, Pt] | null = null;
    let dst: [Pt, Pt, Pt] | null = null;
    if (has("left_ankle") && has("right_waist")) {           // pant
      src = [pts.right_waist, pts.left_waist, mid(pts.left_ankle, pts.right_ankle)];
      dst = [{ x: W * 0.42, y: H * 0.58 }, { x: W * 0.58, y: H * 0.58 }, { x: W * 0.5, y: H * 0.96 }];
    } else if (has("top_left") && has("left_hem")) {         // pallu
      src = [pts.top_right, pts.top_left, mid(pts.left_hem, pts.right_hem)];
      dst = [{ x: W * 0.30, y: H * 0.24 }, { x: W * 0.70, y: H * 0.24 }, { x: W * 0.5, y: H * 0.7 }];
    } else if (has("left_waist") && has("left_hem")) {       // skirt
      src = [pts.right_waist, pts.left_waist, mid(pts.left_hem, pts.right_hem)];
      dst = [{ x: W * 0.42, y: H * 0.58 }, { x: W * 0.58, y: H * 0.58 }, { x: W * 0.5, y: H * 0.95 }];
    } else if (has("left_shoulder") && has("left_hem")) {    // top / dupatta
      src = [pts.right_shoulder, pts.left_shoulder, mid(pts.left_hem, pts.right_hem)];
      dst = [{ x: W * 0.30, y: H * 0.26 }, { x: W * 0.70, y: H * 0.26 }, { x: W * 0.5, y: H * 0.66 }];
    }
    if (src && dst) {
      const m = solveAffine3(src, dst);
      if (m) {
        ctx.save();
        ctx.globalAlpha = 0.95;
        ctx.setTransform(m.a, m.b, m.c, m.d, m.e, m.f);
        ctx.drawImage(im, 0, 0);
        ctx.restore();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
      }
    }
  }, [pts, dims, scheme]);

  const nextTarget = () => scheme.order.find((n) => !pts[n]);
  const imgPos = (e: React.MouseEvent) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: (e.clientX - r.left) / scaleRef.current, y: (e.clientY - r.top) / scaleRef.current };
  };
  const hit = (p: Pt) => {
    const tol = 10 / scaleRef.current;
    let best: string | null = null, bd = tol;
    for (const n of scheme.order) {
      const q = pts[n]; if (!q) continue;
      const d = Math.hypot(q.x - p.x, q.y - p.y);
      if (d <= bd) { bd = d; best = n; }
    }
    return best;
  };

  function onDown(e: React.MouseEvent) {
    if (!imgRef.current) return;
    const p = imgPos(e);
    const h = hit(p);
    if (h) { dragRef.current = h; return; }
    const t = nextTarget(); if (!t) return;
    setPts((prev) => ({ ...prev, [t]: p }));
  }
  function onMove(e: React.MouseEvent) {
    if (!dragRef.current) return;
    const p = imgPos(e);
    setPts((prev) => ({ ...prev, [dragRef.current as string]: p }));
  }
  function onUp() { dragRef.current = null; }

  function guess() {
    const im = imgRef.current; if (!im) return;
    // alpha bbox (falls back to full frame for opaque images)
    const c = document.createElement("canvas");
    c.width = dims[0]; c.height = dims[1];
    const cx = c.getContext("2d")!;
    cx.drawImage(im, 0, 0);
    let x0 = dims[0], y0 = dims[1], x1 = 0, y1 = 0, found = false;
    try {
      const d = cx.getImageData(0, 0, dims[0], dims[1]).data;
      const step = Math.max(1, Math.floor(Math.min(dims[0], dims[1]) / 400));
      for (let y = 0; y < dims[1]; y += step)
        for (let x = 0; x < dims[0]; x += step)
          if (d[(y * dims[0] + x) * 4 + 3] > 12) {
            found = true;
            if (x < x0) x0 = x; if (x > x1) x1 = x;
            if (y < y0) y0 = y; if (y > y1) y1 = y;
          }
    } catch { /* tainted */ }
    if (!found) { x0 = 0; y0 = 0; x1 = dims[0]; y1 = dims[1]; }
    const bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0);
    const p: Record<string, Pt> = {};
    for (const n of scheme.order) {
      const f = scheme.guess[n]; if (!f) continue;
      p[n] = { x: x0 + f[0] * bw, y: y0 + f[1] * bh };
    }
    setPts(p);
  }

  const placed = scheme.order.filter((n) => pts[n]).length;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs">
        <button onClick={guess} className="rounded border px-2 py-1">Guess (auto)</button>
        <button onClick={() => setPts({})} className="rounded border px-2 py-1">Reset</button>
        <span className="text-neutral-500">{placed}/{scheme.order.length} points</span>
      </div>
      <div className="overflow-auto rounded border border-neutral-200 bg-neutral-100" style={{ maxHeight: "60vh" }}>
        <canvas
          ref={canvasRef}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onUp}
          className="block cursor-crosshair"
        />
        {!imageSrc && <div className="p-6 text-center text-sm text-neutral-400">Upload an image to annotate</div>}
      </div>
      <div className="mt-2 flex gap-3">
        <ol className="flex-1 space-y-0.5 text-[11px]">
          {scheme.order.map((n) => (
            <li key={n} className={pts[n] ? "text-emerald-600" : "text-neutral-500"}>
              {pts[n] ? "✓ " : "• "}{n} — <span className="text-neutral-400">{scheme.hints[n]}</span>
            </li>
          ))}
        </ol>
        <div className="shrink-0 text-center">
          <canvas ref={previewRef} width={140} height={210}
            className="rounded border border-neutral-200" />
          <p className="mt-0.5 text-[10px] text-neutral-400">live preview</p>
        </div>
      </div>
    </div>
  );
});

export default Annotator;
