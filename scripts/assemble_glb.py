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

    for jp in json_files:
        d = json.loads(jp.read_text())
        wp = decode_array(d["world_points"])          # [H, W, 3]
        wpc = decode_array(d["world_points_conf"])    # [H, W]
        img = decode_array(d["image"])                # [H, W, 3] uint8

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
    # GLB doesn't natively support point-cloud primitives in all viewers; embed as a Scene.
    scene = trimesh.Scene(pc)
    scene.export(args.out)
    size_mb = args.out.stat().st_size / 1e6
    print(f"Wrote {args.out} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
