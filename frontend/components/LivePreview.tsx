"use client";

import { useEffect, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { assetUrl } from "@/lib/api";

// Garment keypoints are baked into the JSON; for the live overlay we only
// need the normalized shoulder + hem anchors. We hardcode the canvas-relative
// anchors that match assets/generate_shirts.py so we avoid an extra fetch.
const GARMENT_ANCHORS = {
  // normalized within the garment PNG (W=600,H=700)
  right_shoulder: [0.3, 0.2143],
  left_shoulder: [0.7, 0.2143],
  hem_mid: [0.5, 0.8857],
};

// MediaPipe Pose landmark indices
const LS = 11; // left shoulder
const RS = 12; // right shoulder
const LH = 23; // left hip
const RH = 24; // right hip

export default function LivePreview() {
  const { selectedGarment } = useStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const garmentImgRef = useRef<HTMLImageElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const landmarkerRef = useRef<any>(null);
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("");

  // Preload the selected garment image for canvas drawing
  useEffect(() => {
    if (!selectedGarment) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = assetUrl(selectedGarment.image);
    img.onload = () => (garmentImgRef.current = img);
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

      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play();
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
  }

  function loop() {
    const video = videoRef.current!;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const landmarker = landmarkerRef.current;

    const render = () => {
      if (video.readyState >= 2) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const res = landmarker.detectForVideo(video, performance.now());
        const lm = res.landmarks?.[0];
        const g = garmentImgRef.current;
        if (lm && g) drawGarment(ctx, canvas, lm, g);
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
    const ls = { x: lm[LS].x * W, y: lm[LS].y * H };
    const rs = { x: lm[RS].x * W, y: lm[RS].y * H };
    const hipMid = {
      x: ((lm[LH].x + lm[RH].x) / 2) * W,
      y: ((lm[LH].y + lm[RH].y) / 2) * H,
    };

    // Garment anchor pixels in source image space
    const gw = g.width;
    const gh = g.height;
    const gRS = { x: GARMENT_ANCHORS.right_shoulder[0] * gw, y: GARMENT_ANCHORS.right_shoulder[1] * gh };
    const gLS = { x: GARMENT_ANCHORS.left_shoulder[0] * gw, y: GARMENT_ANCHORS.left_shoulder[1] * gh };

    // Affine: scale from shoulder distance, rotate to shoulder line,
    // translate to shoulder midpoint.
    const shoulderMid = { x: (ls.x + rs.x) / 2, y: (ls.y + rs.y) / 2 };
    const dx = ls.x - rs.x;
    const dy = ls.y - rs.y;
    const bodyShoulderW = Math.hypot(dx, dy);
    const garmentShoulderW = Math.hypot(gLS.x - gRS.x, gLS.y - gRS.y);
    const scale = (bodyShoulderW / garmentShoulderW) * 1.15;
    const angle = Math.atan2(dy, dx);

    const gShoulderMid = { x: (gLS.x + gRS.x) / 2, y: (gLS.y + gRS.y) / 2 };

    ctx.save();
    ctx.globalAlpha = 0.92;
    ctx.translate(shoulderMid.x, shoulderMid.y);
    ctx.rotate(angle);
    ctx.scale(scale, scale);
    ctx.drawImage(g, -gShoulderMid.x, -gShoulderMid.y);
    ctx.restore();
  }

  useEffect(() => () => stop(), []);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium text-neutral-700">Live preview (beta)</h2>
        <button
          onClick={active ? stop : start}
          disabled={!selectedGarment}
          className="rounded-md border border-neutral-300 px-3 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100 disabled:opacity-50"
        >
          {active ? "Stop camera" : "Start camera"}
        </button>
      </div>
      <div className="relative aspect-video overflow-hidden rounded-lg border border-neutral-200 bg-neutral-900">
        <video ref={videoRef} className="hidden" playsInline muted />
        <canvas ref={canvasRef} className="h-full w-full object-contain" />
        {!active && (
          <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-neutral-400">
            {status || (selectedGarment
              ? "Press Start camera for a real-time overlay"
              : "Select a garment first")}
          </div>
        )}
      </div>
    </div>
  );
}
