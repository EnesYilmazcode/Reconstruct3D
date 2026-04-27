import { STAGES, Stage, useStore } from "../store";

const STAGE_DURATIONS_MS: Record<Exclude<Stage, "ready">, number> = {
  extract: 1200,
  vggt: 3500,
  unidepth: 1800,
  scale: 800,
};

const SAMPLE_GLB_URL =
  "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Models/main/2.0/Duck/glTF-Binary/Duck.glb";

export function runMockPipeline(file: File) {
  const startedAt = performance.now();
  const { setView } = useStore.getState();

  setView({
    kind: "processing",
    filename: file.name,
    sizeBytes: file.size,
    stage: "extract",
    startedAt,
  });

  let cancelled = false;
  let acc = 0;

  for (const stage of STAGES) {
    if (stage === "ready") continue;
    acc += STAGE_DURATIONS_MS[stage];
    const at = acc;
    setTimeout(() => {
      if (cancelled) return;
      const v = useStore.getState().view;
      if (v.kind !== "processing") return;
      const next = STAGES[STAGES.indexOf(stage) + 1];
      if (next === "ready") {
        useStore.getState().setView({
          kind: "ready",
          filename: file.name,
          sizeBytes: file.size,
          glbUrl: SAMPLE_GLB_URL,
          elapsedMs: performance.now() - startedAt,
          source: "video",
        });
      } else {
        useStore.getState().setView({ ...v, stage: next });
      }
    }, at);
  }

  return () => {
    cancelled = true;
  };
}

export function loadGlbDirect(file: File) {
  const url = URL.createObjectURL(file);
  useStore.getState().setView({
    kind: "ready",
    filename: file.name,
    sizeBytes: file.size,
    glbUrl: url,
    elapsedMs: 0,
    source: "glb",
  });
}

const SAMPLE_LOCAL_URL = "/sample.glb";
const SAMPLE_LABEL = "room1 · vggt-1b · 13 frames";

export async function loadSampleGlb() {
  const head = await fetch(SAMPLE_LOCAL_URL, { method: "HEAD" }).catch(() => null);
  const size = head?.ok ? Number(head.headers.get("content-length") ?? 0) : 0;
  useStore.getState().setView({
    kind: "ready",
    filename: SAMPLE_LABEL,
    sizeBytes: size,
    glbUrl: SAMPLE_LOCAL_URL,
    elapsedMs: 0,
    source: "glb",
  });
}
