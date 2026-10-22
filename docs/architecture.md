# Architecture (as built, Phase 3)

```
browser ──HTTPS──> Lambda function URL (auth NONE, public, read-only)
                    └─ FastAPI + Mangum (python3.14, arm64, 128 MB, 10 s)
                         ├─ GET /api/health, /api/dogs, /api/dogs/{breed}
                         ├─ static web (Vite build, bundled in the zip)
                         └─ S3 sdlc-lab-app-dogs-dev-992382408037 (private, SSE-S3, TLS-only)
                              images under dogs/<breed>/, served as 15-minute presigned URLs
```

## Trust boundaries
1. Internet → function URL: unauthenticated, any caller.
2. Lambda → S3: execution role `sdlc-lab-app-dogs-api-dev` (list `dogs/`, read `dogs/*`, write its log group); carries `sdlc-lab-boundary`.
3. Browser → S3: presigned GET only; the bucket rejects unsigned reads.
4. GitHub Actions → AWS: OIDC, role `sdlc-lab-gh-dogs-app-dev`, environment `dev` (main only).
5. GitHub Actions → Claude API: OIDC workload identity federation (Anthropic rules pinned to the reviewer workflow commit and the author workflow on `main`).

## Data
Images (CC0 seed set) and their breed (from the key). No users, no personal data, no writes.

## Known gaps (lab-admin BASELINE)
No CDN/WAF; shared account Lambda concurrency limit of 10 (no reserved concurrency); function URL hostname changes on rebuild; current code predates SR-004 headers, SR-024 log format, SR-006 timeouts and SR-027 hashed locks.
