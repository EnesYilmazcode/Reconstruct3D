# Reconstruct3D

Turn a phone-shot apartment walkthrough video into a **metrically scaled** 3D point cloud, then drop in furniture GLBs to plan layout. Built to answer one question fast — *"will a roommate fit in this NYC apartment?"* — and to ship as a portfolio piece in spatial AI.

## Why this project exists

The video is already taken. Re-shooting (RoomPlan, Polycam) is not an option. Out-of-the-box video-to-3D models (VGGT, MASt3R) are **scale-ambiguous** — geometry is correct in shape but unknown in absolute size. The work this repo does that those models don't: **resolve metric scale** and turn the result into a useful measurement + furniture-planning tool.

## Two tracks

| Track | Goal | Time budget | Output |
|-------|------|------------|--------|
| **A. Urgent** | Decide on the roommate | This week | A floor-plan PDF with rough room dimensions ±10% |
| **B. Portfolio** | Public demo + recruiter narrative | 3–4 weeks | Hosted webapp: upload video → metric 3D + GLB drop-in |

Track A is hand-tooled (manual reference-object scaling on a Jupyter notebook). Track B wraps the same math behind a Modal endpoint + React/Three.js frontend.

## Stack at a glance

- **Geometry**: VGGT-1B (Meta, feed-forward video → point cloud + camera poses)
- **Metric scale**: UniDepth v2 (primary) + door/ceiling reference (sanity check)
- **Compute**: Modal A10G ($1.10/hr, scales to zero) — Replicate `vufinder/vggt-1b-depth` as fallback for first end-to-end demo
- **Viz**: Three.js (custom UI) + Rerun (debug)
- **Furniture**: IKEA GLB catalog → loaded via `three/examples/jsm/loaders/GLTFLoader`

## Documentation

Read in order:

1. [`docs/01-overview.md`](docs/01-overview.md) — problem, goals, accuracy targets
2. [`docs/02-architecture.md`](docs/02-architecture.md) — system diagram, data contracts
3. [`docs/03-pipeline.md`](docs/03-pipeline.md) — VGGT inference + frame extraction
4. [`docs/04-metric-scaling.md`](docs/04-metric-scaling.md) — the three scaling strategies (the hard part)
5. [`docs/05-frontend.md`](docs/05-frontend.md) — Three.js viewer, measurement tool, GLB drop-in
6. [`docs/06-deployment.md`](docs/06-deployment.md) — Modal app, Replicate fallback, cost model
7. [`docs/07-roadmap.md`](docs/07-roadmap.md) — Track A (this week) + Track B (3–4 weeks) milestones
8. [`docs/08-risks.md`](docs/08-risks.md) — failure modes and mitigations

## Quickstart for Track A (urgent dimension answer)

```bash
# 1. Drop the apartment video at data/raw/apartment.mp4
# 2. Extract frames
python scripts/extract_frames.py data/raw/apartment.mp4 --fps 2 --max 60

# 3. Run hosted VGGT (Replicate) — get .glb + camera poses
python scripts/run_replicate_vggt.py data/frames/ --out data/recon/

# 4. Open notebooks/scale_from_door.ipynb, click two points on a door
#    in the .glb, enter 80 inches, get scale factor
# 5. Apply scale, measure room walls in Blender or Rerun
```

Expected wall-clock: ~2 hours from running the video to a numbered floor plan.

## What this is *not*

- Not a SLAM system. No real-time, no incremental updates.
- Not legally precise. ±5–10% in the best case. Don't argue with a landlord using these numbers.
- Not a replacement for RoomPlan if you can re-shoot in person — that's a 5-minute solved problem with an iPhone.
