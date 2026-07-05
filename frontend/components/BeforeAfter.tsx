"use client";

import { useRef, useState } from "react";

/** Draggable before/after comparison slider.
 *
 * Both images are rendered identically (absolute, object-contain) and the
 * "before" layer is revealed with clip-path — so they are always perfectly
 * aligned and scaled, regardless of container size or render timing. The
 * container adopts the result image's own aspect ratio, so there is no
 * letterboxing around photos that aren't 3:4.
 */
export default function BeforeAfter({
  before, after, alt = "result",
}: { before: string; after: string; alt?: string }) {
  const [pos, setPos] = useState(50); // % from left where "before" ends
  const [aspect, setAspect] = useState<number | null>(null); // w/h of result
  const boxRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  function setFromClientX(clientX: number) {
    const el = boxRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  }

  const img = "pointer-events-none absolute inset-0 h-full w-full object-contain";
  return (
    <div
      ref={boxRef}
      className="relative w-full select-none overflow-hidden rounded-lg border border-neutral-200 bg-white"
      style={{ aspectRatio: aspect ?? 3 / 4 }}
      onMouseDown={(e) => { dragging.current = true; setFromClientX(e.clientX); }}
      onMouseMove={(e) => dragging.current && setFromClientX(e.clientX)}
      onMouseUp={() => (dragging.current = false)}
      onMouseLeave={() => (dragging.current = false)}
      onTouchStart={(e) => setFromClientX(e.touches[0].clientX)}
      onTouchMove={(e) => setFromClientX(e.touches[0].clientX)}
    >
      {/* after (full) — its natural size also sets the container aspect */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={after}
        alt={alt}
        className={img}
        onLoad={(e) => {
          const el = e.currentTarget;
          if (el.naturalWidth && el.naturalHeight)
            setAspect(el.naturalWidth / el.naturalHeight);
        }}
      />
      {/* before — same geometry, revealed left of the handle via clip-path */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={before}
        alt="before"
        className={img}
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
      />
      {/* labels */}
      <span className="absolute left-1 top-1 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white">Before</span>
      <span className="absolute right-1 top-1 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white">After</span>
      {/* handle */}
      <div className="absolute inset-y-0 w-0.5 bg-white shadow" style={{ left: `${pos}%` }}>
        <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white p-1 shadow ring-1 ring-neutral-300">
          <div className="h-3 w-3 text-[8px] leading-3 text-neutral-500">⟺</div>
        </div>
      </div>
    </div>
  );
}
