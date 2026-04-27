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


def mesh_from_frame_grid(world_points: np.ndarray, image: np.ndarray, conf: np.ndarray,
                         conf_thr: float, edge_thr: float, stride: int = 1):
    """Convert a single frame's [H,W,3] world_points grid into a triangle mesh.

    Each stride-spaced 2x2 pixel block becomes 2 triangles. We drop quads where any
    vertex is below confidence or where any edge is longer than `edge_thr` (depth
    discontinuities at object boundaries — meshing across them produces the
    "spaghetti" surfaces that connect foreground to background).
    """
    if stride > 1:
        world_points = world_points[::stride, ::stride]
        image = image[::stride, ::stride]
        conf = conf[::stride, ::stride]
    H, W, _ = world_points.shape
    verts = world_points.reshape(-1, 3).astype(np.float32)
    cols = image.reshape(-1, 3).astype(np.uint8)
    flat_conf = conf.reshape(-1)

    idx = np.arange(H * W).reshape(H, W)
    i00 = idx[:-1, :-1].ravel()
    i01 = idx[:-1, 1:].ravel()
    i10 = idx[1:, :-1].ravel()
    i11 = idx[1:, 1:].ravel()

    quad_conf_ok = (
        (flat_conf[i00] >= conf_thr)
        & (flat_conf[i01] >= conf_thr)
        & (flat_conf[i10] >= conf_thr)
        & (flat_conf[i11] >= conf_thr)
    )

    # Edge-length check: any edge longer than edge_thr -> discontinuity.
    e_top = np.linalg.norm(verts[i01] - verts[i00], axis=1)
    e_left = np.linalg.norm(verts[i10] - verts[i00], axis=1)
    e_diag = np.linalg.norm(verts[i11] - verts[i00], axis=1)
    e_right = np.linalg.norm(verts[i11] - verts[i01], axis=1)
    e_bot = np.linalg.norm(verts[i11] - verts[i10], axis=1)
    edge_ok = (e_top < edge_thr) & (e_left < edge_thr) & (e_diag < edge_thr) & (e_right < edge_thr) & (e_bot < edge_thr)

    keep = quad_conf_ok & edge_ok
    if not np.any(keep):
        return None
    f1 = np.stack([i00[keep], i01[keep], i11[keep]], axis=1)
    f2 = np.stack([i00[keep], i11[keep], i10[keep]], axis=1)
    faces = np.concatenate([f1, f2], axis=0)
    return verts, cols, faces


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
    p.add_argument("--conf-quantile", type=float, default=0.6,
                   help="drop points below this quantile of world_points_conf (default 0.6 = bottom 60%)")
    p.add_argument("--voxel", type=float, default=0.01, help="voxel size in canonical units")
    p.add_argument("--depth-multiple", type=float, default=2.5,
                   help="per-frame, drop points whose depth exceeds this multiple of the frame's median depth")
    p.add_argument("--traj-radius-factor", type=float, default=1.6,
                   help="drop points farther than this multiple of the trajectory bbox diagonal from any camera center")
    p.add_argument("--frame-pose-mad", type=float, default=3.0,
                   help="drop entire frames whose camera position is more than this many MADs from the trajectory median")
    p.add_argument("--mode", choices=["mesh", "cloud"], default="mesh",
                   help="mesh = per-frame triangle mesh from world_points grid (default, looks like surfaces); "
                        "cloud = legacy colored point cloud")
    p.add_argument("--edge-multiple", type=float, default=0.03,
                   help="for mesh mode, drop quad edges longer than this multiple of frame median depth (depth discontinuity filter)")
    p.add_argument("--stride", type=int, default=2,
                   help="for mesh mode, sample every Nth pixel of the grid (default 2 = 4x smaller mesh)")
    args = p.parse_args()

    json_files = sorted(args.recon_dir.glob("image_*.json"))
    print(f"Found {len(json_files)} frame JSONs")

    # ---- Pass 1: collect poses and median depths so we can reject bad frames ----
    poses, med_depths, payloads = [], [], []
    for jp in json_files:
        d = json.loads(jp.read_text())
        pose_enc = decode_array(d["pose_enc"])
        depth = decode_array(d["depth"])
        poses.append(pose_enc[:3].astype(np.float32))
        med_depths.append(float(np.median(depth)))
        payloads.append((jp, d, pose_enc))
    poses = np.array(poses)
    med_depths = np.array(med_depths)

    # Reject frames whose pose center is way off the trajectory median (likely a tracking failure)
    pose_median = np.median(poses, axis=0)
    pose_dev = np.linalg.norm(poses - pose_median, axis=1)
    pose_mad = np.median(np.abs(pose_dev - np.median(pose_dev))) + 1e-6
    pose_threshold = np.median(pose_dev) + args.frame_pose_mad * 1.4826 * pose_mad
    frame_pose_ok = pose_dev <= pose_threshold

    # Reject frames whose median depth is anomalous (motion-blurred frames often have abnormally high/low median depth)
    md_median = np.median(med_depths)
    md_mad = np.median(np.abs(med_depths - md_median)) + 1e-6
    md_threshold_lo = md_median - 3 * 1.4826 * md_mad
    md_threshold_hi = md_median + 3 * 1.4826 * md_mad
    frame_depth_ok = (med_depths >= md_threshold_lo) & (med_depths <= md_threshold_hi)

    frame_keep = frame_pose_ok & frame_depth_ok
    print(f"Frame filter: kept {frame_keep.sum()}/{len(json_files)} (rejected pose-outliers={(~frame_pose_ok).sum()}, depth-outliers={(~frame_depth_ok).sum()})")

    # ---- Pass 2: build cloud OR mesh from kept frames ----
    cam_centers, frustums = [], []
    frame_meshes = []   # list of (verts, cols, faces) per frame for mesh mode
    all_pts, all_cols = [], []  # for cloud mode

    for i, (jp, d, pose_enc) in enumerate(payloads):
        if not frame_keep[i]:
            print(f"  {jp.name}: SKIP (outlier frame)")
            continue
        t = pose_enc[:3].astype(np.float32)
        R = quat_to_rotmat(pose_enc[3:7].astype(np.float32))
        cam_centers.append(t)
        frustums.append(make_camera_frustum(t, R))

        wp = decode_array(d["world_points"])
        wpc = decode_array(d["world_points_conf"])
        img = decode_array(d["image"])
        depth = decode_array(d["depth"])
        med_d = float(np.median(depth))

        if args.mode == "mesh":
            conf_thr = float(np.quantile(wpc, args.conf_quantile))
            edge_thr = med_d * args.edge_multiple
            res = mesh_from_frame_grid(wp, img, wpc, conf_thr=conf_thr, edge_thr=edge_thr, stride=args.stride)
            if res is None:
                print(f"  {jp.name}: SKIP (no surviving quads)")
                continue
            verts, cols, faces = res
            frame_meshes.append((verts, cols, faces))
            print(f"  {jp.name}: {len(faces):>7,} tris (median_depth={med_d:.2f})")
        else:
            H, W, _ = wp.shape
            pts = wp.reshape(-1, 3)
            cols = img.reshape(-1, 3)
            confs = wpc.reshape(-1)
            depth_flat = depth.reshape(-1)
            keep = depth_flat <= med_d * args.depth_multiple
            keep &= confs >= np.quantile(confs, args.conf_quantile)
            pts, cols = pts[keep], cols[keep]
            all_pts.append(pts.astype(np.float32))
            all_cols.append(cols.astype(np.uint8))
            print(f"  {jp.name}: kept {len(pts):,} / {H*W:,} pts (median_depth={med_d:.2f})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()

    if args.mode == "mesh":
        # Concatenate every frame's quad mesh, offsetting face indices.
        all_verts = []
        all_cols_m = []
        all_faces = []
        v_offset = 0
        for verts, cols, faces in frame_meshes:
            all_verts.append(verts)
            all_cols_m.append(cols)
            all_faces.append(faces + v_offset)
            v_offset += len(verts)
        big_verts = np.concatenate(all_verts, axis=0)
        big_cols = np.concatenate(all_cols_m, axis=0)
        big_faces = np.concatenate(all_faces, axis=0)
        rgba = np.concatenate([big_cols, np.full((len(big_cols), 1), 255, dtype=np.uint8)], axis=1)
        big_mesh = trimesh.Trimesh(vertices=big_verts, faces=big_faces, vertex_colors=rgba, process=False)
        scene.add_geometry(big_mesh)
        print(f"Mesh: {len(big_verts):,} verts, {len(big_faces):,} tris from {len(frame_meshes)} frames")
        cloud_extent_pts = big_verts
    else:
        points = np.concatenate(all_pts, axis=0)
        colors = np.concatenate(all_cols, axis=0)
        print(f"Combined: {len(points):,} points")
        cam_arr = np.array(cam_centers, dtype=np.float32)
        traj_diag = float(np.linalg.norm(cam_arr.max(axis=0) - cam_arr.min(axis=0))) + 1e-6
        radius_cap = max(traj_diag * args.traj_radius_factor, 0.5)
        chunk = 100_000
        keep_global = np.zeros(len(points), dtype=bool)
        for i in range(0, len(points), chunk):
            sub = points[i:i + chunk]
            d2 = ((sub[:, None, :] - cam_arr[None, :, :]) ** 2).sum(-1).min(axis=1)
            keep_global[i:i + chunk] = d2 <= radius_cap * radius_cap
        points = points[keep_global]
        colors = colors[keep_global]
        print(f"Trajectory-radius filter (cap={radius_cap:.2f}): kept {len(points):,} pts")
        points, colors = voxel_downsample(points, colors.astype(np.float64), args.voxel)
        print(f"After voxel ({args.voxel}): {len(points):,} points")
        rgba = np.concatenate([colors, np.full((len(colors), 1), 255, dtype=np.uint8)], axis=1)
        pc = trimesh.points.PointCloud(vertices=points, colors=rgba)
        scene.add_geometry(pc)
        cloud_extent_pts = points

    # Camera trajectory: a polyline through cam centers + a frustum at each.
    if len(cam_centers) >= 2:
        centers = np.array(cam_centers, dtype=np.float32)
        traj = trimesh.load_path(centers)
        for entity in traj.entities:
            entity.color = (255, 200, 80, 255)
        scene.add_geometry(traj)
    for fr in frustums:
        scene.add_geometry(fr)

    # Axis triad scaled to the cloud/mesh footprint so it's visible but not overwhelming.
    cloud_extent = float(np.linalg.norm(cloud_extent_pts.max(axis=0) - cloud_extent_pts.min(axis=0)))
    scene.add_geometry(make_axis_triad(length=cloud_extent * 0.15, thickness=cloud_extent * 0.003))

    scene.export(args.out)
    size_mb = args.out.stat().st_size / 1e6
    print(f"Wrote {args.out} ({size_mb:.1f} MB) - mode={args.mode}, {len(frustums)} frustums + axis triad embedded")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
