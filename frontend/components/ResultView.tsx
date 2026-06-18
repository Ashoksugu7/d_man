"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import {
  requestTryOn,
  requestMeasurements,
  submitHdJob,
  pollHdJob,
  resultUrl,
} from "@/lib/api";
import { addToGallery } from "@/lib/gallery";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function ResultView({ onGalleryUpdate }: { onGalleryUpdate?: () => void }) {
  const {
    photo,
    photoUrl,
    selectedGarment,
    result,
    loading,
    error,
    setResult,
    setLoading,
    setError,
    heightCm,
    measure,
    measuring,
    measureError,
    setHeightCm,
    setMeasure,
    setMeasuring,
    setMeasureError,
  } = useStore();

  const [debug, setDebug] = useState(false);
  const [hdProgress, setHdProgress] = useState<number | null>(null);
  const [hdMessage, setHdMessage] = useState("");
  const canRun = !!photo && !!selectedGarment && !loading && hdProgress === null;
  const canMeasure = !!photo && !!heightCm && heightCm > 0 && !measuring;

  function saveToGallery(r: { result_url: string; result_id: string; engine?: string }, mode: "hd" | "image") {
    if (!selectedGarment) return;
    addToGallery({
      id: r.result_id,
      garmentId: selectedGarment.id,
      garmentName: selectedGarment.name,
      resultUrl: resultUrl(r.result_url),
      mode,
      engine: r.engine,
      createdAt: Date.now(),
    });
    onGalleryUpdate?.();
  }

  async function run() {
    if (!photo || !selectedGarment) return;
    setLoading(true);
    setError(null);
    try {
      const r = await requestTryOn(selectedGarment.id, photo, debug);
      setResult(r);
      saveToGallery(r, "image");
    } catch (e: any) {
      setError(e.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function runHd() {
    if (!photo || !selectedGarment) return;
    setError(null);
    setHdProgress(0);
    setHdMessage("Submitting…");
    try {
      const { job_id } = await submitHdJob(selectedGarment.id, photo);
      // Poll until terminal state.
      for (let i = 0; i < 200; i++) {
        await sleep(1500);
        const s = await pollHdJob(job_id);
        if (typeof s.progress === "number") setHdProgress(s.progress);
        if (s.message) setHdMessage(s.message);
        if (s.status === "success" && s.result_url && s.result_id) {
          setResult({
            result_url: s.result_url,
            result_id: s.result_id,
            garment_id: selectedGarment.id,
          });
          saveToGallery(
            { result_url: s.result_url, result_id: s.result_id, engine: s.engine },
            "hd"
          );
          break;
        }
        if (s.status === "failure") throw new Error(s.error || "HD job failed");
      }
    } catch (e: any) {
      setError(e.message ?? "HD try-on failed");
    } finally {
      setHdProgress(null);
      setHdMessage("");
    }
  }

  async function checkFit() {
    if (!photo || !heightCm) return;
    setMeasuring(true);
    setMeasureError(null);
    try {
      const m = await requestMeasurements(photo, heightCm);
      setMeasure(m);
      if (!m.ok && m.message) setMeasureError(m.message);
    } catch (e: any) {
      setMeasureError(e.message ?? "Couldn't estimate measurements");
    } finally {
      setMeasuring(false);
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-sm font-medium text-neutral-700">3 · Result</h2>
      <div className="mb-2 flex gap-2">
        <button
          onClick={run}
          disabled={!canRun}
          className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
        >
          {loading ? "Generating…" : "Try it on"}
        </button>
        <button
          onClick={runHd}
          disabled={!photo || !selectedGarment || hdProgress !== null || loading}
          title="Higher-quality async render (diffusion-ready pipeline)"
          className="flex-1 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
        >
          {hdProgress !== null ? "Rendering…" : "HD render"}
        </button>
      </div>

      {hdProgress !== null && (
        <div className="mb-3">
          <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200">
            <div
              className="h-full bg-violet-600 transition-all"
              style={{ width: `${hdProgress}%` }}
            />
          </div>
          <p className="mt-1 text-[11px] text-neutral-500">
            {hdMessage} ({hdProgress}%)
          </p>
        </div>
      )}

      <label className="mb-3 flex items-center gap-2 text-xs text-neutral-500">
        <input
          type="checkbox"
          checked={debug}
          onChange={(e) => setDebug(e.target.checked)}
        />
        Debug overlay (show detected pose + fit target)
      </label>

      <div className="mb-3 rounded-lg border border-neutral-200 bg-neutral-50 p-3">
        <label className="block text-xs font-medium text-neutral-700">
          Your height (cm) — for size recommendations
        </label>
        <div className="mt-1.5 flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={260}
            inputMode="numeric"
            placeholder="e.g. 175"
            value={heightCm ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              setHeightCm(v === "" ? null : Number(v));
            }}
            className="w-24 rounded-md border border-neutral-300 px-2 py-1 text-sm"
          />
          <button
            onClick={checkFit}
            disabled={!canMeasure}
            className="rounded-md bg-neutral-800 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-neutral-900 disabled:cursor-not-allowed disabled:bg-neutral-300"
          >
            {measuring ? "Measuring…" : "Check my fit"}
          </button>
        </div>
        <p className="mt-1.5 text-[11px] leading-snug text-neutral-400">
          Approximate, from a single photo + your height. Stand back so your
          whole body (head to ankles) is in frame. Use as a guide, not exact
          sizing.
        </p>
        {measureError && (
          <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-[11px] text-amber-700">
            {measureError}
          </p>
        )}
        {measure?.ok && measure.measurements && (
          <p className="mt-2 text-[11px] text-neutral-500">
            Estimated · shoulders ~{measure.measurements.shoulder_width_cm}cm ·
            waist ~{measure.measurements.waist_circumference_cm}cm. Fit badges
            now shown on garments.
          </p>
        )}
      </div>

      {result?.pose_method && (
        <p
          className={`mb-3 rounded-md px-3 py-2 text-xs ${
            result.pose_method === "mediapipe"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-amber-50 text-amber-700"
          }`}
        >
          Pose detection: {result.pose_method}
          {result.pose_method !== "mediapipe" &&
            " — MediaPipe not installed; using a fixed-position guess (low accuracy). Install backend requirements."}
        </p>
      )}

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <figure>
          <figcaption className="mb-1 text-xs text-neutral-400">Before</figcaption>
          <div className="aspect-[3/4] overflow-hidden rounded-lg border border-neutral-200 bg-white">
            {photoUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photoUrl} alt="before" className="h-full w-full object-contain" />
            )}
          </div>
        </figure>
        <figure>
          <figcaption className="mb-1 text-xs text-neutral-400">After</figcaption>
          <div className="aspect-[3/4] overflow-hidden rounded-lg border border-neutral-200 bg-white">
            {result && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={resultUrl(result.result_url)}
                alt="after"
                className="h-full w-full object-contain"
              />
            )}
          </div>
        </figure>
      </div>

      {result && (
        <a
          href={resultUrl(result.result_url)}
          download={`tryon-${result.result_id}.${result.result_url.split(".").pop() || "png"}`}
          className="mt-3 inline-block rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-100"
        >
          Download result
        </a>
      )}
    </div>
  );
}
