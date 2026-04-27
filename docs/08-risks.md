# 08 — Risks and mitigations

Ordered by impact-on-success.

## R1 — The apartment video is bad input for VGGT

VGGT (and any feed-forward 3D reconstruction model) works best on:
- Slow, smooth camera motion (a real-estate "walk-through" pace)
- Overlapping coverage (each point on a wall visible from 3+ frames)
- Diffuse lighting, no harsh sun-through-window blowouts
- Textured surfaces (wallpaper, framed art) easier than flat painted walls

Landlord-shot videos often violate these:
- Quick whip-pans between rooms
- Each room visible for <2 s
- Vertical orientation, then flipped horizontal mid-video
- Backlit windows blowing out detail
- Long stretches of plain white wall with no texture

**Mitigation**:
- Pre-flight script: `scripts/inspect_video.py` reports per-second motion magnitude (optical flow), exposure histogram, and orientation changes. Surfaces "this video may be poor input" warning before paying for VGGT compute.
- If geometry is garbage on the full video, sub-clip to the slowest, best-lit segment of each room and process each room separately. The renter doesn't need a single coherent reconstruction — room-by-room is fine.
- Document this honestly in the user-facing demo: "Works best on slow walk-throughs."

## R2 — Scale ambiguity not resolved (the project's whole point)

UniDepth disagrees with the door reference; both disagree with the landlord-stated ceiling height. Now what?

**Mitigation**:
- Always surface all three estimates in `run.json` and the UI; never silently pick one.
- Default to the highest-priority strategy that the user has provided input for: landlord measurement > door reference > UniDepth.
- If all three are within 10% — high confidence, proceed.
- If they spread over >20% — the system tells the user "we cannot determine scale reliably from this video; please provide a known measurement."

This is honest engineering. Users will trust the tool more if it admits when it doesn't know.

## R3 — Modal cold-start makes the demo feel broken

A 60 s cold start before a 60 s reconstruction makes "I just uploaded a video" feel like 2 minutes of nothing.

**Mitigation**:
- `keep_warm=1` on the worker function. Costs ~$0.30/day to keep one A10G provisioned. Acceptable for a demo.
- Frontend shows progress: "Starting GPU... extracting frames... running VGGT (35 s)..." with model-name attribution. Visible activity beats a spinner.
- Pre-warm the worker when the user starts the file picker, not when they hit submit.

## R4 — IKEA GLB licensing

Bundling IKEA's 3D models in a public demo without permission is questionable. Their 3D viewer is for shopping, not redistribution.

**Mitigation**:
- For the personal-use Track A: not a concern.
- For the public Track B: replace IKEA models with CC0 / CC-BY furniture from Polyhaven, Sketchfab Free, or Quaternius (low-poly stylized — actually fits a "wireframe" demo aesthetic).
- Or: ship without bundled GLBs, let the user paste a GLB URL. Nothing to license if the user provides the file.

## R5 — Frontend point-cloud rendering is sluggish

A 500k-point GLB at 60 fps in the browser is non-trivial. R3F's default `<points>` mesh is fine for ~100k; past that it's CPU-bound.

**Mitigation**:
- Voxel-downsample to ≤200k points server-side before exporting GLB.
- Use `THREE.PointsMaterial` with `sizeAttenuation: false` and a 1–2 px size — cheaper than instanced spheres.
- LOD: a separate ~30k-point version for orbit, full 200k only when stationary >500ms.
- Worst case: ditch points and ship a Poisson-reconstructed mesh (Open3D has `create_from_point_cloud_poisson`). Renders at 60 fps trivially but loses high-frequency detail.

## R6 — Spending more than $10 on the demo by accident

A misconfigured rate limit + viral demo + 24 hours = $200 in GPU bills.

**Mitigation**:
- Rate limit 5 jobs / IP / hour at the FastAPI gateway.
- Modal `concurrency_limit=4` on the worker function — caps total concurrent GPU spend.
- Cloudflare daily-spend alert email.
- If the demo gets traction, gate uploads behind a "describe yourself in one sentence" textarea — kills bot spam.

## R7 — Spending a week on the portfolio piece and not solving the actual roommate question

Easy failure mode: get excited about the portfolio, never finish the dimension-measurement task that has a real-world deadline.

**Mitigation**:
- Track A explicitly precedes Track B in [`07-roadmap.md`](07-roadmap.md).
- Track A is allowed to be ugly: Jupyter notebooks, no UI, hardcoded paths. Get the answer, then pretty it up.
- Make the roommate decision before Day 4. The portfolio piece is wasted if the renter signed a lease they shouldn't have.

## R8 — Landlord's video is single-room loops, not a coherent walk-through

Common pattern in landlord videos: stand in the doorway, slowly rotate 360°. Move to next room, repeat.

VGGT handles this poorly because there's no parallax — pure rotation gives ambiguous depth. UniDepth still works (it's per-frame), and the *shape* of the room comes out roughly right, but absolute distances along the camera's gaze direction are unreliable.

**Mitigation**:
- Detect single-rotation segments via pose-graph analysis: if camera positions span <30 cm but orientation spans >180°, flag as "rotation-only."
- For rotation-only rooms, lean entirely on UniDepth + reference-object scaling and bypass the VGGT-vs-UniDepth ratio solver (which fails when VGGT's geometry is ambiguous).
- Surface a "rotation-only segment detected — accuracy in this room may be lower" warning to the user.

## R9 — UniDepth or VGGT installs break (CUDA/PyTorch hell)

VGGT requires `torch>=2.4`. UniDepth requires `xformers`. Both want specific CUDA versions. On a fresh Modal image, this works once and then every transitive dep update can break it.

**Mitigation**:
- Pin all versions in `modal_app.py` image build.
- Cache the built image with a version tag. Don't rebuild on every deploy.
- Local dev uses the same Modal-built image via `modal run` — no "works on my machine."

## R10 — User loses trust if first run looks wrong

The first thing a stranger sees on the demo determines whether they recommend it. If the example video produces a tilted, miscolored, twice-too-small reconstruction, they bounce.

**Mitigation**:
- Bake in a "Try with sample video" button that loads a known-good reconstruction (cached on R2, no GPU spend) so the first interaction is always clean.
- Pre-validate the sample on multiple browsers + devices.
- Empty-state hero animation showing the trajectory + point cloud forming, before the user has uploaded anything.
