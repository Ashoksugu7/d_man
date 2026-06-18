import { create } from "zustand";

export type SizeDims = {
  shoulder_cm?: number;
  length_cm?: number;
  waist_cm?: number;
  inseam_cm?: number;
};

export type Garment = {
  id: string;
  name: string;
  category: string;
  image: string;
  keypoints: string;
  size_chart: Record<string, SizeDims>;
};

export type TryOnResult = {
  result_id: string;
  result_url: string;
  garment_id: string;
  pose_method?: string;
};

export type FitLabel = "fits_well" | "too_tight" | "too_loose";

export type Recommendation = {
  recommended_size: string;
  fit: FitLabel;
  dimension: string;
  body_cm: number;
  per_size_deltas: Record<string, number>;
};

export type Measurements = {
  cm_per_px: number;
  shoulder_width_cm: number;
  torso_length_cm: number;
  hip_width_cm: number;
  inseam_cm: number;
  waist_circumference_cm: number;
};

export type MeasureResult = {
  ok: boolean;
  measurements: Measurements | null;
  recommendations: Record<string, Recommendation>;
  pose_method?: string;
  message?: string;
  note?: string;
};

type State = {
  garments: Garment[];
  selectedGarment: Garment | null;
  photo: File | null;
  photoUrl: string | null;
  result: TryOnResult | null;
  loading: boolean;
  error: string | null;
  heightCm: number | null;
  measure: MeasureResult | null;
  measuring: boolean;
  measureError: string | null;
  setGarments: (g: Garment[]) => void;
  selectGarment: (g: Garment) => void;
  setPhoto: (f: File | null) => void;
  setResult: (r: TryOnResult | null) => void;
  setLoading: (b: boolean) => void;
  setError: (e: string | null) => void;
  setHeightCm: (h: number | null) => void;
  setMeasure: (m: MeasureResult | null) => void;
  setMeasuring: (b: boolean) => void;
  setMeasureError: (e: string | null) => void;
};

export const useStore = create<State>((set, get) => ({
  garments: [],
  selectedGarment: null,
  photo: null,
  photoUrl: null,
  result: null,
  loading: false,
  error: null,
  heightCm: null,
  measure: null,
  measuring: false,
  measureError: null,
  setGarments: (g) => set({ garments: g }),
  selectGarment: (g) => set({ selectedGarment: g, result: null }),
  setPhoto: (f) => {
    const prev = get().photoUrl;
    if (prev) URL.revokeObjectURL(prev);
    // A new photo invalidates any prior measurements.
    set({
      photo: f,
      photoUrl: f ? URL.createObjectURL(f) : null,
      result: null,
      measure: null,
      measureError: null,
    });
  },
  setResult: (r) => set({ result: r }),
  setLoading: (b) => set({ loading: b }),
  setError: (e) => set({ error: e }),
  setHeightCm: (h) => set({ heightCm: h }),
  setMeasure: (m) => set({ measure: m }),
  setMeasuring: (b) => set({ measuring: b }),
  setMeasureError: (e) => set({ measureError: e }),
}));
