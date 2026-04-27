import { Canvas, useFrame } from "@react-three/fiber";
import { Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { Suspense, useMemo, useRef } from "react";
import { Box3, Group, Points, PointsMaterial, Vector3 } from "three";
import { useStore } from "../store";

function fmtBytes(n: number) {
  if (n === 0) return "—";
  if (n < 1024) return `${n} b`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} kb`;
  return `${(n / 1024 / 1024).toFixed(1)} mb`;
}

function Scene({ url }: { url: string }) {
  const gltf = useGLTF(url);
  const ref = useRef<Group>(null);

  const { center, scale } = useMemo(() => {
    // GLTFLoader gives Points primitives a 1.0-size PointsMaterial by default,
    // which renders as effectively invisible after we scale the scene to fit.
    // Replace materials on any Points found in the loaded scene.
    gltf.scene.traverse((obj) => {
      if (obj instanceof Points) {
        const old = obj.material as PointsMaterial;
        const mat = new PointsMaterial({
          size: 0.012,
          sizeAttenuation: true,
          vertexColors: !!old?.vertexColors,
        });
        obj.material = mat;
      }
    });

    const box = new Box3().setFromObject(gltf.scene);
    const size = new Vector3();
    const c = new Vector3();
    box.getSize(size);
    box.getCenter(c);
    const longest = Math.max(size.x, size.y, size.z) || 1;
    return { center: c, scale: 4 / longest };
  }, [gltf]);

  return (
    <group ref={ref} scale={scale} position={[-center.x * scale, -center.y * scale, -center.z * scale]}>
      <primitive object={gltf.scene} />
    </group>
  );
}

function AutoSpin({ enabled }: { enabled: boolean }) {
  const ref = useRef<Group>(null);
  useFrame((_, dt) => {
    if (enabled && ref.current) ref.current.rotation.y += dt * 0.15;
  });
  return <group ref={ref} />;
}

export function Viewer() {
  const view = useStore((s) => s.view);
  const reset = useStore((s) => s.reset);
  if (view.kind !== "ready") return null;

  return (
    <div className="relative h-full w-full">
      <Canvas
        camera={{ position: [4, 3, 6], fov: 45, near: 0.01, far: 200 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: false }}
        style={{ background: "var(--color-bg)" }}
      >
        <color attach="background" args={["#0a0a0a"]} />
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 10, 5]} intensity={0.7} />
        <directionalLight position={[-5, -2, -5]} intensity={0.2} />

        <Grid
          args={[40, 40]}
          cellSize={0.5}
          cellThickness={0.5}
          cellColor="#1f1f1f"
          sectionSize={5}
          sectionThickness={1}
          sectionColor="#2a2a2a"
          fadeDistance={30}
          fadeStrength={1.2}
          infiniteGrid
          followCamera={false}
          position={[0, -2, 0]}
        />

        <Suspense fallback={null}>
          <Scene url={view.glbUrl} />
        </Suspense>
        <AutoSpin enabled={false} />

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          rotateSpeed={0.7}
          panSpeed={0.7}
          zoomSpeed={0.8}
          minDistance={0.5}
          maxDistance={40}
        />
      </Canvas>

      <Hud
        filename={view.filename}
        sizeBytes={view.sizeBytes}
        elapsedMs={view.elapsedMs}
        source={view.source}
        onReset={reset}
      />
    </div>
  );
}

function Hud({
  filename,
  sizeBytes,
  elapsedMs,
  source,
  onReset,
}: {
  filename: string;
  sizeBytes: number;
  elapsedMs: number;
  source: "video" | "glb";
  onReset: () => void;
}) {
  return (
    <>
      <div className="pointer-events-none absolute left-6 top-6 flex flex-col gap-1">
        <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--color-fg)]">
          reconstruct<span className="text-[var(--color-muted)]">3d</span>
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
          {source === "video" ? "reconstructed" : "loaded"}
        </div>
      </div>

      <button
        onClick={onReset}
        className="absolute right-6 top-6 border border-[var(--color-line-strong)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)] hover:border-[var(--color-fg)] hover:text-[var(--color-fg)]"
      >
        new ×
      </button>

      <div className="pointer-events-none absolute bottom-6 left-6 flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
        <div className="text-[var(--color-fg)]">{filename}</div>
        <div>
          {fmtBytes(sizeBytes)}
          {source === "video" && elapsedMs > 0 && (
            <> · {(elapsedMs / 1000).toFixed(1)}s</>
          )}
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-6 right-6 flex flex-col items-end gap-1 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
        <div>orbit · pan · zoom</div>
        <div>scale → unset</div>
      </div>
    </>
  );
}
