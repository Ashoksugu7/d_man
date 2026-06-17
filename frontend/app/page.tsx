"use client";

import { useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import { fetchGarments } from "@/lib/api";
import PhotoUpload from "@/components/PhotoUpload";
import GarmentGrid from "@/components/GarmentGrid";
import ResultView from "@/components/ResultView";
import LivePreview from "@/components/LivePreview";

export default function Home() {
  const { setGarments } = useStore();
  const [tab, setTab] = useState<"image" | "live">("image");

  useEffect(() => {
    fetchGarments()
      .then(setGarments)
      .catch(() => setGarments([]));
  }, [setGarments]);

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <button
          onClick={() => setTab("image")}
          className={`rounded-md px-4 py-1.5 text-sm font-medium ${
            tab === "image" ? "bg-neutral-900 text-white" : "bg-white text-neutral-600 border border-neutral-200"
          }`}
        >
          HD Image Try-On
        </button>
        <button
          onClick={() => setTab("live")}
          className={`rounded-md px-4 py-1.5 text-sm font-medium ${
            tab === "live" ? "bg-neutral-900 text-white" : "bg-white text-neutral-600 border border-neutral-200"
          }`}
        >
          Live Preview
        </button>
      </div>

      {tab === "image" ? (
        <div className="grid gap-6 md:grid-cols-3">
          <PhotoUpload />
          <GarmentGrid />
          <ResultView />
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-3">
          <div className="md:col-span-2">
            <LivePreview />
          </div>
          <GarmentGrid />
        </div>
      )}
    </div>
  );
}
