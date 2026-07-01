"use client";

import { useRef, useState } from "react";

/** Draggable before/after comparison slider. */
export default function BeforeAfter({
  before, after, alt = "result",
}: { before: string; after: string; alt?: string }) {
  const [pos, setPos] = useState(50); // % from left where "after" is revealed
  const boxRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  function setFromClientX(clientX: number) {
    const el = boxRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  }

  return (
    <div
      ref={boxRef}
      className="relative aspect-[3/4] w-full select-none overflow-hidden rounded-lg border border-neutral-200 bg-white"
      onMouseDown={(e) => { dragging.current = true; setFromClientX(e.clientX); }}
      onMouseMove={(e) => dragging.current && setFromClientX(e.clientX)}
      onMouseUp={() => (dragging.current = false)}
      onMouseLeave={() => (dragging.current = false)}
      onTouchStart={(e) => setFromClientX(e.touches[0].clientX)}
      onTouchMove={(e) => setFromClientX(e.touches[0].clientX)}
    >
      {/* after (full) */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={after} alt={alt} className="absolute inset-0 h-full w-full object-contain" />
      {/* before (clipped to the left of the handle) */}
      <div className="absolute inset-0 overflow-hidden" style={{ width: `${pos}%` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt="before" className="h-full w-full object-contain"
          style={{ width: boxRef.current ? boxRef.current.clientWidth : "100%", maxWidth: "none" }} />
      </div>
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
