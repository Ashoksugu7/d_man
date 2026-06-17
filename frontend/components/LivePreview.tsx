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
const FALLBACK_ANCHORS: Anchors = {
  a: [0.3, 0.2143],
  b: [0.7, 0.2143],
  c: [0.5, 0.8857],
};

const isPant = (cat?: string) => (cat || "").toLowerCase() === "pant";

const MIN_VISIBILITY = 0.5; // skip overlay if shoulders aren't confidently seen
const LOST_GRACE_MS = 500; // keep last garment briefly when pose flickers

export default function LivePreview() {
  const { selectedGarment } = useStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const garmentImgRef = useRef<HTMLImageElement | null>(null);
  const anchorsRef = useRef<Anchors>(FALLBACK_ANCHORS);
  const rafRef = useRef<number | null>(null);
  const landmarkerRef = useRef<any>(null);
  const smootherRef = useRef(new EMASmoother(0.4));
  const lastSeenRef = useRef<number>(0);

  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("");
  const [mirror, setMirror] = useState(true);
  const [showLandmarks, setShowLandmarks] = useState(false);
  const [fps, setFps] = useState(0);
  const [poseOk, setPoseOk] = useState(false);
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
    const pant = isPant(selectedGarment.category);
    fetch(assetUrl(selectedGarment.keypoints))
      .then((r) => r.json())
      .then((j) => {
        const n = j.keypoints_norm;
        if (!n) return;
        anchorsRef.current = pant
          ? {
              a: n.right_waist,
              b: n.left_waist,
              c: [
                (n.left_ankle[0] + n.right_ankle[0]) / 2,
                (n.left_ankle[1] + n.right_ankle[1]) / 2,
              ],
            }
          : {
              a: n.right_shoulder,
              b: n.left_shoulder,
              c: [
                (n.left_hem[0] + n.right_hem[0]) / 2,
                (n.left_hem[1] + n.right_hem[1]) / 2,
              ],
            };
      })
      .catch(() => {});
  }, [selectedGarment]);

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
          if (g) drawGarment(ctx, canvas, lm, g);
          if (showLandmarks) drawLandmarks(ctx, canvas, lm);
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

  function drawGarment(
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    lm: any[],
    g: HTMLImageElement
  ) {
    const W = canvas.width;
    const H = canvas.height;
    const px = (i: number): Pt => ({ x: lm[i].x * W, y: lm[i].y * H });
    const pant = isPant(selectedGarment?.category);

    // Smooth the landmarks this garment needs, then build the 3 body targets.
    let dst: [Pt, Pt, Pt];
    if (pant) {
      const raw = {
        rightHip: px(LM.rightHip),
        leftHip: px(LM.leftHip),
        rightAnkle: px(LM.rightAnkle),
        leftAnkle: px(LM.leftAnkle),
      };
      const s = smootherRef.current.smooth(
        raw as unknown as Record<string, Pt>
      ) as unknown as typeof raw;
      const { rw, lw, ankle } = pantTargets(s);
      dst = [rw, lw, ankle];
    } else {
      const raw = {
        rightShoulder: px(LM.rightShoulder),
        leftShoulder: px(LM.leftShoulder),
        rightHip: px(LM.rightHip),
        leftHip: px(LM.leftHip),
      };
      const s = smootherRef.current.smooth(
        raw as unknown as Record<string, Pt>
      ) as unknown as typeof raw;
      const { rs, ls, hemMid } = bodyTargets(s);
      dst = [rs, ls, hemMid];
    }

    // Garment source points in image pixels (a/b/c = top-right, top-left, bottom)
    const a = anchorsRef.current;
    const gw = g.width;
    const gh = g.height;
    const src: [Pt, Pt, Pt] = [
      { x: a.a[0] * gw, y: a.a[1] * gh },
      { x: a.b[0] * gw, y: a.b[1] * gh },
      { x: a.c[0] * gw, y: a.c[1] * gh },
    ];

    const m = solveAffine3(src, dst);
    if (!m) return;

    ctx.save();
    ctx.globalAlpha = 0.95;
    ctx.setTransform(m.a, m.b, m.c, m.d, m.e, m.f);
    ctx.drawImage(g, 0, 0);
    ctx.restore();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  function drawLandmarks(
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    lm: any[]
  ) {
    const W = canvas.width;
    const H = canvas.height;
    const pts = isPant(selectedGarment?.category)
      ? [LM.leftHip, LM.rightHip, LM.leftAnkle, LM.rightAnkle]
      : [LM.leftShoulder, LM.rightShoulder, LM.leftHip, LM.rightHip];
    ctx.fillStyle = "#22c55e";
    for (const i of pts) {
      ctx.beginPath();
      ctx.arc(lm[i].x * W, lm[i].y * H, 6, 0, 7);
      ctx.fill();
    }
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
            disabled={!selectedGarment}
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
              (selectedGarment
                ? "Press Start camera for a real-time overlay"
                : "Select a garment first")}
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
        <div className="mt-2 flex gap-4 text-xs text-neutral-500">
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
              checked={showLandmarks}
              onChange={(e) => setShowLandmarks(e.target.checked)}
            />
            Show landmarks
          </label>
        </div>
      )}
    </div>
  );
}
