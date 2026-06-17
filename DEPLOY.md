# Deployment — Staging

Sprint 1 targets a simple staging environment. Two common paths:

## Option A — Docker host (single VM)

```bash
# On the staging VM (Docker + Compose installed)
git clone <repo> && cd d_man
docker compose up -d --build
# frontend → :3000, backend → :8000
```

Put Nginx/Caddy in front to terminate TLS and route `/api` → backend.

## Option B — Managed (recommended for speed)

- **Frontend** → Vercel. Import the `frontend/` directory; set
  `NEXT_PUBLIC_API_BASE` to the backend's public URL.
- **Backend** → Fly.io / Render / Railway using `backend/Dockerfile`.
  Mount a volume for `storage/results` or swap to S3 (Phase 3).

## CI hook

`.github/workflows/ci.yml` has a `deploy-staging` job gated on `main`.
Add provider credentials as repo secrets and replace the placeholder step:

- Vercel: `amondnet/vercel-action` or `vercel deploy --prod`
- Fly: `flyctl deploy --remote-only` with `FLY_API_TOKEN`

## Smoke check after deploy

```bash
curl -s https://<backend>/api/health        # {"status":"ok", ...}
curl -s https://<backend>/api/garments | jq  # 5 shirts
```
