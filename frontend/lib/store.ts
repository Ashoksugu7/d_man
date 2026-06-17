import { create } from "zustand";

export type Garment = {
  id: string;
  name: string;
  category: string;
  image: string;
  keypoints: string;
  size_chart: Record<string, { shoulder_cm: number; length_cm: number }>;
};

export type TryOnResult = {
  result_id: string;
  result_url: string;
  garment_id: string;
};

type State = {
  garments: Garment[];
  selectedGarment: Garment | null;
  photo: File | null;
  photoUrl: string | null;
  result: TryOnResult | null;
  loading: boolean;
  error: string | null;
  setGarments: (g: Garment[]) => void;
  selectGarment: (g: Garment) => void;
  setPhoto: (f: File | null) => void;
  setResult: (r: TryOnResult | null) => void;
  setLoading: (b: boolean) => void;
  setError: (e: string | null) => void;
};

export const useStore = create<State>((set, get) => ({
  garments: [],
  selectedGarment: null,
  photo: null,
  photoUrl: null,
  result: null,
  loading: false,
  error: null,
  setGarments: (g) => set({ garments: g }),
  selectGarment: (g) => set({ selectedGarment: g, result: null }),
  setPhoto: (f) => {
    const prev = get().photoUrl;
    if (prev) URL.revokeObjectURL(prev);
    set({ photo: f, photoUrl: f ? URL.createObjectURL(f) : null, result: null });
  },
  setResult: (r) => set({ result: r }),
  setLoading: (b) => set({ loading: b }),
  setError: (e) => set({ error: e }),
}));
