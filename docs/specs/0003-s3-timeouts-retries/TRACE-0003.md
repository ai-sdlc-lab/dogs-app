# TRACE-0003: security traceability

Requirements: appsec-baseline `requirements/security-requirements.md` @ `b6fc1ac2a020732ba4da5c04102e1b1faf5cf456`
Artifacts reviewed: INT-0003.md, SPEC-0003.md @ working tree of `stage/0003-spec` (round 3)

## Triggers
| Trigger | True? | Why |
|---|---|---|
| INPUT | false | No new input (SPEC 2: no new endpoint, parameter, header or setting). The breed check is unchanged and runs before any S3 call (1.8). |
| ENDPOINT | true | The error behaviour of `GET /api/dogs` and `GET /api/dogs/{breed}` changes (new 503). |
| WRITE | false | Read-only app; every S3 call is a read (1.1). |
| FILE | true | The app lists images and serves presigned image URLs (SPEC 8). There is no upload, so the upload requirements are N/A. |
| AUTHN | false | Public and anonymous; `actor` is always `anonymous` (SPEC 4). |
| AUTHZ | false | Same data for every caller (SPEC 5). |
| CRYPTO | false | Jitter is load spreading, not a security value (1.3); no TLS, hashing or token change. |
| DATA | true | The new log line carries `source_ip`, a network address (SPEC 6). |
| LOG | true | New event `dependency.unavailable` (1.6). |
| SECRET | false | No credential, key or token added (SPEC 4). |
| DEP | false | No dependency, image or tool added (1.8). The version file is written by `make build` into the zip. |
| IAC | false | No infrastructure or IAM change; Lambda 10 s / 128 MB unchanged (1.4, 1.8). |
| CI | false | No workflow change (1.6 version row, D-6). |
| AI | false | No LLM or agent behaviour in the app. |

## Requirements
| SR | Level | Status (covered / missing / N/A) | Where (artifact § and named test) | Justification |
|---|---|---|---|---|
| SR-001 | MUST | N/A | - | INPUT is false: no new input; the breed check is unchanged (1.8). |
| SR-002 | MUST | N/A | - | INPUT is false. |
| SR-003 | MUST | covered | SPEC 1.5, 8; `test_s3_failure_returns_503` (parsed JSON) | The 503 body comes from the JSON serialiser. |
| SR-004 | MUST | covered | SPEC 1.5, 8, 9; `test_503_has_security_headers` | Exact header values, each once, through the single header wrapper; no CSP/COOP/CORS/Cache-Control on JSON. |
| SR-005 | MUST | missing | SPEC 1.5, 7, 8; `test_s3_failure_returns_503`, `test_partial_listing_failure_returns_503`, `test_non_s3_error_still_500` | The 503 path is fully met. Old gap stays: other error bodies are not the SR-005 body and `error.unhandled` is not logged (SPEC-0002 D-1). The spec says "Gap (not met)". Pre-existing, not altered here. |
| SR-006 | MUST | covered | SPEC 1.2 to 1.5, 1.7, 3, 8, 9; `test_s3_client_config_timeouts_and_retries`, `test_s3_failure_returns_503`, `test_retries_at_most_two`, `test_backoff_bounds`, `test_s3_deadline_with_hanging_stub`, `test_s3_resources_released` | 2 s connect and 3 s read (maxima 3 s and 5 s); at most 2 retries with backoff, reads only; 8 s deadline below the 10 s timeout; 503 with the SR-005 body; resources released; SDK retries off, so total attempts are 1 per SDK call. |
| SR-007 | MUST | covered | SPEC 1.4, 3, 8; `test_function_timeout_exceeds_s3_deadline` | Timeout 10 s, memory 128 MB unchanged; reserved concurrency is the documented lab exception. |
| SR-008 | MUST | N/A | - | FILE is true only for serving; there is no upload (SPEC 8). |
| SR-009 | MUST | N/A | - | FILE is true only for serving; there is no upload. |
| SR-010 | MUST | N/A | - | FILE is true only for serving; there is no upload. |
| SR-011 | MUST | N/A | - | FILE is true only for serving; there is no upload. |
| SR-012 | MUST | N/A | - | The app creates no storage keys; keys come from the bucket listing (1.8). |
| SR-013 | MUST | covered | SPEC 3, 8 | Presigned URL lifetime unchanged at 900 s (at most 900 s); not touched by this change. Weak evidence: no new test, existing behaviour. |
| SR-014 | MUST | N/A | - | FILE is true only for serving; there is no upload or quarantine. |
| SR-015 | MUST | N/A | - | No upload or write (FILE serving only, WRITE false). |
| SR-016 | MUST | N/A | - | AUTHN is false. |
| SR-017 | MUST | N/A | - | AUTHN is false. |
| SR-018 | MUST | N/A | - | AUTHN and AUTHZ are false. |
| SR-019 | MUST | N/A | - | AUTHN is false. |
| SR-020 | MUST | N/A | - | AUTHZ and WRITE are false. |
| SR-021 | MUST | N/A | - | CRYPTO and SECRET are false; jitter is not security-relevant (1.3). |
| SR-022 | MUST | missing | SPEC 1.2, 8 | Endpoint stays `https://s3.<region>.amazonaws.com` with certificate validation on. Old gap stays: no `s3:TlsVersion` < 1.2 bucket deny and no TLS 1.1 test (SPEC-0002 D-3). The spec says gap unchanged. Pre-existing, IAC not touched here. |
| SR-023 | MUST | covered | SPEC 8 | Bucket SSE-S3 `AES256` unchanged; the log group has the AWS-managed default (lab exception); no new store. |
| SR-024 | MUST | missing | SPEC 1.6, 7, 8, D-4, D-6; `test_dependency_unavailable_log_event`, `test_503_body_and_log_leak_nothing`, `test_version_from_build_file`, `test_version_unknown_when_missing_or_invalid` | The new event is fully specified: all mandatory fields, JSON-encoded values, `source_ip` from the platform context only, `version` = full commit SHA read from the build file and validated against `^[0-9a-f]{40}$` (resolves AUD-007), the new event name covered by EXC-002. Old gap stays: the other mandatory events are not emitted by the current code (pre-existing). |
| SR-025 | MUST | covered | SPEC 1.6, 6, 8 | `source_ip` is listed with purpose, storage (existing log group), retention (7 days); no query string, header or body; no third party. |
| SR-026 | MUST | N/A | - | SECRET, CI and IAC are false; no secret added. |
| SR-027 | MUST | N/A | - | DEP and CI are false; no dependency or build tool added. |
| SR-028 | MUST | N/A | - | IAC is false. |
| SR-029 | MUST | N/A | - | IAC is false. |
| SR-030 | MUST | N/A | - | CI is false. |
| SR-031 | MUST | N/A | - | AI and CI are false. |

## Summary
Covered: 7 · Missing: 3 · N/A: 21

Round 3: AUD-007 resolved (version is the commit SHA from a build-written file, validated, two named tests). AUD-008 resolved (the upload requirements SR-008 to SR-011, SR-014, SR-015 are listed separately with a reason tied to FILE serving only; SR-012 and SR-013 are separate). The three missing rows (SR-005, SR-022, SR-024) are old debt that this change does not alter; they are reported as pre_existing and do not block.
