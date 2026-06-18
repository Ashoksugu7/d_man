import type { Garment, TryOnResult, MeasureResult } from "./store";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function fetchGarments(): Promise<Garment[]> {
  const res = await fetch(`${API_BASE}/api/garments`);
  if (!res.ok) throw new Error("Failed to load garments");
  return res.json();
}

export async function requestTryOn(
  garmentId: string,
  photo: File,
  debug = false
): Promise<TryOnResult> {
  const form = new FormData();
  form.append("garment_id", garmentId);
  form.append("photo", photo);
  if (debug) form.append("debug", "true");
  const res = await fetch(`${API_BASE}/api/tryon/image`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Try-on failed");
  }
  return res.json();
}

export async function requestMeasurements(
  photo: File,
  heightCm: number
): Promise<MeasureResult> {
  const form = new FormData();
  form.append("photo", photo);
  form.append("height_cm", String(heightCm));
  const res = await fetch(`${API_BASE}/api/measure`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Measurement failed");
  }
  return res.json();
}

// --- HD (async diffusion) try-on -------------------------------------------
export type HdJobStatus = {
  job_id: string;
  status: string; // queued | pending | progress | started | success | failure
  progress?: number;
  message?: string;
  result_url?: string;
  result_id?: string;
  engine?: string;
  error?: string;
};

export async function submitHdJob(
  garmentId: string,
  photo: File,
  outputFormat = "png"
): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("garment_id", garmentId);
  form.append("photo", photo);
  form.append("output_format", outputFormat);
  const res = await fetch(`${API_BASE}/api/tryon/hd`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to submit HD job");
  }
  return res.json();
}

export async function pollHdJob(jobId: string): Promise<HdJobStatus> {
  const res = await fetch(`${API_BASE}/api/tryon/hd/${jobId}`);
  if (!res.ok) throw new Error("Failed to poll HD job");
  return res.json();
}

export function assetUrl(path: string): string {
  return `${API_BASE}/assets/${path}`;
}

export function resultUrl(path: string): string {
  return `${API_BASE}${path}`;
}
