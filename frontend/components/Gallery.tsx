"use client";

import { useEffect, useState } from "react";
import { GalleryItem, clearGallery, loadGallery } from "@/lib/gallery";

export default function Gallery({ refreshKey }: { refreshKey?: number }) {
  const [items, setItems] = useState<GalleryItem[]>([]);

  useEffect(() => {
    setItems(loadGallery());
  }, [refreshKey]);

  if (items.length === 0) {
    return (
      <div>
        <h2 className="mb-2 text-sm font-medium text-neutral-700">Your history</h2>
        <p className="text-xs text-neutral-400">
          HD try-on results you generate will appear here (saved in this browser).
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium text-neutral-700">
          Your history ({items.length})
        </h2>
        <button
          onClick={() => setItems(clearGallery())}
          className="text-xs text-neutral-400 hover:text-red-600"
        >
          Clear
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
        {items.map((it) => (
          <a
            key={it.id}
            href={it.resultUrl}
            target="_blank"
            rel="noreferrer"
            className="group block overflow-hidden rounded-lg border border-neutral-200 bg-white"
            title={`${it.garmentName} · ${new Date(it.createdAt).toLocaleString()}`}
          >
            <div className="aspect-[3/4] bg-neutral-100">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={it.resultUrl}
                alt={it.garmentName}
                className="h-full w-full object-contain"
              />
            </div>
            <div className="flex items-center justify-between px-1.5 py-1">
              <span className="truncate text-[11px] text-neutral-600">
                {it.garmentName}
              </span>
              {it.mode === "hd" && (
                <span className="rounded bg-violet-100 px-1 text-[9px] font-medium text-violet-700">
                  HD
                </span>
              )}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
