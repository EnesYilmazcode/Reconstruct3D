# 04 — Metric scaling

This is the technically interesting part. VGGT gives shape; this layer gives size.

## The fundamental problem

A monocular camera moving through a scene produces images that are invariant under uniform scaling: a 1 m wide hallway captured from 0.5 m away looks identical to a 2 m wide hallway captured from 1 m away. No amount of clever multi-view geometry recovers absolute scale from images alone — you need an additional source of information.

Sources of metric information available to us:

1. **Strong learned priors** from a metric-depth network trained on indoor scenes (UniDepth v2, Metric3D v2, Depth-Anything-V2-Metric). The network has seen enough rooms to guess that "this looks like a 2.5 m ceiling."
2. **Objects of known dimension** in the frame (doors, light switches, outlets, ceiling height conventions).
3. **One ground-truth measurement** asked of the landlord ("how tall is the ceiling?").

We use all three, in that priority order, with the lower-priority ones serving as cross-checks.

## Strategy 1 (primary) — UniDepth v2

### Why it's the default

- Zero user input required.
- Trained specifically for metric monocular depth on indoor + outdoor data.
- ~5–15% error on indoor scenes per the UniDepth paper.
- Single forward pass per keyframe (~1–2 s on A10G).

### Implementation

See [`03-pipeline.md`](03-pipeline.md) Stages 3–4. Summary: run UniDepth on N keyframes, compute the median per-pixel ratio of UniDepth meters to VGGT canonical units, take median across keyframes.

### Failure modes

- **Untextured walls**: UniDepth tends to over-flatten white walls. Mitigated by masking out low-gradient regions before computing the ratio.
- **Reflective surfaces** (mirrors, TVs, polished countertops): both models hallucinate depth. Mask using a quick gradient + mean-color heuristic, or use a SAM-2 segmentation pass to drop "screen-like" regions.
- **Per-keyframe disagreement**: if the std of per-keyframe scales exceeds 15% of the median, fall back to Strategy 2.

## Strategy 2 (cross-check) — Reference object in the video

### Standard US dimensions (interior, residential)

Burn this list into the codebase as a prior:

| Object | Standard dimension | Confidence |
|--------|-------------------|-----------|
| Interior door height | 80 in (2.032 m) | Very high — code-mandated |
| Interior door width | 32 or 36 in (0.81 / 0.91 m) | High — bedroom usually 32, main 36 |
| Outlet plate | 4.5 × 2.75 in (0.114 × 0.070 m) | Very high — NEMA standard |
| Light switch plate | 4.5 × 2.75 in (same as outlet) | Very high |
| Outlet center from floor | 12 in (0.305 m) | Medium — varies |
| Switch center from floor | 48 in (1.219 m) | Medium |
| Ceiling height (older NYC) | 8 ft (2.44 m) | Medium |
| Ceiling height (newer NYC builds) | 9 ft (2.74 m) | Medium |
| Standard fridge height | 70 in (1.78 m) | Medium |
| Standard toilet seat height | 17 in (0.43 m) | Medium |
| Kitchen counter height | 36 in (0.91 m) | High |

### Implementation

Two flows:

#### Manual (Track A, this week):
1. User opens the unmetricized .glb in the Three.js viewer.
2. Clicks "Add reference."
3. Picks an object from the dropdown ("Interior door, height").
4. Clicks two points on it in the 3D scene.
5. Frontend computes `scale = real_dim / clicked_distance`.
6. Frontend rewrites all measurements with the new scale; user can swap reference and re-scale instantly.

#### Automatic (Track B, later):
1. Run YOLOv8-seg or DETR on a few keyframes detecting `{door, outlet, switch, fridge, toilet}`.
2. Project bounding box corners back into 3D using VGGT poses.
3. Take the dimension along the dominant axis of the detected object.
4. Compute scale per detection, take median across detections.

## Strategy 3 (sanity check) — Ask one question

If the renter can squeeze one number out of the landlord, even just **ceiling height in this specific apartment**, that becomes a perfect anchor.

The viewer should expose a "set ceiling height" input that overrides whatever the model computed. This lets the user pin one known truth and have everything else fall into place.

## Combining strategies

Compute all three when possible. Surface them side-by-side in `run.json`:

```json
"scale_method": "unidepth_median",
"scale_factor": 1.247,
"scale_factor_alternative_door_ref": 1.193,
"scale_factor_alternative_unidepth_keyframe_5": 1.281,
"scale_factor_alternative_user_ceiling_input": null
```

If two methods disagree by >10%, raise a warning. If three agree within 5%, mark the result as "high confidence" in the UI.

## Why not a single canonical reference (e.g., a banana)?

The classic "include a known object" trick assumes you can re-shoot. Our input is a video already filmed without any planted reference. The strategies above all work on found imagery.

## What we are explicitly choosing to skip

- **Camera EXIF + IMU fusion**: phone IMU data isn't in standard mp4 containers; even if it were, single-camera VIO without ground-truth scale calibration buys us ~5–10% error — same neighborhood as UniDepth, more code.
- **Multi-view stereo with bundle adjustment**: COLMAP-style pipelines also produce scale-ambiguous reconstructions. Doesn't help.
- **AR Cloud / GPS scale**: indoors, GPS is useless and there's no AR session.
