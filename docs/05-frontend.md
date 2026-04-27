# 05 — Frontend

## Stack

- **Framework**: Vite + React 18 + TypeScript.
- **3D**: `@react-three/fiber` (declarative Three.js) + `@react-three/drei` (OrbitControls, GLB loader, TransformControls, Html overlay).
- **State**: Zustand (lightweight; the app has very little global state — current scene, current measurement, list of placed furniture).
- **Styling**: Tailwind. The UI is utilitarian, not designed.
- **Hosting**: Vercel. Static build, no SSR — the API gateway lives separately on Modal.

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Reconstruct3D                                  [Upload video]│
├────────────┬─────────────────────────────────────────────────┤
│            │                                                  │
│  Sidebar   │            3D Viewer (full bleed)               │
│            │                                                  │
│  Scene     │                                                  │
│  ▸ Walls   │                                                  │
│  ▸ Cameras │              ◯  point cloud                      │
│  ▸ Floor   │             ╱                                    │
│            │           ▲ camera frustum                       │
│  Tools     │                                                  │
│  ▸ Measure │                                                  │
│  ▸ Scale   │                                                  │
│  ▸ Furniture│                                                 │
│            │                                                  │
│  Furniture │                                                  │
│  ▸ Bed Q   │                                                  │
│  ▸ Desk    │                                                  │
│  ▸ Sofa    │                                                  │
│            │  Status: scale=1.247 m/unit (UniDepth, ±8%)     │
└────────────┴─────────────────────────────────────────────────┘
```

## Core interactions

### 1. Video upload

- Drop zone in the top-right corner. Accepts `.mp4`, `.mov`, `.webm`. Max ~200 MB.
- POST `/jobs` with multipart, get back `{ job_id }`.
- Polls `GET /jobs/{job_id}` every 2 s. Shows progress: `extracting → vggt → unidepth → scaling → ready`.
- On `ready`, fetches `scene.glb` + `cameras.json` + `run.json` and renders.

### 2. 3D viewer

```tsx
<Canvas camera={{ position: [3, 3, 3], fov: 50 }}>
  <ambientLight intensity={0.6} />
  <OrbitControls />
  <PointCloud url={glbUrl} scale={scaleMetersPerUnit} />
  <CameraTrajectory frames={cameras} scale={scaleMetersPerUnit} />
  {placedFurniture.map(f => <FurnitureItem key={f.id} {...f} />)}
  <MeasurementOverlay />
</Canvas>
```

Camera frustums are wireframe pyramids — same trick as Open Reality. Animate a small sphere along the trajectory if the user clicks "play."

### 3. Measurement tool

- Click-click: pick two points in 3D space using a raycast against the point cloud.
- Display the distance in the chosen unit (ft/in default for US users — auto-detect via `navigator.language`).
- Persist in a list on the sidebar; each can be hidden/deleted.
- The two clicked points are stored in canonical (unscaled) units, so changing the scale factor instantly updates all measurements.

```tsx
function distanceLabel(p1: Vector3, p2: Vector3, scale: number) {
  const meters = p1.distanceTo(p2) * scale;
  return formatFeetInches(meters);
}
```

### 4. Scale override panel

- Default scale shown (from `cameras.json.scale_meters_per_unit`).
- "Override using reference" button → user picks an object type from the dropdown (door height, outlet width, ceiling height, etc.), clicks two points, the scale recomputes globally. See [`04-metric-scaling.md`](04-metric-scaling.md) Strategy 2.
- "I asked the landlord and ceiling = X" plain numeric input. Highest priority — overrides everything else.
- Three computed scale candidates from `run.json` shown read-only as a sanity check.

### 5. Furniture drag-and-drop

- Sidebar lists IKEA GLBs grouped by category (Beds, Desks, Sofas, Storage). Pre-loaded thumbnails.
- Drag a thumbnail into the scene → spawns the model at the cursor's raycast hit on the floor plane.
- `<TransformControls>` from drei allows move/rotate. Snap rotation to 15°.
- Collision check: AABB-vs-AABB against placed furniture and against the wall geometry. Show red outline on collision; allow placement anyway (user is the source of truth for what counts as "fits").
- Persist placed-furniture list in localStorage, keyed by `job_id`. Refreshing the page restores the layout.

### 6. Top-down floor plan view

- Toggle in the toolbar. Camera moves to `(0, ceiling_height + 2, 0)` looking straight down, orthographic.
- Renders only the bottom 30 cm of the point cloud (the floor) plus furniture footprints as filled polygons.
- "Export PNG" button — uses `gl.domElement.toDataURL()`. This is the main Track A deliverable.

## IKEA GLB sourcing

IKEA does not officially publish a GLB API, but most catalog items have a "View in 3D" / AR button that loads a `.usdz` (iOS) or `.glb` (Android). Pull the GLB URLs by inspecting network traffic on a small set of items (queen bed, desk, sofa, dresser, nightstand, bookshelf, chair) and bundle into `public/furniture/`. ~20 items is plenty.

If IKEA's terms get awkward, fallback to Sketchfab's free downloadable furniture (check licenses individually) or Polyhaven for generic items.

## Rerun fallback (debug only)

For Track A, before the React frontend is even built, dump the reconstruction to a Rerun viewer. ~10 lines of Python:

```python
import rerun as rr
rr.init("reconstruct3d", spawn=True)
rr.log("world/points", rr.Points3D(pcd.points, colors=pcd.colors))
for i, frame in enumerate(cameras):
    rr.log(f"world/cam_{i}", rr.Pinhole(...))
    rr.log(f"world/cam_{i}/image", rr.Image(frame_image))
```

Rerun has built-in measurement, point picking, and a slider for scrubbing through camera poses. For "I just need to see if this works," it's faster than building any UI.
