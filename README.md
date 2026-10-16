# dogs-app

Read-only dog gallery: the Stage 0 target app of the AI-native S-SDLC lab (`ai-sdlc-lab`). No upload, no auth, no database.

## Architecture (Phase 3)

```
browser ──HTTPS──> Lambda function URL (auth NONE)
                    └─ FastAPI via Mangum: /api/* + built web (web/dist)
                         └─ S3 sdlc-lab-app-dogs-dev-992382408037 (private, SSE-S3)
                              images served as 15-min presigned URLs
```

No CloudFront: the lab's permissions boundary can't scope CloudFront safely in a shared account (see lab-admin `docs/BASELINE.md`), so the function URL serves everything.

| Path | What |
|---|---|
| `api/` | FastAPI: `GET /api/health`, `GET /api/dogs`, `GET /api/dogs/{breed}`. Lambda via Mangum; container via uvicorn |
| `web/` | Vite + TypeScript gallery with breed filter |
| `infra/` | Terraform, state `s3://sdlc-lab-tfstate-992382408037/apps/dogs-app/dev/terraform.tfstate` |
| `seed/` | 10 CC0 images, sources in `seed/SOURCES.md` |
| `k8s/` | Deployment + Service for the API container (kind in CI only) |

## Commands

```
cd api && python3.14 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt
make test lint build
export AWS_PROFILE=sdlc-lab-admin   # aws login
make plan            # review
make apply           # applies the saved plan only
make seed
make destroy
```

CI: `ci.yml` on pull requests (ruff, pytest, tsc + build, terraform fmt/validate, tflint, docker build, kind deploy + health). `deploy.yml` on push to `main`: environment `dev`, OIDC → `sdlc-lab-gh-dogs-app-dev`, terraform apply, seed, smoke test.
