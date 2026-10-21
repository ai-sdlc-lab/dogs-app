# Phase 3 report: dogs-app minimal and deployed (Stage 0)

Dates: 2026-10-16 to 2026-10-21. Status: **done**.

## Outcome

| Done criterion | Result | Evidence |
|---|---|---|
| App live, shows seeded dogs | ✅ 10 CC0 images, 9 breeds, breed filter | Function URL (changes on rebuild; see the latest deploy run summary) |
| First deploy proves the OIDC environment `sub` | ✅ observed `repo:ai-sdlc-lab@343500886/dogs-app@1422084569:environment:dev`, exactly as trusted | deploy runs 39604174059, 39605531934 (claims printed by `deploy.yml`) |
| `make destroy` + redeploy | ✅ 11 destroyed (local, `sdlc-lab-admin`), 11 re-added from CI (run 39605531934 attempt 2); bootstrap untouched | |
| `ci.yml` green incl. kind | ✅ api, web, infra, kind (deploy + `/api/health`), `ci` | PR #1 to #3 checks |
| Deployed by GitHub Actions only | ✅ OIDC → STS → terraform apply → seed → smoke test; no stored credentials | `deploy.yml` |

## Architecture as built

```
browser ──HTTPS──> Lambda function URL (auth NONE, read-only)
                    └─ FastAPI + Mangum: /api/health, /api/dogs, /api/dogs/{breed}, static web
                         └─ S3 sdlc-lab-app-dogs-dev-992382408037 (private, SSE-S3, TLS-only)
                              images reach browsers as 15-minute presigned URLs
```

Lambda: python3.14, arm64, 128 MB, 10 s timeout, logs 7 days. Container image (uvicorn, non-root, read-only rootfs) runs the same API on kind in CI.

## Decisions

| Decision | Why | Source |
|---|---|---|
| **No CloudFront** (fallback A) | CI could not be kept off the other project's CloudFront resources: OAC actions have no tag/condition keys (Update/Delete need `*`); `CreateDistributionWithTags` also authorizes `TagResource`, and requiring `aws:ResourceTag` at create time is undocumented | Service Authorization Reference (JSON v1.4) |
| **Mangum**, not Lambda Web Adapter | Both maintained; Web Adapter needs a layer from AWS's account (boundary blocks `lambda:GetLayerVersion` on foreign ARNs) or ECR | GitHub releases, boundary |
| OIDC → STS with the runner's AWS CLI, not `aws-actions/configure-aws-credentials` | Not on the BL-01 allowlist and not needed | |
| Function URL `NONE` needs two permissions | Since Oct 2025: `InvokeFunctionUrl` + `InvokeFunction` (`InvokedViaFunctionUrl`) | Lambda docs, urls-auth |

## Defects found by deploying (not by CI)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Deploy 1 failed at "Assume dev role" with `NoCredentials` | Role assumption succeeded; my in-step `get-caller-identity` ran before `$GITHUB_ENV` applies (later steps only) | Separate step (PR #2) |
| 2 | Deploy 2 smoke test: presigned image URL → 400 | boto3 signed for the global `s3.amazonaws.com`, which returns `TemporaryRedirect` for new buckets | Regional endpoint + regression test (PR #3) |
| 3 | First CI run: `infra` job failed | `terraform validate` evaluates `filebase64sha256()` on a zip that only exists after `make build` | Placeholder zip in the validate job |

## Measurements

| Metric | Value |
|---|---|
| Cold start | Init ~1.5 s + first request ~1.0 s |
| First `/api/dogs` on a fresh instance | ~2.5 s (S3 client + list + 10 presigns) |
| Warm requests | 6–370 ms |
| Peak memory | 111 MB of 128 MB (13% headroom) |
| Account Lambda concurrency limit | **10**, shared with the other project; reserved concurrency impossible |
| Estimated cost | ~$0/month (within Lambda/S3/CloudWatch free tiers) |
| CI duration (ci.yml) | ~1.5 min, kind job dominant |

## Human interventions (data for Mode A/B)

| # | Intervention | Why it needed a human | Avoidable? |
|---|---|---|---|
| 1 | Chose fallback A over CloudFront | Security/scope trade-off in a shared account | No: a design decision |
| 2 | `aws login` (twice) | Session expiry (12 h max); no stored keys by design | No: the cost of no long-lived credentials |
| 3 | Root updated the `sdlc-lab-admin` policy | The admin identity can't edit its own policy (anti-escalation) | No: deliberate |
| 4 | Claude Code auto-mode blocked apply, PR merge and reading CI logs | The agent's own safety classifier had no context that this is a lab | Yes: `autoMode` environment/allow entries in user settings; switched to approval prompts instead |
| 5 | Approved merges/applies via prompts | Mode A by choice | Policy |

## Security checks on the live app

- Unsigned direct read of the images bucket → **403**; presigned read → 200
- `/docs`, `/openapi.json` → 404 (disabled); invalid/unknown breed and `..%2F` → 404
- Web renders API data with DOM APIs only (no `innerHTML`)

## Gaps carried forward (see lab-admin `docs/BASELINE.md`)

- Public unauthenticated function URL, no CDN/WAF; **account concurrency limit of 10 is shared**, so flooding our URL can throttle the other project's Lambdas (cross-tenant availability risk) and reserved concurrency can't cap it.
- Function URL hostname changes on every rebuild.
- Python deps pinned by version, not hash; kind node image not pinned by digest.
- Memory headroom 13% at 128 MB.

## Next

Phase 4: spec chain, security agents and code gates.
