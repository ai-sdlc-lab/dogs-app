# TRACE-0002: security traceability

Requirements: appsec-baseline `requirements/security-requirements.md` @ `0c20e20` (pinned in appsec-baseline.lock)
Artifacts reviewed: INT-0002.md, SPEC-0002.md @ working tree of `stage/0002-spec` (round 2)

## Triggers
| Trigger | True? | Why |
|---|---|---|
| INPUT | false | No new input (SPEC 2: no new endpoint, parameter or request header). Existing breed path input is unchanged. The page now handles API `url` and `breed` data, covered under SR-003 via ENDPOINT. |
| ENDPOINT | true | Every served response changes (headers on API, page and assets). |
| WRITE | false | Read-only app; no caller can create, change or delete data. |
| FILE | true | The app serves the web build's static files (SPEC 1.1). There is no upload, so the upload requirements SR-008 to SR-015 are N/A. |
| AUTHN | false | Public, unauthenticated; no accounts or sessions (SPEC 4). |
| AUTHZ | false | Same data for every caller (SPEC 5). |
| CRYPTO | false | HSTS is a header value only; no TLS configuration, hashing or token generation is added. |
| DATA | false | No personal data (SPEC 6). |
| LOG | false | No logging added or changed (SPEC 7). |
| SECRET | false | No credentials added; deploy keeps OIDC (SPEC 4). |
| DEP | true | Conditional: the release-container and ZAP gate change in 1.7 may add a build input. Treated as true because the spec does not rule it out. |
| IAC | false | No infrastructure change (SPEC 1.5). |
| CI | true | `deploy.yml` changes (ZAP gate and smoke test, SPEC 1.7). |
| AI | false | CI calls no AI (change 0001). |

## Requirements
| SR | Level | Status (covered / missing / N/A) | Where (artifact § and named test) | Justification |
|---|---|---|---|---|
| SR-001 | MUST | N/A | - | INPUT is false: no new input. |
| SR-002 | MUST | N/A | - | INPUT is false. |
| SR-003 | MUST | covered | SPEC 1.6a, 8, 9; `test_breed_with_script_renders_as_text`, `test_api_json_encodes_markup_in_filename`, `test_frontend_rejects_non_https_or_foreign_image_urls`; `test_page_has_no_inline_code` (no `innerHTML`) | JSON serialiser output; text-only rendering; API `url` accepted only if `https:` on the regex-defined S3 host (no user info, no port), narrowed further by CSP. Resolves round-1 AUD-001. |
| SR-004 | MUST | covered | SPEC 1.2 to 1.7, 9; `test_security_headers`, `test_security_headers_on_unhandled_error`, `test_csp_*`, ZAP gate on rules 10019/10020/10021/10035/10038/10055, post-deploy smoke test | Exact header values, exactly-once and replace semantics, CSP/COOP on HTML only, no CORS, no Cache-Control. |
| SR-005 | MUST | missing | SPEC 8 (SR-005 row), D-1 | Error bodies stay `{"detail": ...}` / `Internal Server Error`, not `{"error","request_id"}`; no `error.unhandled` log. The spec itself says "Gap (not met)". Documented and owner-blocked by INT item 7, but a MUST that is not met. |
| SR-006 | MUST | missing | SPEC 8 (SR-006 row), D-9 | No connect<=3 s / read<=5 s timeouts, no bounded retries, S3 failure gives 500 rather than 503, no failing-S3-stub test. The spec itself says "Gap (not met)". |
| SR-007 | MUST | covered | SPEC 3, 8 | Timeout 10 s, memory 128 MB fixed in IaC; reserved concurrency is the documented lab exception. |
| SR-008 | MUST | N/A | - | No upload (FILE only means serving the app's own build). |
| SR-009 | MUST | N/A | - | No upload. |
| SR-010 | MUST | N/A | - | No upload. |
| SR-011 | MUST | N/A | - | No upload. |
| SR-012 | MUST | N/A | - | No upload and no storage keys created. |
| SR-013 | MUST | N/A | - | No uploaded files served; the presigned URL lifetime is unchanged at 900 s (SPEC 3). |
| SR-014 | MUST | N/A | - | No upload. |
| SR-015 | MUST | N/A | - | No upload or write. |
| SR-016 | MUST | N/A | - | AUTHN is false. |
| SR-017 | MUST | N/A | - | AUTHN is false. |
| SR-018 | MUST | N/A | - | AUTHN and AUTHZ are false. |
| SR-019 | MUST | N/A | - | AUTHN is false. |
| SR-020 | MUST | N/A | - | AUTHZ and WRITE are false. |
| SR-021 | MUST | N/A | - | CRYPTO and SECRET are false. |
| SR-022 | MUST | missing | SPEC 8 (SR-022 row), D-3 | HSTS and https-only CSP are covered, but the bucket policy has no `s3:TlsVersion` < 1.2 deny and there is no TLS 1.1 handshake test. The spec itself says "Gap (not met)". Applies via ENDPOINT. |
| SR-023 | MUST | N/A | - | IAC and DATA are false; no data store is changed. FILE here is only static serving. |
| SR-024 | MUST | N/A | - | LOG, AUTHN, AUTHZ, INPUT and FILE (uploads) do not apply to this change; no logging is added (SPEC 7). The gap is tracked under SR-005. |
| SR-025 | MUST | N/A | - | DATA is false. The spec notes that the CSP keeps third-party origins out. |
| SR-026 | MUST | covered | SPEC 4, 7, 8; `test_deploy_logs_no_presigned_urls` | OIDC kept; no secret or presigned URL printed by the ZAP gate or smoke test. Applies via CI. |
| SR-027 | MUST | covered | SPEC 1.7, 8; `test_deploy_workflow_hardening_kept` | Any added tool, image or action is pinned (digest, version + SHA-256, commit SHA from the allowlist). |
| SR-028 | MUST | N/A | - | IAC is false. |
| SR-029 | MUST | N/A | - | IAC is false; no resource change. |
| SR-030 | MUST | covered | SPEC 8; `test_deploy_workflow_hardening_kept` | `permissions: {}`, `persist-credentials: false`, timeout-minutes<=30, checksum-verified downloads, untrusted values only through env. |
| SR-031 | MUST | covered | SPEC 8 | CI still calls no AI; the deploy change adds none. |

## Summary
Covered: 7 · Missing: 3 · N/A: 21

Round 2: AUD-001 resolved (SPEC 1.6a and three named tests). AUD-002 (SR-005), AUD-003 (SR-006) and AUD-004 (SR-022) remain open: documented and owner-blocked by INT-0002 scope, but still unmet MUST requirements.
