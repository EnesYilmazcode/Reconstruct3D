# 02 — Architecture

## System diagram

```
                        ┌──────────────────────────────────────────┐
  apartment.mp4  ───►   │  FRONTEND (React + Three.js, Vercel)     │
  (uploaded)            │  - drop-zone for video                   │
                        │  - 3D viewer (point cloud + frustums)    │
                        │  - measurement tool                      │
                        │  - GLB drag-and-drop                     │
                        └──────────────┬───────────────────────────┘
                                       │ multipart upload
                                       ▼
                        ┌──────────────────────────────────────────┐
                        │  API GATEWAY (FastAPI on Modal)          │
                        │  - signed URL upload to S3/R2            │
                        │  - kicks off async reconstruction job    │
                        │  - returns job_id; polls status          │
                        └──────────────┬───────────────────────────┘
                                       │ enqueue
                                       ▼
                        ┌──────────────────────────────────────────┐
                        │  RECONSTRUCT WORKER (Modal, A10G GPU)    │
                        │  ┌────────────────────────────────────┐  │
                        │  │ 1. ffmpeg → frames (configurable)  │  │
                        │  │ 2. VGGT → point cloud + cameras    │  │
                        │  │ 3. UniDepth v2 → metric depth      │  │
                        │  │ 4. solve scale factor              │  │
                        │  │ 5. apply scale, write outputs      │  │
                        │  └────────────────────────────────────┘  │
                        │  output: scene.glb, cameras.json,        │
                        │          metric_pointcloud.ply, run.json │
                        └──────────────┬───────────────────────────┘
                                       │ writes to
                                       ▼
                        ┌──────────────────────────────────────────┐
                        │  OBJECT STORE (Cloudflare R2 or S3)      │
                        │  jobs/{job_id}/scene.glb                 │
                        │  jobs/{job_id}/cameras.json              │
                        │  jobs/{job_id}/run.json (timing, scale)  │
                        └──────────────────────────────────────────┘
```

## Component boundaries

### Frontend (Vercel)

- **Owns**: rendering, interaction, GLB library, measurement UX, persistence of layouts in localStorage.
- **Knows nothing about**: VGGT, UniDepth, GPU, Modal. Talks to a thin REST API only.
- **Stack**: Vite + React + TypeScript + `@react-three/fiber` + `@react-three/drei`.

### API gateway (FastAPI on Modal, CPU-only `@app.function`)

- **Owns**: HTTP surface, auth (eventually), job lifecycle (`POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/result`), signed URL minting.
- **Knows nothing about**: ML model internals.
- **Why split from worker**: the gateway needs to be always-warm and cheap (~$0/mo idle); the worker only spins up GPU when a job lands.

### Reconstruct worker (Modal, GPU-bound `@app.function(gpu="A10G")`)

- **Owns**: ffmpeg, VGGT, UniDepth, scale solver, output serialization.
- **Cold start**: ~30–60 s (model weights from `huggingface_hub` cached in a Modal Volume).
- **Warm runtime**: ~30–90 s for a 30 s input video at 2 fps sampling.
- **Concurrency**: 1 video per worker instance — VGGT can saturate an A10G's 24 GB by itself on long clips. Modal autoscaling spins up additional instances as needed.

### Object store

- Cloudflare R2 chosen over S3 to avoid egress fees on GLB downloads (the frontend pulls them).
- Bucket layout: `jobs/{uuid}/{scene.glb,cameras.json,metric_pointcloud.ply,run.json,thumb.jpg}`.

## Data contracts between stages

### `cameras.json` (worker → frontend)

```json
{
  "intrinsics": { "fx": 580.1, "fy": 580.1, "cx": 320.0, "cy": 240.0 },
  "frames": [
    {
      "index": 0,
      "timestamp_s": 0.000,
      "extrinsic_world_to_cam": [[...4x4 row-major...]],
      "thumb_url": "https://r2.../thumb_0.jpg"
    },
    ...
  ],
  "scale_meters_per_unit": 1.247
}
```

`scale_meters_per_unit` is the single number that lets the frontend label dimensions in real-world units. Before scaling is applied this is `null`; after, every coordinate in `scene.glb` is multiplied by this factor when the viewer displays measurements.

### `run.json` (worker → frontend, debug-grade)

```json
{
  "video": { "duration_s": 28.4, "fps": 30.0, "resolution": [1920, 1080] },
  "frames_used": 56,
  "vggt_seconds": 41.2,
  "unidepth_seconds": 8.9,
  "scale_method": "unidepth_median",
  "scale_factor": 1.247,
  "scale_factor_alternative_door_ref": 1.193,
  "scale_factor_alternative_unidepth_keyframe_5": 1.281,
  "warnings": ["frame 23 had low texture; pose estimate may be noisy"]
}
```

The alternative scale factors are **not** averaged. Surfacing them in the UI lets the user spot disagreement (which signals a bad reconstruction) and pick a method.

### `scene.glb` (worker → frontend)

- Vertices in **whatever units VGGT returned** (canonical, scale-ambiguous). The viewer applies `scale_meters_per_unit` at render time, so the same .glb is reusable if a better scale estimate is computed later.
- Vertex colors from VGGT's color head (or by sampling the source frames at the projected pixel — TBD; see [`03-pipeline.md`](03-pipeline.md)).

## Key trade-offs

- **Modal vs. RunPod**: chose Modal because user has prior experience and it composes a CPU gateway + GPU worker more cleanly than RunPod serverless. Cost difference is in the noise.
- **R2 vs. S3**: chose R2 for free egress on the GLB downloads.
- **One .glb vs. separate point cloud + mesh**: shipping just `.glb` keeps the frontend loader code minimal. Power users who want to do their own measurements can download the `.ply` from `/jobs/{id}/metric_pointcloud.ply`.
- **Sync vs. async API**: async with polling. A 30 s video takes ~60–90 s to process; HTTP request timeouts make sync infeasible.
