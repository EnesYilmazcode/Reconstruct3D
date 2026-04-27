import { useCallback, useEffect, useRef, useState } from "react";
import { loadGlbDirect, loadSampleGlb, runMockPipeline } from "../pipeline/mockPipeline";

const VIDEO_EXT = [".mp4", ".mov", ".webm", ".m4v"];
const GLB_EXT = [".glb"];

function classify(file: File): "video" | "glb" | null {
  const name = file.name.toLowerCase();
  if (VIDEO_EXT.some((e) => name.endsWith(e))) return "video";
  if (GLB_EXT.some((e) => name.endsWith(e))) return "glb";
  if (file.type.startsWith("video/")) return "video";
  return null;
}

export function DropZone() {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleAvailable, setSampleAvailable] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/sample.glb", { method: "HEAD" })
      .then((r) => setSampleAvailable(r.ok))
      .catch(() => setSampleAvailable(false));
  }, []);

  const accept = useCallback((file: File) => {
    const kind = classify(file);
    if (kind === "video") {
      setError(null);
      runMockPipeline(file);
    } else if (kind === "glb") {
      setError(null);
      loadGlbDirect(file);
    } else {
      setError(`unsupported · ${file.name}`);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) accept(file);
    },
    [accept]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className="relative h-full w-full"
    >
      <Wordmark />

      <div className="flex h-full w-full items-center justify-center px-6">
        <div className="flex flex-col items-center gap-10">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className={[
              "group relative flex h-[320px] w-[320px] cursor-pointer flex-col items-center justify-center",
              "border border-dashed transition-colors",
              over
                ? "border-[var(--color-fg)] bg-[var(--color-surface)]"
                : "border-[var(--color-line-strong)] hover:border-[var(--color-fg)]",
            ].join(" ")}
          >
            <Crosshair />
            <div className="mt-6 font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-muted)] group-hover:text-[var(--color-fg)]">
              drop video or .glb
            </div>
          </button>

          <div className="flex flex-col items-center gap-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
              mp4 · mov · webm · glb
            </div>
            {sampleAvailable && (
              <button
                type="button"
                onClick={() => loadSampleGlb()}
                className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)] underline-offset-4 hover:text-[var(--color-fg)] hover:underline"
              >
                view pre-generated sample →
              </button>
            )}
            {error && (
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-fg)]">
                {error}
              </div>
            )}
          </div>
        </div>
      </div>

      <FootnoteIdle />

      <input
        ref={inputRef}
        type="file"
        accept=".mp4,.mov,.webm,.m4v,.glb,video/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) accept(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function Crosshair() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      className="text-[var(--color-muted)] group-hover:text-[var(--color-fg)]"
    >
      <line x1="14" y1="2" x2="14" y2="10" />
      <line x1="14" y1="18" x2="14" y2="26" />
      <line x1="2" y1="14" x2="10" y2="14" />
      <line x1="18" y1="14" x2="26" y2="14" />
      <circle cx="14" cy="14" r="3" />
    </svg>
  );
}

function Wordmark() {
  return (
    <div className="absolute left-6 top-6 font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--color-fg)]">
      reconstruct<span className="text-[var(--color-muted)]">3d</span>
    </div>
  );
}

function FootnoteIdle() {
  return (
    <div className="absolute bottom-6 left-6 right-6 flex items-end justify-between font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
      <div>video → metric 3d · vggt + unidepth v2</div>
      <div>local · no upload</div>
    </div>
  );
}
