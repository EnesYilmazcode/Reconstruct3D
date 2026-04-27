import { useEffect } from "react";
import { DropZone } from "./components/DropZone";
import { Processing } from "./components/Processing";
import { Viewer } from "./components/Viewer";
import { useStore } from "./store";
import { loadGlbDirect, runMockPipeline } from "./pipeline/mockPipeline";

export default function App() {
  const view = useStore((s) => s.view);

  useEffect(() => {
    const onDragOver = (e: DragEvent) => e.preventDefault();
    const onDrop = (e: DragEvent) => {
      if (view.kind === "ready" || view.kind === "processing") return;
      e.preventDefault();
      const file = e.dataTransfer?.files?.[0];
      if (!file) return;
      const name = file.name.toLowerCase();
      if (name.endsWith(".glb")) loadGlbDirect(file);
      else if (file.type.startsWith("video/") || /\.(mp4|mov|webm|m4v)$/i.test(name))
        runMockPipeline(file);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [view.kind]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-[var(--color-bg)]">
      {view.kind === "idle" && <DropZone />}
      {view.kind === "processing" && <Processing />}
      {view.kind === "ready" && <Viewer />}
    </div>
  );
}
