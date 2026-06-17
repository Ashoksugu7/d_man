"use client";

import { useCallback, useRef, useState } from "react";
import { useStore } from "@/lib/store";

export default function PhotoUpload() {
  const { photoUrl, setPhoto } = useStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file && file.type.startsWith("image/")) setPhoto(file);
    },
    [setPhoto]
  );

  return (
    <div>
      <h2 className="mb-2 text-sm font-medium text-neutral-700">1 · Your photo</h2>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex aspect-[3/4] cursor-pointer items-center justify-center overflow-hidden rounded-xl border-2 border-dashed transition ${
          dragging
            ? "border-blue-500 bg-blue-50"
            : "border-neutral-300 bg-white hover:border-neutral-400"
        }`}
      >
        {photoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photoUrl} alt="upload" className="h-full w-full object-contain" />
        ) : (
          <div className="px-4 text-center text-sm text-neutral-500">
            Drag &amp; drop a full-body, front-facing photo
            <br />
            <span className="text-neutral-400">or click to browse</span>
          </div>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/*"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  );
}
