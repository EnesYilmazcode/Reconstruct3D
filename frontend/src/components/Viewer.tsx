import { Canvas, ThreeEvent, useFrame } from "@react-three/fiber";
import { Grid, Html, Line, OrbitControls, useGLTF } from "@react-three/drei";
import { Suspense, useMemo, useRef, useState } from "react";
import { Box3, Group, Points, PointsMaterial, Vector3 } from "three";
import { Pt, useStore } from "../store";

function fmtBytes(n: number) {
  if (n === 0) return "—";
  if (n < 1024) return `${n} b`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} kb`;
  return `${(n / 1024 / 1024).toFixed(1)} mb`;
}

function Scene({ url }: { url: string }) {
  const gltf = useGLTF(url);
  const ref = useRef<Group>(null);
  const pick = useStore((s) => s.pick);

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

  const onSceneClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const p = e.point;
    pick([p.x, p.y, p.z]);
  };

  return (
    <group
      ref={ref}
      scale={scale}
      position={[-center.x * scale, -center.y * scale, -center.z * scale]}
      onClick={onSceneClick}
    >
      <primitive object={gltf.scene} />
    </group>
  );
}

function PickMarker({ pos, label }: { pos: Pt; label: string }) {
  return (
    <group position={pos}>
      <mesh>
        <sphereGeometry args={[0.04, 16, 16]} />
        <meshBasicMaterial color="#ff5050" />
      </mesh>
      <Html
        position={[0, 0.08, 0]}
        center
        style={{ pointerEvents: "none", whiteSpace: "nowrap" }}
        className="font-mono text-[9px] uppercase tracking-[0.18em] text-white"
      >
        {label}
      </Html>
    </group>
  );
}

function MeasureLine({ a, b, label }: { a: Pt; b: Pt; label: string }) {
  const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
  return (
    <>
      <Line points={[a, b]} color="#ff8030" lineWidth={2} />
      <Html
        position={mid}
        center
        style={{ pointerEvents: "none", whiteSpace: "nowrap" }}
        className="rounded-sm bg-black/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-[#ffaa50]"
      >
        {label}
      </Html>
    </>
  );
}

function MeasureOverlay() {
  const picked = useStore((s) => s.picked);
  const metersPerUnit = useStore((s) => s.metersPerUnit);

  const fmtDistance = (worldDist: number) => {
    if (metersPerUnit == null) return `${worldDist.toFixed(3)} u`;
    const meters = worldDist * metersPerUnit;
    const inches = meters * 39.3701;
    return `${meters.toFixed(2)} m · ${inches.toFixed(1)} in`;
  };

  let lineLabel: string | null = null;
  if (picked.length === 2) {
    const [a, b] = picked;
    const d = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    lineLabel = fmtDistance(d);
  }

  return (
    <>
      {picked.map((p, i) => (
        <PickMarker key={i} pos={p} label={i === 0 ? "A" : "B"} />
      ))}
      {picked.length === 2 && lineLabel && (
        <MeasureLine a={picked[0]} b={picked[1]} label={lineLabel} />
      )}
    </>
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
        <MeasureOverlay />
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
      <MeasurePanel />
    </div>
  );
}

function MeasurePanel() {
  const picked = useStore((s) => s.picked);
  const clearPicks = useStore((s) => s.clearPicks);
  const metersPerUnit = useStore((s) => s.metersPerUnit);
  const setReferenceMeters = useStore((s) => s.setReferenceMeters);
  const clearReference = useStore((s) => s.clearReference);
  const [refInput, setRefInput] = useState("80");
  const [unit, setUnit] = useState<"in" | "cm">("in");

  const worldDist =
    picked.length === 2
      ? Math.hypot(
          picked[0][0] - picked[1][0],
          picked[0][1] - picked[1][1],
          picked[0][2] - picked[1][2]
        )
      : 0;

  const apply = () => {
    const v = parseFloat(refInput);
    if (!Number.isFinite(v) || v <= 0) return;
    const meters = unit === "in" ? v * 0.0254 : v / 100;
    setReferenceMeters(meters);
  };

  return (
    <div className="absolute bottom-6 right-6 flex w-[260px] flex-col gap-3 border border-[var(--color-line-strong)] bg-black/60 p-3 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-muted)] backdrop-blur-sm">
      <div className="flex items-center justify-between text-[var(--color-fg)]">
        <span>measure</span>
        <span className="text-[var(--color-muted)]">{picked.length}/2 pts</span>
      </div>

      {picked.length < 2 ? (
        <div className="text-[var(--color-muted)]">
          {picked.length === 0
            ? "click two points on a known feature (door height, outlet)"
            : "click second point to complete"}
        </div>
      ) : (
        <div className="text-[var(--color-fg)]">
          {metersPerUnit == null ? (
            <>{worldDist.toFixed(3)} canonical units</>
          ) : (
            <>
              {(worldDist * metersPerUnit).toFixed(2)} m
              <span className="text-[var(--color-muted)]">
                {" "}
                · {(worldDist * metersPerUnit * 39.3701).toFixed(1)} in
              </span>
            </>
          )}
        </div>
      )}

      {picked.length === 2 && metersPerUnit == null && (
        <div className="flex flex-col gap-2">
          <div className="text-[var(--color-muted)]">set as reference:</div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={refInput}
              onChange={(e) => setRefInput(e.target.value)}
              className="w-20 border border-[var(--color-line-strong)] bg-transparent px-2 py-1 font-mono text-[11px] text-[var(--color-fg)] outline-none focus:border-[var(--color-fg)]"
            />
            <button
              onClick={() => setUnit("in")}
              className={`px-1 ${unit === "in" ? "text-[var(--color-fg)]" : "text-[var(--color-muted)]"}`}
            >
              in
            </button>
            <button
              onClick={() => setUnit("cm")}
              className={`px-1 ${unit === "cm" ? "text-[var(--color-fg)]" : "text-[var(--color-muted)]"}`}
            >
              cm
            </button>
            <button
              onClick={apply}
              className="ml-auto border border-[var(--color-line-strong)] px-2 py-1 hover:border-[var(--color-fg)] hover:text-[var(--color-fg)]"
            >
              apply
            </button>
          </div>
        </div>
      )}

      <div className="flex justify-between">
        {metersPerUnit != null && (
          <button onClick={clearReference} className="hover:text-[var(--color-fg)]">
            clear ref
          </button>
        )}
        {picked.length > 0 && (
          <button onClick={clearPicks} className="ml-auto hover:text-[var(--color-fg)]">
            clear pts
          </button>
        )}
      </div>
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

    </>
  );
}
