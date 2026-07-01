"use client";

import { useEffect, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { assetUrl } from "@/lib/api";
import {
  EMASmoother,
  LM,
  Pt,
  bodyTargets,
  pantTargets,
  skirtTargets,
  kindFor,
  topHem,
  solveAffine3,
} from "@/lib/liveFit";

// Normalized garment anchors (0..1 within the PNG), loaded per-garment from
// its keypoint JSON. For tops these are shoulders + hem midpoint; for pants
// they are the waist corners + ankle midpoint.
type Anchors = {
  a: [number, number]; // top-right anchor (right shoulder / right waist)
  b: [number, number]; // top-left anchor (left shoulder / left waist)
  c: [number, number]; // bottom anchor (hem mid / ankle mid)
};
type NormPoint = [number, number];
type AnnotationPoint = { name: string; x: number; y: number }; // normalized 0..1
type AffineMatrix = { a: number; b: number; c: number; d: number; e: number; f: number };

const FALLBACK_ANCHORS: Anchors = {
  a: [0.3, 0.2143],
  b: [0.7, 0.2143],
  c: [0.5, 0.8857],
};

// kindFor maps category -> top | pant | skirt | lehenga (lehenga live = skirt).
// Saree is image-mode only (multi-region drape) — not supported in live.
const isImageOnly = (cat?: string) => (cat || "").toLowerCase() === "saree";

const MIN_VISIBILITY = 0.5; // skip overlay if shoulders aren't confidently seen
const LOST_GRACE_MS = 500; // keep last garment briefly when pose flickers

export default function LivePreview() {
  const { selectedGarment } = useStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const garmentImgRef = useRef<HTMLImageElement | null>(null);
  const anchorsRef = useRef<Anchors>(FALLBACK_ANCHORS);
  const annotationRef = useRef<AnnotationPoint[]>([]);
  const rafRef = useRef<number | null>(null);
  const landmarkerRef = useRef<any>(null);
  const smootherRef = useRef(new EMASmoother(0.4));
  const lastSeenRef = useRef<number>(0);

  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("");
  const [mirror, setMirror] = useState(true);
  const [fps, setFps] = useState(0);
  const [poseOk, setPoseOk] = useState(false);
  const [showDupatta, setShowDupatta] = useState(true);
  // Debug overlays (refs because the render loop reads them every frame).
  const [poseDebug, setPoseDebug] = useState(false);
  const [annoDebug, setAnnoDebug] = useState(false);
  const showDupattaRef = useRef(true);
  const poseDebugRef = useRef(false);
  const annoDebugRef = useRef(false);
  useEffect(() => { showDupattaRef.current = showDupatta; }, [showDupatta]);
  useEffect(() => { poseDebugRef.current = poseDebug; }, [poseDebug]);
  useEffect(() => { annoDebugRef.current = annoDebug; }, [annoDebug]);
  const isDupatta = (selectedGarment?.category || "").toLowerCase() === "dupatta";
  const [garmentError, setGarmentError] = useState(false);

  // Preload selected garment image + anchors
  useEffect(() => {
    if (!selectedGarment) return;
    garmentImgRef.current = null;
    setGarmentError(false);
    const img = new Image();
    // No crossOrigin: we only display the live canvas, never read its pixels,
    // so canvas tainting is harmless and we avoid a CORS failure mode.
    img.src = assetUrl(selectedGarment.image);
    img.onload = () => (garmentImgRef.current = img);
    img.onerror = () => setGarmentError(true);

    anchorsRef.current = FALLBACK_ANCHORS;
    annotationRef.current = [];
    const kind = kindFor(selectedGarment.category);
    fetch(assetUrl(selectedGarment.keypoints))
      .then((r) => r.json())
      .then((j) => {
        const raw = j.keypoints_norm || {};
        const n = Object.fromEntries(
          Object.entries(raw).filter(([, p]) =>
            Array.isArray(p) &&
            p.length >= 2 &&
            Number.isFinite(p[0]) &&
            Number.isFinite(p[1])
          )
        ) as Record<string, NormPoint>;
        annotationRef.current = collectAnnotationPoints(j);
        const hemMid = (l: string, r: string): NormPoint | null => {
          if (!n[l] || !n[r]) return null;
          return [
            (n[l][0] + n[r][0]) / 2,
            (n[l][1] + n[r][1]) / 2,
          ];
        };
        if (kind === "pant") {
          const ankle = hemMid("left_ankle", "right_ankle");
          if (!n.right_waist || !n.left_waist || !ankle) return;
          anchorsRef.current = {
            a: n.right_waist, b: n.left_waist,
            c: ankle,
          };
        } else if (kind === "skirt" || kind === "lehenga") {
          // lehenga's primary keypoints file is the skirt (waist + hem)
          const hem = hemMid("left_hem", "right_hem");
          if (!n.right_waist || !n.left_waist || !hem) return;
          anchorsRef.current = {
            a: n.right_waist, b: n.left_waist,
            c: hem,
          };
        } else {
          const hem = hemMid("left_hem", "right_hem");
          if (!n.right_shoulder || !n.left_shoulder || !hem) return;
          anchorsRef.current = {
            a: n.right_shoulder, b: n.left_shoulder,
            c: hem,
          };
        }
      })
      .catch(() => {});
  }, [selectedGarment]);

  function collectAnnotationPoints(j: any): AnnotationPoint[] {
    const seen = new Set<string>();
    const out: AnnotationPoint[] = [];
    const canvas = Array.isArray(j?.canvas) ? j.canvas : [1, 1];
    const canvasW = Number(canvas[0]) || 1;
    const canvasH = Number(canvas[1]) || 1;
    const add = (name: string, x: number, y: number) => {
      if (!name || seen.has(name) || !Number.isFinite(x) || !Number.isFinite(y)) return;
      seen.add(name);
      out.push({ name, x, y });
    };
    const addMap = (
      map: unknown,
      scaleX: number,
      scaleY: number,
      prefix = ""
    ) => {
      if (!map || typeof map !== "object") return;
      Object.entries(map as Record<string, unknown>).forEach(([name, p]) => {
        if (Array.isArray(p) && p.length >= 2) {
          add(`${prefix}${name}`, Number(p[0]) * scaleX, Number(p[1]) * scaleY);
        }
      });
    };

    addMap(j?.keypoints_norm, 1, 1);
    addMap(j?.keypoints_px, 1 / canvasW, 1 / canvasH);
    addMap(j?.points_norm, 1, 1);
    addMap(j?.points_px, 1 / canvasW, 1 / canvasH);
    addMap(j?.points, 1 / canvasW, 1 / canvasH);
    if (j?.pieces && typeof j.pieces === "object") {
      Object.entries(j.pieces as Record<string, any>).forEach(([piece, data]) => {
        addMap(data?.keypoints_norm, 1, 1, `${piece}.`);
        addMap(data?.keypoints_px, 1 / canvasW, 1 / canvasH, `${piece}.`);
        addMap(data?.points_norm, 1, 1, `${piece}.`);
        addMap(data?.points_px, 1 / canvasW, 1 / canvasH, `${piece}.`);
        addMap(data?.points, 1 / canvasW, 1 / canvasH, `${piece}.`);
      });
    }
    return out;
  }

  async function start() {
    setStatus("Loading pose model…");
    try {
      const vision = await import("@mediapipe/tasks-vision");
      const { FilesetResolver, PoseLandmarker } = vision;
      const fileset = await FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
      );
      landmarkerRef.current = await PoseLandmarker.createFromOptions(fileset, {
        baseOptions: {
          modelAssetPath:
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
          delegate: "GPU",
        },
        runningMode: "VIDEO",
        numPoses: 1,
      });

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720 },
      });
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play();
      smootherRef.current.reset();
      setActive(true);
      setStatus("");
      loop();
    } catch (e: any) {
      setStatus(`Could not start camera/model: ${e.message ?? e}`);
    }
  }

  function stop() {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    const video = videoRef.current;
    const stream = video?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (video) video.srcObject = null;
    setActive(false);
    setPoseOk(false);
  }

  function loop() {
    const video = videoRef.current!;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const landmarker = landmarkerRef.current;

    let frames = 0;
    let fpsT0 = performance.now();

    const render = () => {
      if (video.readyState >= 2) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const res = landmarker.detectForVideo(video, performance.now());
        const lm = res.landmarks?.[0];
        const g = garmentImgRef.current;

        // Gate on landmark *presence*, not visibility: tasks-vision frequently
        // reports visibility 0/undefined even for good detections, so a
        // visibility threshold would reject every valid frame. We only use
        // visibility to suppress clearly-occluded shoulders, and only when the
        // model actually provides a non-zero score.
        const hasPose = !!lm && lm.length > LM.rightHip;
        const lvis = lm?.[LM.leftShoulder]?.visibility ?? 0;
        const rvis = lm?.[LM.rightShoulder]?.visibility ?? 0;
        const visScored = lvis > 0 || rvis > 0; // model populated visibility?
        const visOk =
          hasPose && (!visScored || Math.max(lvis, rvis) > MIN_VISIBILITY);

        if (lm && visOk) {
          // Pose is detected regardless of whether the garment image is ready.
          lastSeenRef.current = performance.now();
          setPoseOk(true);
          const garmentMatrix = g ? drawGarment(ctx, canvas, lm, g) : null;
          if (annoDebugRef.current) drawAnnoDebug(ctx, g, garmentMatrix);
          if (poseDebugRef.current) drawPoseDebug(ctx, canvas, lm);
        } else {
          const lostFor = performance.now() - lastSeenRef.current;
          if (lostFor > LOST_GRACE_MS) {
            setPoseOk(false);
            smootherRef.current.reset();
          }
        }

        // FPS (rolling, updated ~2x/sec)
        frames++;
        const now = performance.now();
        if (now - fpsT0 > 500) {
          setFps(Math.round((frames * 1000) / (now - fpsT0)));
          frames = 0;
          fpsT0 = now;
        }
      }
      rafRef.current = requestAnimationFrame(render);
    };
    render();
  }

  // Shared: the 3 affine target points (where the garment's anchors land) for
  // the current garment category, from smoothed landmarks.
  function targetsFor(lm: any[], W: number, H: number): [Pt, Pt, Pt] {
    const px = (i: number): Pt => ({ x: lm[i].x * W, y: lm[i].y * H });
    const kind = kindFor(selectedGarment?.category);
    if (kind === "pant") {
      const s = smootherRef.current.smooth({
        rightHip: px(LM.rightHip), leftHip: px(LM.leftHip),
        rightAnkle: px(LM.rightAnkle), leftAnkle: px(LM.leftAnkle),
      } as any) as any;
      const { rw, lw, ankle } = pantTargets(s);
      return [rw, lw, ankle];
    }
    if (kind === "skirt" || kind === "lehenga") {
      const s = smootherRef.current.smooth({
        rightHip: px(LM.rightHip), leftHip: px(LM.leftHip),
        rightAnkle: px(LM.rightAnkle), leftAnkle: px(LM.leftAnkle),
      } as any) as any;
      const { rw, lw, hemMid } = skirtTargets(s);
      return [rw, lw, hemMid];
    }
    const s = smootherRef.current.smooth({
      rightShoulder: px(LM.rightShoulder), leftShoulder: px(LM.leftShoulder),
      rightHip: px(LM.rightHip), leftHip: px(LM.leftHip),
    } as any) as any;
    const { rs, ls, hemMid } = bodyTargets(s, topHem(selectedGarment?.category));
    return [rs, ls, hemMid];
  }

  function affineFor(
    lm: any[],
    canvas: HTMLCanvasElement,
    g: HTMLImageElement
  ): AffineMatrix | null {
    const dst = targetsFor(lm, canvas.width, canvas.height);

    // Garment source points in image pixels (a/b/c = top-right, top-left, bottom)
    const a = anchorsRef.current;
    const src: [Pt, Pt, Pt] = [
      { x: a.a[0] * g.width, y: a.a[1] * g.height },
      { x: a.b[0] * g.width, y: a.b[1] * g.height },
      { x: a.c[0] * g.width, y: a.c[1] * g.height },
    ];
    return solveAffine3(src, dst);
  }

  function drawGarment(
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    lm: any[],
    g: HTMLImageElement
  ): AffineMatrix | null {
    if (isImageOnly(selectedGarment?.category)) return null; // saree: image mode only
    if ((selectedGarment?.category || "").toLowerCase() === "dupatta" &&
        !showDupattaRef.current) return null; // dupatta toggled off
    const m = affineFor(lm, canvas, g);
    if (!m) return null;

    ctx.save();
    ctx.globalAlpha = 0.95;
    ctx.setTransform(m.a, m.b, m.c, m.d, m.e, m.f);
    ctx.drawImage(g, 0, 0);
    ctx.restore();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return m;
  }

  // Annotation/fit debug: project every annotation.json keypoint through the
  // same affine matrix used for the live garment, so the dots show where each
  // annotated garment point landed on the body.
  function drawAnnoDebug(
    ctx: CanvasRenderingContext2D,
    g: HTMLImageElement | null,
    m: AffineMatrix | null
  ) {
    if (!g || !m) return;
    const points = annotationRef.current;
    if (!points.length) return;
    const project = (p: AnnotationPoint): Pt => ({
      x: m.a * (p.x * g.width) + m.c * (p.y * g.height) + m.e,
      y: m.b * (p.x * g.width) + m.d * (p.y * g.height) + m.f,
    });
    const projected = points.map((p) => [p.name, project(p)] as const);
    const anchorPoints = [anchorsRef.current.a, anchorsRef.current.b, anchorsRef.current.c].map(
      ([x, y]) => ({ name: "", x, y })
    ).map(project);

    ctx.save();
    ctx.strokeStyle = "#f97316";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(anchorPoints[0].x, anchorPoints[0].y);
    ctx.lineTo(anchorPoints[1].x, anchorPoints[1].y);
    ctx.lineTo(anchorPoints[2].x, anchorPoints[2].y);
    ctx.closePath();
    ctx.stroke();

    projected.forEach(([name, p]) => {
      ctx.fillStyle = "#06b6d4";
      ctx.beginPath();
      ctx.arc(p.x, p.y, 5, 0, 7);
      ctx.fill();
      ctx.strokeStyle = "#083344";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = "rgba(8, 51, 68, 0.86)";
      ctx.font = "11px system-ui";
      const label = name.replace(/_/g, " ");
      const w = ctx.measureText(label).width;
      ctx.fillRect(p.x + 7, p.y - 18, w + 8, 16);
      ctx.fillStyle = "#ecfeff";
      ctx.fillText(label, p.x + 11, p.y - 6);
    });
    const count = `${points.length} annotation points`;
    ctx.font = "12px system-ui";
    const w = ctx.measureText(count).width;
    ctx.fillStyle = "rgba(8, 51, 68, 0.86)";
    ctx.fillRect(10, 10, w + 16, 22);
    ctx.fillStyle = "#ecfeff";
    ctx.fillText(count, 18, 26);
    ctx.restore();
  }

  // Pose debug: full skeleton plus every MediaPipe pose landmark point.
  function drawPoseDebug(ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, lm: any[]) {
    const W = canvas.width, H = canvas.height;
    const P = (i: number) => ({ x: lm[i].x * W, y: lm[i].y * H });
    const bones: [number, number][] = [
      [LM.leftShoulder, LM.rightShoulder], [LM.leftShoulder, LM.leftElbow],
      [LM.leftElbow, LM.leftWrist], [LM.rightShoulder, LM.rightElbow],
      [LM.rightElbow, LM.rightWrist], [LM.leftShoulder, LM.leftHip],
      [LM.rightShoulder, LM.rightHip], [LM.leftHip, LM.rightHip],
      [LM.leftHip, LM.leftKnee], [LM.leftKnee, LM.leftAnkle],
      [LM.rightHip, LM.rightKnee], [LM.rightKnee, LM.rightAnkle],
    ];
    ctx.save();
    ctx.strokeStyle = "#22c55e"; ctx.lineWidth = 3;
    for (const [i, j] of bones) {
      if (!lm[i] || !lm[j]) continue;
      const p = P(i), q = P(j);
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
    }
    lm.forEach((point, i) => {
      if (!point) return;
      const p = P(i);
      ctx.fillStyle = "#16a34a";
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4, 0, 7);
      ctx.fill();
      ctx.strokeStyle = "#dcfce7";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = "rgba(20, 83, 45, 0.82)";
      ctx.font = "10px system-ui";
      const label = String(i);
      const w = ctx.measureText(label).width;
      ctx.fillRect(p.x + 5, p.y - 14, w + 6, 13);
      ctx.fillStyle = "#f0fdf4";
      ctx.fillText(label, p.x + 8, p.y - 4);
    });
    ctx.restore();
  }

  useEffect(() => () => stop(), []);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium text-neutral-700">Live preview</h2>
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          {active && (
            <>
              <span className={fps >= 24 ? "text-emerald-600" : "text-amber-600"}>
                {fps} FPS
              </span>
              <span className={poseOk ? "text-emerald-600" : "text-neutral-400"}>
                {poseOk ? "● tracking" : "○ no pose"}
              </span>
            </>
          )}
          <button
            onClick={active ? stop : start}
            className="rounded-md border border-neutral-300 px-3 py-1 font-medium text-neutral-700 hover:bg-neutral-100 disabled:opacity-50"
          >
            {active ? "Stop camera" : "Start camera"}
          </button>
        </div>
      </div>

      <div className="relative aspect-video overflow-hidden rounded-lg border border-neutral-200 bg-neutral-900">
        {/* Rendered (not display:none) but hidden behind the canvas, so the
            browser keeps decoding frames for MediaPipe to read. */}
        <video
          ref={videoRef}
          playsInline
          muted
          className="pointer-events-none absolute inset-0 h-px w-px opacity-0"
        />
        <canvas
          ref={canvasRef}
          className="h-full w-full object-contain"
          style={{ transform: mirror ? "scaleX(-1)" : "none" }}
        />
        {!active && (
          <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-neutral-400">
            {status ||
              (isImageOnly(selectedGarment?.category)
                ? "Saree is image-mode only — use the HD Image Try-On tab"
                : "Press Start camera — pick a garment now or after it starts")}
          </div>
        )}
        {active && isImageOnly(selectedGarment?.category) && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs text-white">
            Saree is image-mode only — switch to HD Image Try-On
          </div>
        )}
        {active && !selectedGarment && poseOk && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs text-white">
            Pick a garment to overlay it
          </div>
        )}
        {active && !poseOk && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs text-white">
            Step back so your head and torso are in frame
          </div>
        )}
        {active && poseOk && garmentError && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-red-600/80 px-3 py-1 text-xs text-white">
            Pose OK — but the garment image failed to load (check the backend /assets URL)
          </div>
        )}
      </div>

      {active && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={mirror}
              onChange={(e) => setMirror(e.target.checked)}
            />
            Mirror (selfie view)
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={poseDebug}
              onChange={(e) => setPoseDebug(e.target.checked)}
            />
            Pose debug (skeleton)
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={annoDebug}
              onChange={(e) => setAnnoDebug(e.target.checked)}
            />
            Annotation debug (all keypoints)
          </label>
          {isDupatta && (
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={showDupatta}
                onChange={(e) => setShowDupatta(e.target.checked)}
              />
              Show dupatta
            </label>
          )}
        </div>
      )}
    </div>
  );
}
