# THREAT-0003: threat model

## Scope and change summary
SPEC-0003 (round 3) adds explicit S3 timeouts (connect 2 s, read 3 s), at most 2 app-level retries with jittered backoff, an 8 s overall per-request deadline, and a fixed `503` `dependency_unavailable` response when the S3 list call fails. It adds one log event, `dependency.unavailable`. Round 3 also reads the log `version` from a build-written file in the Lambda zip (D-6), validated against `^[0-9a-f]{40}$`, with `unknown` as the fallback.

In `api/app/main.py`, `boto3.client(..., config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))` is the only S3 client. The spec changes only its timeout and retry settings. `make build` zips `build/lambda`. No IAM, infra, CI, dependency or new-service change.

ARC-001 (the SDK must make exactly one HTTP attempt per call) is resolved. The spec now requires `total_max_attempts` 1 and not just a retry count. It also adds a test, `test_s3_client_config_timeouts_and_retries`, that counts requests reaching the stub per failing SDK call.

## Assets
- Availability and cost of the shared Lambda (128 MB, 10 s, shared account concurrency).
- Confidentiality of S3 error text, bucket name, keys and presigned URLs.
- Integrity of log lines (operator evidence).
- `source_ip` in logs (personal data, 7-day retention).
- Log `version` field (build provenance).

## Trust boundaries and data flows
| # | From → To | Data | Crosses boundary |
|---|---|---|---|
| 1 | Browser/anonymous caller → function URL → Lambda | GET path, query, headers | Yes (internet to app) |
| 2 | Lambda → S3 (regional HTTPS endpoint) | ListObjectsV2, attempts and retries | Yes (app to AWS service) |
| 3 | S3 → Lambda | listing, errors, delays or hangs | Yes (the dependency is untrusted for timing and error text) |
| 4 | Lambda → caller | 200, 404, 500 or 503 body and headers | Yes |
| 5 | Lambda → CloudWatch | `dependency.unavailable` line (path, `source_ip`, `version`) | Yes (path is attacker-controlled) |
| 6 | `make build` (local or CI) → zip → Lambda filesystem | version file (commit SHA) | Yes (build to runtime) |

## STRIDE per element
| Element | S | T | R | I | D | E | Notes |
|---|---|---|---|---|---|---|---|
| Function URL / app process | n/a (public, anonymous) | n/a | Mitigated: one log line per failed request with `request_id` | Mitigated: fixed 503 body, `cause` allow-list (M-03) | Threat: slow S3 holds the worker. Mitigated by the 8 s deadline, M-09 and 3 attempts max (M-01, M-02) | n/a (no new permissions) | Retries must not multiply: SDK attempts are 1 (M-02) |
| S3 call and retry loop | n/a | n/a | n/a | Mitigated: the exception is mapped to an allow-list | Threat: worker abandoned at the deadline keeps retrying. Mitigated by M-01. Retry stampede during an S3 outage. Mitigated by jitter and the cap | n/a | Reads only (M-06) |
| 503 response | n/a | Mitigated: header wrapper (M-04) | n/a | Mitigated: no AWS text (M-03) | n/a | n/a | Fail closed, no partial data (M-07) |
| Log line | Threat: forged `source_ip` via X-Forwarded-For. Mitigated: only the platform context (M-05) | Threat: log injection through the path. Mitigated: JSON-encoded, truncated, no query (M-05) | Mitigated | Mitigated: no URL, header or message | Mitigated: 1 line per request | n/a | |
| Version file (new) | n/a | Threat: a tampered or garbage file in the zip. Mitigated: the 40-hex check, with a fixed path and no caller input; the zip is built by the owner or CI and deployed via the `main` gate | Mitigated: version ties the log to the commit | Low: only a public SHA | Low: an unreadable or oversized file must not crash import (ARC-002) | n/a | Read once at start |
| Lambda to S3 TLS | n/a | Mitigated: certificate validation on, regional endpoint (SR-022) | n/a | n/a | n/a | n/a | |

## Abuse cases
| ID | Attacker goal and steps | Impact |
|---|---|---|
| AC-1 | Flood `GET /api/dogs` while S3 is slow, to tie up the Lambda and the shared account concurrency. Each request holds a worker for up to 8 s. | Bounded to 8 s by the deadline, below the 10 s timeout (M-02, M-09). Concurrency stays the existing lab exception (SR-007). |
| AC-2 | Cause S3 to hang (or induce slow responses) so the SDK's hidden retries multiply (default 3-5 attempts x 5 s) and run past 10 s. | Mitigated by M-02: the SDK does one attempt, so the app rule is the only retry. Tested by counting requests. |
| AC-3 | Get an abandoned worker thread to keep calling S3 after the 503, to amplify cost or leak into later requests. | Mitigated by M-01, `test_abandoned_worker_makes_no_further_attempts`. |
| AC-4 | Request a path with a newline, a 10 kB path or `?x=` to forge or split log lines or bloat logs. | Mitigated by M-05: JSON-encoded, truncated to 256, no query. |
| AC-5 | Send `X-Forwarded-For: 1.2.3.4` to poison `source_ip`. | Mitigated by M-05: only `requestContext.http.sourceIp`. |
| AC-6 | Trigger an S3 error that leaks the bucket name, a presigned URL or AWS text in the 503 body or log. | Mitigated by M-03 (fixed body, allow-list cause). |
| AC-7 | Make a presign or app bug look like a dependency outage (or the reverse) to hide it from the owner. | Mitigated by M-06: only S3 list-call errors give 503. |
| AC-8 | Fail page 2 of a listing to get a truncated list returned as 200. | Mitigated by M-07: all pages or 503. |
| AC-9 | Tamper with the build-written version file to inject log content (forged `version`, log splitting). | Mitigated by M-05: strict `^[0-9a-f]{40}$` and a fixed path. The attacker has no write access to the zip without deploy rights. A malformed or unreadable file must degrade to `unknown` and not crash cold start (ARC-002). |
| AC-10 | Make the 503 reach the browser without security headers by building it outside the wrapper. | Mitigated by M-04: single app-wide wrapper. |

## Required mitigations
| ID (M-xx) | Mitigation | SR / named test | Plan step |
|---|---|---|---|
| M-01 | After the 8 s deadline the abandoned worker starts no new attempt or backoff wait; its late result is dropped silently | SR-006; `test_abandoned_worker_makes_no_further_attempts` | To be mapped in the plan |
| M-02 | SDK makes exactly one HTTP attempt per call (`total_max_attempts` 1); one monotonic deadline across pages, attempts and backoff; per-attempt cap by the deadline wait | SR-006; `test_s3_client_config_timeouts_and_retries`, `test_multi_page_listing_shares_one_deadline`, `test_retries_at_most_two` | To be mapped |
| M-03 | No exception text, AWS text, URL or stack trace in the body or log; `cause` from an allow-list | SR-005, SR-024; `test_503_body_and_log_leak_nothing`, `test_dependency_unavailable_log_event` | To be mapped |
| M-04 | The 503 gets its headers only through the single header wrapper | SR-004; `test_503_has_security_headers` | To be mapped |
| M-05 | Log path without query, 256-char cap, JSON-encoded values; `source_ip` only from the platform context; `version` from a fixed-path build file, validated, with `unknown` on any read or format failure | SR-024, SR-025; `test_dependency_unavailable_log_event`, `test_version_from_build_file`, `test_version_unknown_when_missing_or_invalid` | To be mapped |
| M-06 | Only list-call errors and the deadline give 503; other errors stay 500; non-transient errors are not retried; reads only | SR-005, SR-006; `test_non_s3_error_still_500`, `test_non_transient_error_not_retried`, `test_s3_calls_are_reads_only` | To be mapped |
| M-07 | Fail closed: all pages or nothing, no cache or stale fallback | SR-005; `test_partial_listing_failure_returns_503` | To be mapped |
| M-08 | S3 resources released on success, failure and deadline | SR-006; `test_s3_resources_released` | To be mapped |
| M-09 | Deadline 8 s at least 1 s below the Lambda timeout (at most 10 s) | SR-007; `test_function_timeout_exceeds_s3_deadline` | To be mapped |

## Impact on the existing system
- Strengthens SR-006: today the client has botocore defaults (60 s timeouts, SDK retries), which can exceed the 10 s Lambda timeout.
- Adds a `503` path in front of the existing last-resort `500`. It keeps the header wrapper, and `500` handling is unchanged.
- Cost exposure: bounded to at most 3 list calls per request, 8 s per request.
- Build: the zip gains one file (version). This changes `source_code_hash` on every commit, so every build redeploys. That is acceptable and no control is weakened. No IAM, CI or bucket-privacy change.
- Log volume: at most 1 line per failed request. During an S3 outage a flood gives one ERROR line per request within the existing 7-day log group.

## Residual risk
- Reserved concurrency stays the lab exception (SR-007). A flood can still use the shared account concurrency for up to 8 s per request.
- Other error bodies are not yet the SR-005 body, and `error.unhandled` is not logged (SPEC-0002 D-1, unchanged).
- Event `dependency.unavailable` is outside the SR-024 vocabulary (EXC-002).
- The version file is trusted build output. Only the strict hex check and a fixed path protect it. A tampered build already implies code compromise.
- An abandoned worker's in-flight call still runs up to 2 s + 3 s after the 503. This is bounded and has no effect on the response.
