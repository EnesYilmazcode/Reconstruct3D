"""Track A — call vufinder/vggt-1b on a video file via Replicate, save outputs.

Usage:
    REPLICATE_API_TOKEN=r8_... python scripts/run_replicate_vggt.py data/raw/room1.mp4 --out data/recon/room1

The model accepts a video file directly (no manual frame extraction). Returns a list
of URLs in output["data"] — we download each one and write a manifest so downstream
notebooks know what they're looking at.
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve

import replicate

MODEL_VERSION = "vufinder/vggt-1b:8f588e57226dc37aecdfceda935eac3ab3f8632b48d385a6c2d86cf6bf73cd23"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video", type=Path, help="path to input video file")
    p.add_argument("--out", type=Path, required=True, help="output directory")
    args = p.parse_args()

    if not os.environ.get("REPLICATE_API_TOKEN"):
        print("ERROR: REPLICATE_API_TOKEN env var not set", file=sys.stderr)
        return 1
    if not args.video.exists():
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)

    mime, _ = mimetypes.guess_type(args.video.name)
    mime = mime or "video/mp4"
    size_mb = args.video.stat().st_size / 1e6
    print(f"Encoding {args.video} ({size_mb:.1f} MB, {mime}) as data URL...")
    b64 = base64.b64encode(args.video.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    print(f"Calling {MODEL_VERSION.split(':')[0]} ...")
    t0 = time.time()
    output = replicate.run(
        MODEL_VERSION,
        input={
            "inputs": [data_url],
            "normals": True,
            "point_scales": True,
            "alpha_blend_onto": "keep",
            "weighted_pose_transform": True,
            "enable_pose_postprocessing": True,
        },
    )
    elapsed = time.time() - t0
    print(f"Replicate call returned in {elapsed:.1f}s")

    # output is typically a dict with a "data" list of FileOutput objects (URLs).
    # Normalize so we can both inspect and download.
    raw = output if isinstance(output, dict) else {"data": output}
    urls: list[str] = []
    for v in raw.get("data", []):
        urls.append(str(v))

    print(f"Got {len(urls)} output URLs")

    manifest = {
        "model": MODEL_VERSION,
        "input_video": str(args.video),
        "elapsed_seconds": round(elapsed, 1),
        "raw_output_keys": list(raw.keys()) if isinstance(raw, dict) else None,
        "urls": urls,
        "files": [],
    }

    for i, url in enumerate(urls):
        # Preserve the original filename from the URL path so we know which file is which.
        name = Path(urlparse(url).path).name or f"output_{i}"
        dest = args.out / name
        print(f"  [{i}] {url} -> {dest.name}")
        urlretrieve(url, dest)
        manifest["files"].append({"index": i, "url": url, "local": str(dest), "size": dest.stat().st_size})

    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
