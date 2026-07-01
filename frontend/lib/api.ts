import type { Garment, TryOnResult, MeasureResult } from "./store";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function fetchGarments(): Promise<Garment[]> {
  const res = await fetch(`${API_BASE}/api/garments`);
  if (!res.ok) throw new Error("Failed to load garments");
  return res.json();
}

export type TryOnOpts = { debug?: boolean; occlude?: boolean; lighting?: boolean; tps?: boolean };

export async function requestTryOn(
  garmentId: string,
  photo: File,
  opts: TryOnOpts = {}
): Promise<TryOnResult> {
  const form = new FormData();
  form.append("garment_id", garmentId);
  form.append("photo", photo);
  if (opts.debug) form.append("debug", "true");
  // realism flags (occlude defaults on server-side to true)
  if (opts.occlude === false) form.append("occlude", "false");
  if (opts.lighting) form.append("lighting", "true");
  if (opts.tps) form.append("tps", "true");
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

// --- Garment management (Phase C) ------------------------------------------
export type Keypoints = {
  keypoints_norm?: Record<string, [number, number]>;
  keypoints_px?: Record<string, [number, number]>;
  canvas?: [number, number];
};

async function jf(path: string, opts: RequestInit): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const getGarment = (id: string) => jf(`/api/garments/${id}`, { method: "GET" });

export const createGarment = (b: {
  id?: string; name: string; category: string; size_chart?: any;
  fit_params?: Record<string, number>; image_only?: boolean;
}) => jf(`/api/garments`, { method: "POST", body: JSON.stringify(b) });

export const updateGarment = (id: string, b: Record<string, unknown>) =>
  jf(`/api/garments/${id}`, { method: "PUT", body: JSON.stringify(b) });

export const archiveGarment = (id: string) =>
  fetch(`${API_BASE}/api/garments/${id}`, { method: "DELETE" }).then((r) => r.json());

export async function uploadGarmentImage(
  id: string, file: File, role?: string, removeBg = false
) {
  const form = new FormData();
  form.append("photo", file);
  if (role) form.append("role", role);
  if (removeBg) form.append("remove_bg", "true");
  const res = await fetch(`${API_BASE}/api/garments/${id}/image`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Upload failed");
  return res.json();
}

export const listVersions = (id: string) =>
  jf(`/api/garments/${id}/versions`, { method: "GET" });

export const revertVersion = (id: string, versionId: string) =>
  jf(`/api/garments/${id}/revert/${versionId}`, { method: "POST" });

export const saveAnnotation = (id: string, keypoints: Keypoints, role?: string) =>
  jf(`/api/garments/${id}/annotation`, {
    method: "POST",
    body: JSON.stringify({ keypoints, role: role || null }),
  });

export function assetUrl(path: string): string {
  return `${API_BASE}/assets/${path}`;
}

export function resultUrl(path: string): string {
  return `${API_BASE}${path}`;
}
