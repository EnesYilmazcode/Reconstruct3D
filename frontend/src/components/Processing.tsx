import { useEffect, useState } from "react";
import { STAGES, Stage, useStore } from "../store";

const STAGE_LABEL: Record<Stage, string> = {
  extract: "extract frames",
  vggt: "vggt",
  unidepth: "unidepth v2",
  scale: "solve scale",
  ready: "ready",
};

function fmtBytes(n: number) {
  if (n < 1024) return `${n} b`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} kb`;
  return `${(n / 1024 / 1024).toFixed(1)} mb`;
}

export function Processing() {
  const view = useStore((s) => s.view);
  const reset = useStore((s) => s.reset);
  const [now, setNow] = useState(performance.now());

  useEffect(() => {
    const id = setInterval(() => setNow(performance.now()), 100);
    return () => clearInterval(id);
  }, []);

  if (view.kind !== "processing") return null;

  const elapsed = ((now - view.startedAt) / 1000).toFixed(1);
  const currentIndex = STAGES.indexOf(view.stage);
  const totalStages = STAGES.length - 1;
  const progress = currentIndex / totalStages;

  return (
    <div className="relative h-full w-full">
      <div className="absolute left-6 top-6 font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--color-fg)]">
        reconstruct<span className="text-[var(--color-muted)]">3d</span>
      </div>

      <button
        onClick={reset}
        className="absolute right-6 top-6 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)] hover:text-[var(--color-fg)]"
      >
        cancel ×
      </button>

      <div className="flex h-full w-full items-center justify-center px-6">
        <div className="flex w-full max-w-[640px] flex-col gap-12">
          <div className="flex flex-col gap-2 text-center">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
              processing
            </div>
            <div className="truncate font-mono text-[13px] tracking-tight text-[var(--color-fg)]">
              {view.filename}
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
              {fmtBytes(view.sizeBytes)} · {elapsed}s
            </div>
          </div>

          <div className="flex w-full flex-wrap items-center justify-center gap-x-3 gap-y-2 font-mono text-[11px] uppercase tracking-[0.18em]">
            {STAGES.filter((s) => s !== "ready").map((stage, i) => {
              const isDone = i < currentIndex;
              const isCurrent = i === currentIndex;
              return (
                <div key={stage} className="flex items-center gap-3">
                  <span
                    className={
                      isDone
                        ? "text-[var(--color-muted)] line-through decoration-[var(--color-line-strong)]"
                        : isCurrent
                          ? "text-[var(--color-fg)]"
                          : "text-[var(--color-line-strong)]"
                    }
                  >
                    {STAGE_LABEL[stage]}
                    {isCurrent && <Cursor />}
                  </span>
                  {i < STAGES.length - 2 && (
                    <span className="text-[var(--color-line-strong)]">→</span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="relative h-px w-full bg-[var(--color-line)]">
            <div
              className="absolute inset-y-0 left-0 bg-[var(--color-fg)] transition-all duration-300"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function Cursor() {
  return (
    <span className="ml-1 inline-block h-[1em] w-[6px] translate-y-[2px] animate-pulse bg-[var(--color-fg)]" />
  );
}
