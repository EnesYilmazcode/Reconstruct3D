"""Assemble per-frame VGGT JSON outputs into a single colored point-cloud GLB.

The Replicate deployment of vufinder/vggt-1b returns one JSON per sampled frame
with raw model outputs (depth, world_points, normals, pose, image). Each frame's
world_points are already in a shared world coordinate frame, so we just concat
them, color from the per-pixel image, filter by confidence, voxel-downsample to
keep the file size manageable, and export as GLB.

Usage:
    python scripts/assemble_glb.py data/recon/room1 --out frontend/public/sample.glb
"""
import argparse
import base64
import json
from pathlib import Path

import numpy as np
import trimesh


def decode_array(field: dict) -> np.ndarray:
    """Decode the {shape, dtype, data} dict produced by the Replicate model.

    `data` is base64-encoded raw bytes of the dtype-typed array.
    """
    raw = base64.b64decode(field["data"])
    arr = np.frombuffer(raw, dtype=np.dtype(field["dtype"]))
    return arr.reshape(field["shape"])


def quat_to_rotmat(q: np.ndarray) -> np.ndarray:
    """qx, qy, qz, qw (Hamilton) -> 3x3 rotation matrix."""
    qx, qy, qz, qw = q
    n = qx * qx + qy * qy + qz * qz + qw * qw
    if n < 1e-12:
        return np.eye(3, dtype=np.float32)
    s = 2.0 / n
    return np.array([
        [1 - s * (qy * qy + qz * qz),     s * (qx * qy - qz * qw),     s * (qx * qz + qy * qw)],
        [    s * (qx * qy + qz * qw), 1 - s * (qx * qx + qz * qz),     s * (qy * qz - qx * qw)],
        [    s * (qx * qz - qy * qw),     s * (qy * qz + qx * qw), 1 - s * (qx * qx + qy * qy)],
    ], dtype=np.float32)


def make_camera_frustum(t: np.ndarray, R: np.ndarray, size: float = 0.08, color=(255, 80, 80)):
    """Return a tiny tetrahedral frustum mesh (tip at camera center, base in front).

    R, t are camera-from-world; we build the frustum in camera-local coords then
    transform to world: world = R @ local + t (using camera-to-world).
    """
    R_c2w = R.T  # invert rotation for cam-to-world
    apex = np.array([0, 0, 0], dtype=np.float32)
    f = float(size)
    half = f * 0.5
    base = np.array([
        [-half, -half * 0.6, f],
        [+half, -half * 0.6, f],
        [+half, +half * 0.6, f],
        [-half, +half * 0.6, f],
    ], dtype=np.float32)
    local = np.vstack([apex[None, :], base])
    world = (R_c2w @ local.T).T + t[None, :]
    faces = np.array([
        [0, 1, 2],   # side
        [0, 2, 3],
        [0, 3, 4],
        [0, 4, 1],
        [1, 2, 3],   # base (two tris)
        [1, 3, 4],
    ], dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=world, faces=faces, process=False)
    mesh.visual.face_colors = np.tile(np.array([*color, 255], dtype=np.uint8), (len(faces), 1))
    return mesh


def make_axis_triad(length: float = 0.5, thickness: float = 0.01) -> trimesh.Trimesh:
    """RGB cylinders along X, Y, Z so the user can orient the scene."""
    parts = []
    for axis, color in enumerate([(255, 60, 60), (60, 200, 60), (60, 100, 255)]):
        cyl = trimesh.creation.cylinder(radius=thickness, height=length, sections=12)
        # cylinder() makes Z-aligned; rotate so it aligns with the requested axis
        if axis == 0:  # X
            T = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
        elif axis == 1:  # Y
            T = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
        else:  # Z
            T = np.eye(4)
        cyl.apply_transform(T)
        # shift cylinder so its base sits at origin and it points along +axis
        offset = np.zeros(3)
        offset[axis] = length / 2
        cyl.apply_translation(offset)
        cyl.visual.face_colors = np.tile(np.array([*color, 255], dtype=np.uint8), (len(cyl.faces), 1))
        parts.append(cyl)
    return trimesh.util.concatenate(parts)


def voxel_downsample(points: np.ndarray, colors: np.ndarray, voxel_size: float):
    """Per-voxel mean using a hash on integer cell coords. Stable, no open3d needed."""
    cells = np.floor(points / voxel_size).astype(np.int64)
    # Pack 3 ints into a single 64-bit key
    key = (cells[:, 0] * 73856093) ^ (cells[:, 1] * 19349663) ^ (cells[:, 2] * 83492791)
    _, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
    n_out = counts.size
    out_pts = np.zeros((n_out, 3), dtype=np.float64)
    out_cols = np.zeros((n_out, 3), dtype=np.float64)
    np.add.at(out_pts, inverse, points)
    np.add.at(out_cols, inverse, colors)
    out_pts /= counts[:, None]
    out_cols /= counts[:, None]
    return out_pts.astype(np.float32), np.clip(out_cols, 0, 255).astype(np.uint8)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("recon_dir", type=Path, help="dir with image_*.json files")
    p.add_argument("--out", type=Path, required=True, help="output .glb path")
    p.add_argument("--conf-quantile", type=float, default=0.3,
                   help="drop points below this quantile of world_points_conf (default 0.3 = bottom 30%)")
    p.add_argument("--voxel", type=float, default=0.01,
                   help="voxel size in canonical units (VGGT outputs are scale-ambiguous; tune by eye)")
    args = p.parse_args()

    json_files = sorted(args.recon_dir.glob("image_*.json"))
    print(f"Found {len(json_files)} frame JSONs")

    all_pts = []
    all_cols = []
    cam_centers = []
    frustums = []

    for jp in json_files:
        d = json.loads(jp.read_text())
        wp = decode_array(d["world_points"])          # [H, W, 3]
        wpc = decode_array(d["world_points_conf"])    # [H, W]
        img = decode_array(d["image"])                # [H, W, 3] uint8

        # Decode camera pose. VGGT pose_enc layout = [tx, ty, tz, qx, qy, qz, qw, fx, fy].
        pose_enc = decode_array(d["pose_enc"])
        t = pose_enc[:3].astype(np.float32)
        q = pose_enc[3:7].astype(np.float32)
        R = quat_to_rotmat(q)
        cam_centers.append(t)
        frustums.append(make_camera_frustum(t, R))

        H, W, _ = wp.shape
        pts = wp.reshape(-1, 3)
        cols = img.reshape(-1, 3)
        confs = wpc.reshape(-1)

        # Drop the lowest-confidence pixels (background / sky / specular).
        thr = np.quantile(confs, args.conf_quantile)
        keep = confs >= thr
        pts = pts[keep]
        cols = cols[keep]

        # VGGT sometimes emits stragglers far behind the camera; clip absurd magnitudes.
        norms = np.linalg.norm(pts, axis=1)
        keep = norms < np.quantile(norms, 0.99) * 3
        pts = pts[keep]
        cols = cols[keep]

        all_pts.append(pts.astype(np.float32))
        all_cols.append(cols.astype(np.uint8))
        print(f"  {jp.name}: kept {len(pts):,} / {H*W:,} pts")

    points = np.concatenate(all_pts, axis=0)
    colors = np.concatenate(all_cols, axis=0)
    print(f"Combined: {len(points):,} points before downsample")

    points, colors = voxel_downsample(points, colors.astype(np.float64), args.voxel)
    print(f"After voxel ({args.voxel}): {len(points):,} points")

    # Pad RGB to RGBA for trimesh PointCloud color field.
    rgba = np.concatenate([colors, np.full((len(colors), 1), 255, dtype=np.uint8)], axis=1)
    pc = trimesh.points.PointCloud(vertices=points, colors=rgba)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene(pc)

    # Camera trajectory: a polyline through cam centers + a frustum at each.
    if len(cam_centers) >= 2:
        centers = np.array(cam_centers, dtype=np.float32)
        traj = trimesh.load_path(centers)
        for entity in traj.entities:
            entity.color = (255, 200, 80, 255)
        scene.add_geometry(traj)
    for fr in frustums:
        scene.add_geometry(fr)

    # Axis triad scaled to the cloud's footprint so it's visible but not overwhelming.
    cloud_extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    scene.add_geometry(make_axis_triad(length=cloud_extent * 0.15, thickness=cloud_extent * 0.003))

    scene.export(args.out)
    size_mb = args.out.stat().st_size / 1e6
    print(f"Wrote {args.out} ({size_mb:.1f} MB) — {len(frustums)} camera frustums + axis triad embedded")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
