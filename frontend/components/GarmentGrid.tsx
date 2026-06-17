"use client";

import { useStore } from "@/lib/store";
import { assetUrl } from "@/lib/api";

export default function GarmentGrid() {
  const { garments, selectedGarment, selectGarment } = useStore();

  return (
    <div>
      <h2 className="mb-2 text-sm font-medium text-neutral-700">2 · Pick a garment</h2>
      <div className="grid grid-cols-3 gap-3">
        {garments.map((g) => {
          const active = selectedGarment?.id === g.id;
          return (
            <button
              key={g.id}
              onClick={() => selectGarment(g)}
              className={`group rounded-lg border bg-white p-2 text-left transition ${
                active
                  ? "border-blue-500 ring-2 ring-blue-200"
                  : "border-neutral-200 hover:border-neutral-400"
              }`}
            >
              <div className="aspect-square overflow-hidden rounded bg-neutral-100">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={assetUrl(g.image)}
                  alt={g.name}
                  className="h-full w-full object-contain"
                />
              </div>
              <p className="mt-1 truncate text-xs text-neutral-600">{g.name}</p>
            </button>
          );
        })}
        {garments.length === 0 && (
          <p className="col-span-3 text-sm text-neutral-400">
            No garments loaded. Is the backend running?
          </p>
        )}
      </div>
    </div>
  );
}
