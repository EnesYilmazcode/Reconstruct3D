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
- **Compute**: Modal A10G ($1.10/hr, scales to zero) — Replicate `vufinder/vggt-1b` as fallback for first end-to-end demo (full model, runs on L40S, accepts video files directly)
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

Prerequisites:
- Python 3.11+ with `pip install replicate numpy trimesh`
- A Replicate API token — see [Setting up the Replicate token](#setting-up-the-replicate-token) below
- Node 20+ (for the viewer)

```bash
# 1. Drop the apartment video at data/raw/apartment.mp4 (long videos: trim first)
ffmpeg -i source.mp4 -ss 0:42 -to 0:51 -c:v copy -an data/raw/room1.mp4

# 2. Run hosted VGGT (Replicate). Returns one JSON per sampled frame
#    with depth + world_points + pose + normals + image.
export REPLICATE_API_TOKEN=r8_...
python scripts/run_replicate_vggt.py data/raw/room1.mp4 --out data/recon/room1

# 3. Assemble a colored point-cloud GLB from the per-frame predictions
python scripts/assemble_glb.py data/recon/room1 --out frontend/public/sample.glb

# 4. View it
cd frontend && npm install && npm run dev
# open the printed localhost URL → click "view pre-generated sample"

# 5. (Track A finish) measure walls in the GLB, apply a manual reference-object
#    scale to convert canonical units → meters. See docs/04-metric-scaling.md.
```

Expected wall-clock: ~2 hours from running the video to a numbered floor plan. The Replicate call itself is ~5–10 s once the model is warm.

### Setting up the Replicate token

1. Sign up at https://replicate.com (GitHub login works).
2. **Set a hard spend limit first** — Billing → Spend limit → $5 is plenty for Track A. Do this *before* the next step so a runaway job can't drain your card.
3. Create a token at https://replicate.com/account/api-tokens, name it something memorable.
4. Export it in your shell (or write it to a `.env` at the repo root — already gitignored):
   ```bash
   # bash / zsh
   export REPLICATE_API_TOKEN=r8_...
   # PowerShell
   $env:REPLICATE_API_TOKEN = "r8_..."
   ```
5. Sanity-check: `echo $REPLICATE_API_TOKEN` (or `$env:REPLICATE_API_TOKEN` on PowerShell).

Cost: ~$0.05–$0.20 per video on `vufinder/vggt-1b` (L40S). The model is "Cold" — first call after idle has a 30–60 s warmup; subsequent calls in the same session are fast.

> Local secret notes (gitignored, not for portfolio readers) live in `KEYS.local.md` if you need a more detailed walkthrough.

## What this is *not*

- Not a SLAM system. No real-time, no incremental updates.
- Not legally precise. ±5–10% in the best case. Don't argue with a landlord using these numbers.
- Not a replacement for RoomPlan if you can re-shoot in person — that's a 5-minute solved problem with an iPhone.
