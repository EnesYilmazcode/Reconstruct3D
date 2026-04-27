# 07 — Roadmap

Two parallel tracks. Track A is the personal-utility deadline; Track B is the portfolio polish. Track A's outputs are reusable in Track B (the manual scaling notebook becomes the test fixture for the automatic pipeline).

## Track A — get the apartment dimensions answered (this week)

### Day 1 (≤1 hour)

- [ ] Drop video into `data/raw/apartment.mp4`. Eyeball it: identify candidate reference objects (door, light switch, outlet, window). Note timestamps where each appears clearly.
- [ ] `pip install replicate open3d trimesh rerun-sdk numpy pillow`. (No ffmpeg-python needed for Track A — the Replicate model accepts video directly.)
- [ ] If the video is longer than the Replicate model's max input duration, trim it once with a one-off `ffmpeg -ss 0 -t 30 -c copy ...`. Otherwise skip.
- [ ] `REPLICATE_API_TOKEN` exported in shell (see `KEYS.local.md`). Set a $5 spend limit on the Replicate billing page first.

### Day 2 (≤3 hours)

- [ ] `scripts/run_replicate_vggt.py` — call `vufinder/vggt-1b` on `data/raw/apartment.mp4` directly. Pin the version digest. Persist every URL in `output["data"]` to `data/recon/` and label which is the GLB vs. depth vs. camera params on first run.
- [ ] Open the GLB in a viewer (Blender, or `python -c "import rerun ..."`) and confirm the geometry looks like the apartment.
- [ ] If geometry is garbage: try a shorter clip (trim to a single room) or a slower-pan section. Re-run.

### Day 3 (≤2 hours)

- [ ] `notebooks/scale_from_door.ipynb` — load the GLB, pick two points along a door's height in the visualization, enter the real height (80 in), compute scale factor. Apply.
- [ ] Repeat with a second reference (light switch height = 48 in from floor) as a cross-check. If the two scale factors agree within ~5%, trust the result. If not, eyeball which is correct based on which reference clicked-points were less ambiguous.

### Day 4 (≤2 hours)

- [ ] Measure the relevant walls in the scaled point cloud. Sketch a floor plan in any drawing tool with annotated dimensions.
- [ ] Mark the largest unobstructed floor regions. Lay out a queen bed (60 × 80 in) + desk (48 × 24 in) for each occupant. See if it fits.
- [ ] Make the roommate go/no-go decision. Email the landlord with one or two specific dimension questions to confirm the most ambiguous numbers.

**Done = Track A success criteria from [`01-overview.md`](01-overview.md).**

## Track B — portfolio piece (next 3–4 weeks, ~30–40 hrs total)

### Week 1 — pipeline solidification

- [ ] Move from Replicate to a self-hosted Modal worker. Implement [`03-pipeline.md`](03-pipeline.md) Stages 0–2 + 5 (no UniDepth yet).
- [ ] Add UniDepth v2 (Stage 3). Implement scale solver (Stage 4).
- [ ] Smoke test on Track A's apartment video. Compare auto-computed scale to the door-reference scale from Track A. If they're within 10%, confidence is high enough to call this done.
- [ ] Add chunking (Stage 2.5) for videos longer than ~30 s.
- [ ] Write `tests/` with golden-file fixtures (frozen `.npz` of expected VGGT outputs from a sample).

### Week 2 — frontend MVP

- [ ] Vite + React + R3F skeleton. GLB viewer, OrbitControls, camera frustum rendering from `cameras.json`.
- [ ] `POST /jobs` upload flow + polling.
- [ ] Measurement tool (click-click + distance label).
- [ ] Manual scale override panel (door reference, ceiling input).

### Week 3 — furniture & polish

- [ ] Bundle ~15 IKEA GLBs into `public/furniture/`. Sidebar listing.
- [ ] Drag-to-place + TransformControls.
- [ ] AABB collision visualization.
- [ ] Top-down floor plan view + PNG export.
- [ ] LocalStorage persistence of layout per `job_id`.

### Week 4 — production readiness

- [ ] Modal Secrets for R2 credentials. Move bucket out of test mode.
- [ ] Rate limit on `POST /jobs` (5/IP/hour) to prevent runaway GPU spend.
- [ ] Custom domain on Vercel + Cloudflare.
- [ ] 90-second screen recording for portfolio.
- [ ] Write public README with the demo video embedded. Cross-link from Open Reality / Kinetik repos.
- [ ] Post on Twitter/X with the recording. Mention spatial-AI labs/companies if appropriate.

## Stretch — only if Week 4 lands ahead of schedule

- [ ] Automatic reference-object detection (Strategy 2 automatic from [`04-metric-scaling.md`](04-metric-scaling.md)). YOLOv8-seg fine-tuned on doors/outlets/switches.
- [ ] Semantic segmentation of point cloud (floor / wall / ceiling) using SAM-2 + plane fitting.
- [ ] Auto-extracted parametric floor plan (RoomPlan-style: rectangular wall list with openings) — needs the segmentation pass first.
- [ ] Mobile capture mode: a stripped-down PWA that just records video and uploads, so people without an iPhone Pro can scan rooms.

## Explicit non-roadmap

- Real-time / SLAM-style streaming reconstruction.
- Sub-1% accuracy improvements (would require structured light, IMU fusion, or bundle adjustment — none of which fit the "video already taken" constraint).
- A user-account system. The demo is anonymous; layouts are stored in localStorage only.
- Native mobile apps. The web viewer works on phones; that's enough.

## Decision points along the way

| Decision | When | What to compare |
|----------|------|-----------------|
| Self-host VGGT vs. stay on Replicate | End of Week 1 | Latency + control vs. cost of dev time |
| UniDepth v2 vs. Metric3D v2 vs. Depth-Anything-V2 | End of Week 1 | Empirical scale-factor accuracy on 3+ test videos |
| R3F vs. raw Three.js | Start of Week 2 | If R3F is slowing rendering of dense point clouds, drop to raw |
| Custom GLB collision vs. cannon-es physics | Mid Week 3 | Just AABB is probably enough; only add cannon if user wants real physics |
| Public launch vs. private demo | End of Week 4 | Polish level + cost-protection level |
