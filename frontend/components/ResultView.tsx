"use client";

import { useStore } from "@/lib/store";
import { requestTryOn, resultUrl } from "@/lib/api";

export default function ResultView() {
  const {
    photo,
    photoUrl,
    selectedGarment,
    result,
    loading,
    error,
    setResult,
    setLoading,
    setError,
  } = useStore();

  const canRun = !!photo && !!selectedGarment && !loading;

  async function run() {
    if (!photo || !selectedGarment) return;
    setLoading(true);
    setError(null);
    try {
      const r = await requestTryOn(selectedGarment.id, photo);
      setResult(r);
    } catch (e: any) {
      setError(e.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-sm font-medium text-neutral-700">3 · Result</h2>
      <button
        onClick={run}
        disabled={!canRun}
        className="mb-3 w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
      >
        {loading ? "Generating…" : "Try it on"}
      </button>

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <figure>
          <figcaption className="mb-1 text-xs text-neutral-400">Before</figcaption>
          <div className="aspect-[3/4] overflow-hidden rounded-lg border border-neutral-200 bg-white">
            {photoUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photoUrl} alt="before" className="h-full w-full object-contain" />
            )}
          </div>
        </figure>
        <figure>
          <figcaption className="mb-1 text-xs text-neutral-400">After</figcaption>
          <div className="aspect-[3/4] overflow-hidden rounded-lg border border-neutral-200 bg-white">
            {result && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={resultUrl(result.result_url)}
                alt="after"
                className="h-full w-full object-contain"
              />
            )}
          </div>
        </figure>
      </div>

      {result && (
        <a
          href={resultUrl(result.result_url)}
          download={`tryon-${result.result_id}.png`}
          className="mt-3 inline-block rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-100"
        >
          Download result
        </a>
      )}
    </div>
  );
}
