"""Diagnose why a vggt-1b reconstruction looks collapsed.

Pulls per-frame stats from the JSON outputs and saves preview JPGs so we can
visually confirm what the model actually saw and predicted.

Usage:
    python scripts/diagnose.py data/recon/room1
"""
import argparse
import base64
import json
from pathlib import Path

import numpy as np
from PIL import Image


def decode(field):
    raw = base64.b64decode(field["data"])
    return np.frombuffer(raw, dtype=np.dtype(field["dtype"])).reshape(field["shape"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("recon_dir", type=Path)
    args = p.parse_args()

    previews_dir = args.recon_dir / "_previews"
    previews_dir.mkdir(exist_ok=True)

    json_files = sorted(args.recon_dir.glob("image_*.json"))
    print(f"Found {len(json_files)} frames\n")

    print(f"{'frame':<6} {'cam_pos (xyz)':<32} {'pts_bbox (min->max per axis)':<60} {'mean_conf':>10} {'depth_med':>10}")
    print("-" * 130)

    cam_positions = []
    all_bbox_mins = []
    all_bbox_maxs = []

    for jp in json_files:
        d = json.loads(jp.read_text())
        pose_enc = decode(d["pose_enc"])  # [9]
        wp = decode(d["world_points"])    # [H,W,3]
        wpc = decode(d["world_points_conf"])
        depth = decode(d["depth"])
        img = decode(d["image"])

        # VGGT pose_enc is typically [tx, ty, tz, qx, qy, qz, qw, fx, fy] or similar.
        # Without the helper, just look at the first 3 dims as a translation proxy.
        cam_xyz_proxy = pose_enc[:3]
        cam_positions.append(cam_xyz_proxy)

        pts = wp.reshape(-1, 3)
        bbox_min = pts.min(axis=0)
        bbox_max = pts.max(axis=0)
        all_bbox_mins.append(bbox_min)
        all_bbox_maxs.append(bbox_max)

        bbox_str = f"x:{bbox_min[0]:+.1f}->{bbox_max[0]:+.1f} y:{bbox_min[1]:+.1f}->{bbox_max[1]:+.1f} z:{bbox_min[2]:+.1f}->{bbox_max[2]:+.1f}"
        print(f"{jp.stem:<6} {str(cam_xyz_proxy.round(2)):<32} {bbox_str:<60} {wpc.mean():>10.3f} {np.median(depth):>10.3f}")

        # Save preview JPG of what the model saw
        Image.fromarray(img).save(previews_dir / f"{jp.stem}.jpg", quality=85)

    print()
    cam_positions = np.array(cam_positions)
    cam_spread = cam_positions.max(axis=0) - cam_positions.min(axis=0)
    print(f"pose_enc[:3] spread across frames (should be non-zero if camera moved):")
    print(f"  {cam_spread}")
    print(f"  total magnitude: {np.linalg.norm(cam_spread):.3f}")

    print()
    bb_mins = np.array(all_bbox_mins)
    bb_maxs = np.array(all_bbox_maxs)
    global_min = bb_mins.min(axis=0)
    global_max = bb_maxs.max(axis=0)
    extent = global_max - global_min
    print(f"Global world_points extent across all frames: {extent}")
    print(f"  ratio (longest/shortest): {extent.max() / max(extent.min(), 1e-6):.2f}")
    print(f"  -> a real room is roughly 4:4:2.5 (length:width:height); a tube is >>10:1")

    # Per-frame center-of-mass — should drift across frames if cam moved through space
    print()
    print("Per-frame world_points center-of-mass (should drift):")
    for i, jp in enumerate(json_files):
        d = json.loads(jp.read_text())
        wp = decode(d["world_points"]).reshape(-1, 3)
        com = wp.mean(axis=0)
        print(f"  {jp.stem}: com = {com.round(3)}")

    print(f"\nPreviews saved to {previews_dir}")


if __name__ == "__main__":
    main()
