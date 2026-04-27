# 06 — Deployment

## Production topology

| Component | Where | Why |
|-----------|-------|-----|
| Frontend | Vercel | Free tier covers personal scale; auto-deploys on `main` push |
| API gateway | Modal CPU function (always-warm-ish) | Modal handles HTTPS, autoscaling, no infra |
| Reconstruct worker | Modal A10G GPU function (scales to zero) | Pay-per-second; idle cost = $0 |
| Object store | Cloudflare R2 | No egress fees on user GLB downloads |
| DNS | Cloudflare | Same account as R2 |

## Modal app — single file deploys gateway + worker

```python
# modal_app.py
import modal

VOLUME = modal.Volume.from_name("vggt-weights", create_if_missing=True)

base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.0",
        "torchvision",
        "huggingface_hub",
        "open3d",
        "trimesh",
        "fastapi[standard]",
        "boto3",
    )
    .run_commands(
        "pip install git+https://github.com/facebookresearch/vggt.git",
        "pip install git+https://github.com/lpiccinelli-eth/UniDepth.git",
    )
)

app = modal.App("reconstruct3d")

@app.function(image=base_image, timeout=300)
@modal.fastapi_endpoint(method="POST", label="jobs")
async def create_job(video_url: str):
    job_id = str(uuid.uuid4())
    reconstruct.spawn(job_id, video_url)
    return { "job_id": job_id, "status": "queued" }

@app.function(
    image=base_image,
    gpu="A10G",
    timeout=600,
    volumes={"/weights": VOLUME},
)
def reconstruct(job_id: str, video_url: str):
    # See docs/03-pipeline.md for what this function does
    ...
    upload_to_r2(job_id, "scene.glb", "cameras.json", "run.json")
    return { "job_id": job_id, "status": "ready" }
```

Deploy:

```bash
modal deploy modal_app.py
# → https://<workspace>--reconstruct3d-jobs.modal.run
```

## Replicate fallback for Track A

Don't build the Modal worker on day one. Use Replicate for the first end-to-end demo so the frontend can ship in parallel:

```python
import replicate
output = replicate.run(
    "vufinder/vggt-1b-depth",
    input={"images": [open(f, "rb") for f in frame_paths[:24]]},
)
# output["glb"] is a URL to the reconstruction
```

Caveats:
- Uses VGGT-1B-Commercial weights — point map head removed; we'd need to derive points from depth.
- Doesn't run UniDepth — Track A scaling has to use a manual reference object instead.
- Cost: ~$0.05–0.20 per video. Fine for testing, painful for production.

Plan: ship Track A using Replicate + manual scaling. Build the Modal worker for Track B.

## Environment variables

| Var | Used by | Notes |
|-----|---------|-------|
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | local dev | from `modal token new` |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY` / `R2_SECRET_KEY` | worker | Cloudflare dashboard |
| `R2_BUCKET` | worker | e.g., `reconstruct3d-jobs` |
| `REPLICATE_API_TOKEN` | Track A scripts only | deletable once Modal worker ships |
| `VITE_API_BASE` | frontend | Modal endpoint URL |

`.env` files go in `.gitignore`. Secrets in production are stored in Modal Secrets and Vercel env vars, not committed.

## Cost model

Assumes 100 video uploads/month at 30 s each.

| Line item | Unit cost | Monthly |
|-----------|-----------|---------|
| Modal A10G compute (~80 s/job) | $1.10/hr → $0.024/job | $2.40 |
| Modal CPU gateway | ~$0.50 idle baseline | $0.50 |
| R2 storage (1 GB amortized) | $0.015/GB-mo | $0.02 |
| R2 egress | $0 | $0.00 |
| Vercel hobby tier | $0 | $0.00 |
| Domain | ~$10/year | $0.83 |
| **Total** | | **~$4/mo** |

Worst case (someone shares the demo and 1000 people try it): ~$30/mo. Pull the rate-limit lever in the gateway if that happens.

## Local development

The whole worker can run locally on a 16 GB+ machine, but the 4 GB 3050 will OOM on VGGT past ~6 frames. For dev:

```bash
# Lightweight — frontend only, points at deployed Modal worker
cd frontend && npm run dev

# End-to-end — runs the Modal worker locally on your GPU
modal serve modal_app.py  # hot-reloads on file change

# Tiny smoke test — just the pipeline, no Modal
python scripts/local_pipeline.py --video data/raw/test.mp4 --max-frames 8
```

## CI/CD

- GitHub Actions on push:
  - `frontend/`: typecheck, lint, build, deploy preview to Vercel.
  - `worker/`: `python -m pytest tests/`, then `modal deploy --env=staging`.
  - On tag `v*`: promote to `--env=production`.
- No mock GPUs in CI. Pipeline tests use saved `.npz` fixtures of expected VGGT outputs.
