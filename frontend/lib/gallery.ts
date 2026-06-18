// Try-on history persisted in the browser (localStorage). Phase 3 "result
// gallery" + the Phase 1 "store try-on results in localStorage" item.

export type GalleryItem = {
  id: string;
  garmentId: string;
  garmentName: string;
  resultUrl: string; // absolute URL
  mode: "hd" | "image";
  engine?: string;
  createdAt: number;
};

const KEY = "tryon_gallery_v1";
const MAX = 40;

export function loadGallery(): GalleryItem[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function addToGallery(item: GalleryItem): GalleryItem[] {
  const next = [item, ...loadGallery()].slice(0, MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* quota / private mode — ignore */
  }
  return next;
}

export function clearGallery(): GalleryItem[] {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  return [];
}
