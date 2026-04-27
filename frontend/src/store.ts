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

type Store = {
  view: View;
  setView: (v: View) => void;
  reset: () => void;
};

export const useStore = create<Store>((set) => ({
  view: { kind: "idle" },
  setView: (view) => set({ view }),
  reset: () => set({ view: { kind: "idle" } }),
}));
