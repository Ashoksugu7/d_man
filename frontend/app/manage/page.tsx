"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Annotator, { AnnotatorHandle } from "@/components/Annotator";
import { CATEGORIES, schemeFor, sizeChartFor } from "@/lib/annotation";
import {
  assetUrl, fetchGarments, createGarment, updateGarment,
  archiveGarment, uploadGarmentImage, saveAnnotation,
  listVersions, revertVersion,
} from "@/lib/api";
import type { Garment } from "@/lib/store";

type Mode = { kind: "list" } | { kind: "edit"; garment: Garment | null };

export default function ManagePage() {
  const [garments, setGarments] = useState<Garment[]>([]);
  const [mode, setMode] = useState<Mode>({ kind: "list" });

  async function refresh() {
    try { setGarments(await fetchGarments()); } catch { setGarments([]); }
  }
  useEffect(() => { refresh(); }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Garment Manager</h1>
        <div className="flex gap-2 text-sm">
          <Link href="/" className="rounded-md border px-3 py-1.5">← Try-On</Link>
          {mode.kind === "list" && (
            <button
              onClick={() => setMode({ kind: "edit", garment: null })}
              className="rounded-md bg-blue-600 px-3 py-1.5 font-medium text-white"
            >
              + New garment
            </button>
          )}
        </div>
      </div>

      {mode.kind === "list" ? (
        <GarmentList
          garments={garments}
          onEdit={(g) => setMode({ kind: "edit", garment: g })}
          onArchive={async (id) => { await archiveGarment(id); refresh(); }}
        />
      ) : (
        <GarmentEditor
          garment={mode.garment}
          onDone={() => { setMode({ kind: "list" }); refresh(); }}
          onCancel={() => setMode({ kind: "list" })}
        />
      )}
    </div>
  );
}

function GarmentList({ garments, onEdit, onArchive }: {
  garments: Garment[];
  onEdit: (g: Garment) => void;
  onArchive: (id: string) => void;
}) {
  if (!garments.length)
    return <p className="text-sm text-neutral-400">No garments yet. Create one, or check the backend is running.</p>;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {garments.map((g) => (
        <div key={g.id} className="rounded-lg border border-neutral-200 bg-white p-2">
          <div className="aspect-square overflow-hidden rounded bg-neutral-100">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={assetUrl(g.image)} alt={g.name} className="h-full w-full object-contain" />
          </div>
          <p className="mt-1 truncate text-xs font-medium">{g.name}</p>
          <p className="text-[11px] text-neutral-400">{g.category}</p>
          <div className="mt-1 flex gap-2 text-[11px]">
            <button onClick={() => onEdit(g)} className="text-blue-600">Edit</button>
            <button onClick={() => onArchive(g.id)} className="text-red-600">Archive</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function GarmentEditor({ garment, onDone, onCancel }: {
  garment: Garment | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const editing = !!garment;
  const [id, setId] = useState(garment?.id ?? "");
  const [name, setName] = useState(garment?.name ?? "");
  const [category, setCategory] = useState(garment?.category ?? "shirt");
  const [file, setFile] = useState<File | null>(null);
  const [removeBg, setRemoveBg] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(garment ? assetUrl(garment.image) : null);
  const [initialNorm, setInitialNorm] = useState<Record<string, [number, number]> | undefined>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const annRef = useRef<AnnotatorHandle>(null);
  const scheme = schemeFor(category);

  // When editing, load existing keypoints to preload the canvas.
  useEffect(() => {
    if (!garment?.keypoints) return;
    fetch(assetUrl(garment.keypoints))
      .then((r) => r.json())
      .then((j) => setInitialNorm(j.keypoints_norm))
      .catch(() => {});
  }, [garment]);

  const [fitHem, setFitHem] = useState(garment?.fit_params?.hem_extend?.toString() ?? "");
  const [fitWiden, setFitWiden] = useState(garment?.fit_params?.shoulder_widen?.toString() ?? "");
  const [versions, setVersions] = useState<any[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const previewSrc: File | string | null = file ?? imageUrl;

  useEffect(() => {
    if (garment) listVersions(garment.id).then(setVersions).catch(() => setVersions([]));
  }, [garment]);

  async function doRevert(versionId: string) {
    if (!garment) return;
    try {
      const res = await revertVersion(garment.id, versionId);
      if (res.keypoints) {
        const j = await fetch(assetUrl(res.keypoints)).then((r) => r.json());
        setInitialNorm(j.keypoints_norm);
        setReloadKey((k) => k + 1); // remount Annotator to repaint points
      }
      setVersions(await listVersions(garment.id));
      setMsg("Reverted ✓");
    } catch (e: any) {
      setErr(e.message ?? "Revert failed");
    }
  }

  function buildFitParams(): Record<string, number> | undefined {
    const fp: Record<string, number> = {};
    if (fitHem) fp.hem_extend = Number(fitHem);
    if (fitWiden) fp.shoulder_widen = Number(fitWiden);
    return Object.keys(fp).length ? fp : undefined;
  }

  async function save() {
    setErr(null); setMsg(null);
    const gid = (id || name).trim().replace(/\s+/g, "_");
    if (!name || !gid) return setErr("Name (and id) are required.");
    if (!editing && !file) return setErr("Upload an image for a new garment.");
    const kp = annRef.current?.getKeypoints();
    if (!kp) return setErr("Place all keypoints (use Guess, then adjust).");
    setBusy(true);
    try {
      const fit_params = buildFitParams();
      if (!editing) {
        await createGarment({ id: gid, name, category, size_chart: sizeChartFor(category), fit_params });
      } else {
        await updateGarment(gid, { name, category, size_chart: sizeChartFor(category), fit_params: fit_params ?? null });
      }
      if (file) await uploadGarmentImage(gid, file, undefined, removeBg);
      await saveAnnotation(gid, kp);
      setMsg("Saved ✓");
      setTimeout(onDone, 500);
    } catch (e: any) {
      setErr(e.message ?? "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="space-y-3">
        <label className="block text-xs font-medium text-neutral-700">Garment id
          <input value={id} onChange={(e) => setId(e.target.value)} disabled={editing}
            placeholder="auto from name" className="mt-1 w-full rounded border px-2 py-1 text-sm disabled:bg-neutral-100" />
        </label>
        <label className="block text-xs font-medium text-neutral-700">Name
          <input value={name} onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded border px-2 py-1 text-sm" />
        </label>
        <label className="block text-xs font-medium text-neutral-700">Category
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            className="mt-1 w-full rounded border px-2 py-1 text-sm">
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="block text-xs font-medium text-neutral-700">Image (png/webp, transparent)
          <input type="file" accept="image/png,image/webp,image/jpeg"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setImageUrl(null); setInitialNorm(undefined); } }}
            className="mt-1 w-full text-sm" />
        </label>
        <label className="flex items-center gap-2 text-xs text-neutral-600">
          <input type="checkbox" checked={removeBg} onChange={(e) => setRemoveBg(e.target.checked)} />
          Remove background (auto-cutout on upload)
        </label>
        <details className="rounded border border-neutral-200 p-2 text-xs">
          <summary className="cursor-pointer text-neutral-600">Advanced fit (optional)</summary>
          <div className="mt-2 flex gap-3">
            <label className="flex-1">Hem length
              <input value={fitHem} onChange={(e) => setFitHem(e.target.value)}
                placeholder="e.g. 1.3" inputMode="decimal"
                className="mt-1 w-full rounded border px-2 py-1" />
            </label>
            <label className="flex-1">Shoulder widen
              <input value={fitWiden} onChange={(e) => setFitWiden(e.target.value)}
                placeholder="e.g. 1.18" inputMode="decimal"
                className="mt-1 w-full rounded border px-2 py-1" />
            </label>
          </div>
          <p className="mt-1 text-[11px] text-neutral-400">
            Overrides the default warp for this garment (hem_extend / shoulder_widen).
          </p>
        </details>
        {(category === "lehenga" || category === "saree") && (
          <p className="rounded bg-amber-50 px-2 py-1.5 text-[11px] text-amber-700">
            {category} is multi-piece — this editor annotates the primary piece; add
            blouse/pallu via the API for now.
          </p>
        )}
        <div className="flex gap-2">
          <button onClick={save} disabled={busy}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:bg-neutral-300">
            {busy ? "Saving…" : editing ? "Save changes" : "Create garment"}
          </button>
          <button onClick={onCancel} className="rounded-md border px-4 py-2 text-sm">Cancel</button>
        </div>
        {msg && <p className="text-sm text-emerald-600">{msg}</p>}
        {err && <p className="rounded bg-red-50 px-2 py-1.5 text-sm text-red-700">{err}</p>}

        {editing && versions.length > 0 && (
          <details className="rounded border border-neutral-200 p-2 text-xs">
            <summary className="cursor-pointer text-neutral-600">
              Annotation history ({versions.length})
            </summary>
            <ul className="mt-2 space-y-1">
              {versions.map((v) => (
                <li key={v.id} className="flex items-center justify-between">
                  <span className="text-neutral-500">
                    {new Date(v.created_at).toLocaleString()} {v.role ? `· ${v.role}` : ""}
                  </span>
                  <button onClick={() => doRevert(v.id)} className="text-blue-600">Revert</button>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      <div>
        <Annotator key={reloadKey} ref={annRef} scheme={scheme} imageSrc={previewSrc} initialNorm={initialNorm} />
      </div>
    </div>
  );
}
