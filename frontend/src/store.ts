import { create } from "zustand";

export type Stage = "extract" | "vggt" | "unidepth" | "scale" | "ready";

export const STAGES: Stage[] = ["extract", "vggt", "unidepth", "scale", "ready"];

export type View =
  | { kind: "idle" }
  | {
      kind: "processing";
      filename: string;
      sizeBytes: number;
      stage: Stage;
      startedAt: number;
    }
  | {
      kind: "ready";
      filename: string;
      sizeBytes: number;
      glbUrl: string;
      elapsedMs: number;
      source: "video" | "glb";
    };

export type Pt = [number, number, number];

type Store = {
  view: View;
  setView: (v: View) => void;
  reset: () => void;

  // Measurement state. `picked` is in world (post-scale-group) coordinates.
  picked: Pt[];
  pick: (p: Pt) => void;
  clearPicks: () => void;

  // Reference: meters per world unit. Null until user calibrates.
  metersPerUnit: number | null;
  setReferenceMeters: (meters: number) => void;
  clearReference: () => void;
};

export const useStore = create<Store>((set, get) => ({
  view: { kind: "idle" },
  setView: (view) => set({ view, picked: [], metersPerUnit: null }),
  reset: () => set({ view: { kind: "idle" }, picked: [], metersPerUnit: null }),

  picked: [],
  pick: (p) =>
    set((s) => {
      // After two picks, the next click starts a fresh measurement.
      if (s.picked.length >= 2) return { picked: [p] };
      return { picked: [...s.picked, p] };
    }),
  clearPicks: () => set({ picked: [] }),

  metersPerUnit: null,
  setReferenceMeters: (meters) => {
    const { picked } = get();
    if (picked.length !== 2 || meters <= 0) return;
    const [a, b] = picked;
    const dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2];
    const worldDist = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (worldDist <= 1e-6) return;
    set({ metersPerUnit: meters / worldDist });
  },
  clearReference: () => set({ metersPerUnit: null }),
}));
