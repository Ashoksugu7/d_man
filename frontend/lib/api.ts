import type { Garment, TryOnResult } from "./store";

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

export function assetUrl(path: string): string {
  return `${API_BASE}/assets/${path}`;
}

export function resultUrl(path: string): string {
  return `${API_BASE}${path}`;
}
