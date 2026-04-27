# 03 — Pipeline

This document describes the **self-hosted Track B pipeline** that calls VGGT and UniDepth weights directly from a Modal worker. The Track A path uses the Replicate-hosted model (`vufinder/vggt-1b`), which accepts a video file as input and runs all of Stages 0–2 internally — see [`06-deployment.md`](06-deployment.md#replicate-fallback-for-track-a).

The worker runs a strictly sequential pipeline. Each stage's output is checkpointed to disk so failures mid-run can resume.

## Stage 0 — Frame extraction (ffmpeg, ~1–3 s)

```bash
ffmpeg -i input.mp4 \
       -vf "fps=2,scale=518:-2" \
       -q:v 2 \
       frames/%04d.jpg
```

Tunables:

- **`fps`**: default 2. For fast pans use 4. For static-with-occasional-rotation use 1.
- **`scale=518:-2`**: VGGT-1B was trained at 518px on the long edge. Going higher inflates VRAM with marginal quality gain. Going lower (e.g., 384) is the only way to fit on a 4 GB 3050.
- **Frame budget**: cap at ~60 frames per chunk. VGGT memory grows quadratically with frame count.

For long videos (>30 s), chunk with overlap:

```python
chunk_size = 24
overlap = 4
chunks = [frames[i:i+chunk_size] for i in range(0, len(frames), chunk_size - overlap)]
```

The overlap is later used to stitch chunks into a global coordinate frame (see Stage 2.5).

## Stage 1 — VGGT inference (~30–60 s on A10G)

```python
import torch
from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images

device = "cuda"
model = VGGT.from_pretrained("facebook/VGGT-1B").to(device).eval()

images = load_and_preprocess_images(frame_paths).to(device)  # [N, 3, H, W]

with torch.no_grad(), torch.amp.autocast("cuda", dtype=torch.bfloat16):
    predictions = model(images)
# predictions: { "depth": [N, H, W, 1],
#                "world_points": [N, H, W, 3],
#                "pose_enc": [N, 9]   # encoded camera pose
#              }
```

Notes:

- Use bfloat16 autocast on A10G/L40S. fp32 doubles VRAM and barely changes output.
- `pose_enc` is a compact 9-dim representation; convert to 4×4 extrinsic with VGGT's `pose_encoding_to_extri_intri` helper.
- For the **commercial** weights (VGGT-1B-Commercial), the point-map head is removed — derive points from depth + intrinsics + pose instead. Not used in this project; we self-host the original CC-BY-NC weights for Track B and call `vufinder/vggt-1b` (full model, all heads) for Track A on Replicate.

## Stage 2 — Convert to point cloud

Two options, ranked:

### Option A (preferred): unproject depth using camera

```python
def depth_to_world_points(depth, intrinsics, extrinsic_w2c):
    H, W = depth.shape
    u, v = np.meshgrid(np.arange(W), np.arange(H))
    z = depth
    x = (u - intrinsics[0,2]) * z / intrinsics[0,0]
    y = (v - intrinsics[1,2]) * z / intrinsics[1,1]
    cam_points = np.stack([x, y, z, np.ones_like(z)], axis=-1)
    world = (np.linalg.inv(extrinsic_w2c) @ cam_points.reshape(-1, 4).T).T
    return world[..., :3].reshape(H, W, 3)
```

Color each point by sampling the source frame at `(u, v)`.

### Option B: use VGGT's `world_points` head directly

Faster (no math) but lower quality on edges and skies. Use Option A.

After per-frame unprojection, concatenate all points and voxel-downsample to control point count:

```python
import open3d as o3d
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(all_world_points)
pcd.colors = o3d.utility.Vector3dVector(all_colors)
pcd = pcd.voxel_down_sample(voxel_size=0.01)  # 1 cm in canonical units
```

For Track B, also run statistical outlier removal — VGGT often emits a few stragglers behind the camera.

## Stage 2.5 — Multi-chunk alignment (long videos only)

Skip if the whole video fit in one VGGT chunk.

For each pair of consecutive chunks, run ICP between the overlapping frames' point clouds:

```python
result = o3d.pipelines.registration.registration_icp(
    source=chunk_b_pcd,
    target=chunk_a_pcd,
    max_correspondence_distance=0.05,
    init=np.eye(4),
    estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint()
)
chunk_b_pcd.transform(result.transformation)
```

Compose all transforms left-to-right against the first chunk's frame.

## Stage 3 — Metric depth (UniDepth v2, ~5–10 s)

Run on a few keyframes (every 10th VGGT frame is plenty):

```python
from unidepth.models import UniDepthV2
unidepth = UniDepthV2.from_pretrained("lpiccinelli/unidepth-v2-vitl14").to(device)

keyframe = load_image(keyframe_path).to(device)  # [3, H, W]
out = unidepth.infer(keyframe)
metric_depth = out["depth"]  # [1, H, W] in meters
intrinsics_metric = out["intrinsics"]  # learned intrinsics in metric units
```

This stage is decoupled from VGGT — UniDepth doesn't see camera poses. Its only job is to give a metric-scale ground truth depth that we use in Stage 4 to find the scale factor.

## Stage 4 — Solve scale factor

For each keyframe, we have:
- VGGT depth (canonical units, scale-ambiguous): `d_vggt`
- UniDepth depth (meters): `d_metric`

Both should differ by a constant factor at every pixel **of valid scene** (not sky, not specular). Use median ratio for robustness:

```python
def solve_scale(d_vggt, d_metric, valid_mask):
    ratios = d_metric[valid_mask] / d_vggt[valid_mask]
    return np.median(ratios)

per_keyframe_scales = [solve_scale(...) for kf in keyframes]
final_scale = np.median(per_keyframe_scales)  # robust across keyframes
```

If the std of `per_keyframe_scales` is >15% of the median, surface a warning in `run.json` — that's a sign that one of the two models is producing bad depth on this scene.

## Stage 5 — Apply scale, serialize

```python
pcd.points = o3d.utility.Vector3dVector(np.asarray(pcd.points) * final_scale)
o3d.io.write_point_cloud("metric_pointcloud.ply", pcd)

# Convert to glb via trimesh for the web viewer
import trimesh
mesh = trimesh.PointCloud(np.asarray(pcd.points), colors=np.asarray(pcd.colors))
mesh.export("scene.glb")
```

Camera extrinsics are also scaled: translation gets `* final_scale`, rotation untouched.

## End-to-end timing target

For a 30 s, 1080p input on A10G:

| Stage | Target |
|-------|--------|
| Frame extract | 2 s |
| VGGT (1 chunk of 30 frames) | 35 s |
| Point cloud build + downsample | 5 s |
| UniDepth (5 keyframes) | 8 s |
| Scale solve | <1 s |
| GLB serialization + R2 upload | 5 s |
| **Total** | **~55 s** |

Plus ~30–60 s cold start the first time. Scale-to-zero means most user uploads pay the cold start.
