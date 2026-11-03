# THREAT-0003: threat model

## Scope and change summary

Change 0003 adds timeouts, bounded retries and a per-request overall deadline to the S3 calls behind `GET /api/dogs` and `GET /api/dogs/{breed}`. When S3 fails, those endpoints return a fixed `503` body. Today `api/app/main.py` builds a cached boto3 client (`@cache def s3()`) with no timeouts and the default retry policy. `list_dogs` runs a paginated `list_objects_v2` and signs presigned URLs locally. A hung or failing S3 therefore runs the Lambda to its 10 s timeout and surfaces as an unformatted 500 or a gateway error.

The change adds no endpoint, identity, IAM permission, data store, dependency or CI permission. It adds failure-path behaviour only: client timeouts, standard retry mode with 3 attempts, an 8 s per-request deadline that also bounds a running attempt, and a `503` with `{"error": "dependency_unavailable", "request_id": "<id>"}`. It adds no logging (accepted risk).

Round 3: ARC-005 (per-request deadline state) and ARC-006 (abandoned attempt releases resources) are closed. SPEC-0003 section 1.3 now says deadline and attempt state are never kept in the cached client or in shared state. It also says an abandoned attempt closes its connection and leaves no worker running. Section 10 maps these to M-09 and M-10 and to named tests.

## Assets

- Availability of the public API. The Lambda has a 10 s timeout and a shared account concurrency pool, so slow requests also cost money and capacity.
- Privacy of the S3 bucket. Internal detail (bucket name, keys, host, library and exception text) must not leak in errors.
- Integrity of responses. There must be no partial or stale list served as success.
- Correctness of the shared warm client. One request's failure must not affect another's.

## Trust boundaries and data flows
| # | From → To | Data | Crosses boundary |
|---|---|---|---|
| 1 | Browser or anonymous caller → Function URL / Lambda (FastAPI) | GET path, breed segment, headers | Yes (internet to compute) |
| 2 | Lambda → S3 regional endpoint (HTTPS) | ListObjectsV2 request, signed with the execution role | Yes (compute to AWS service) |
| 3 | S3 → Lambda | Listing pages, error responses, slow or hung bytes | Yes (the response is untrusted for timing and content) |
| 4 | Lambda → browser | 200 list with presigned URLs; 503 fixed body | Yes |
| 5 | Lambda runtime → handler | Lambda request ID, used as `request_id` | Internal |

There is no AI agent reading user content in this change.

## STRIDE per element
| Element | S | T | R | I | D | E | Notes |
|---|---|---|---|---|---|---|---|
| Public endpoints (flow 1) | N/A (anonymous by design) | N/A | Accepted: no log of a 503 (M-08) | Mitigated: fixed body, no echo (M-05) | Mitigated: deadline and limits (M-01, M-02, M-04) | N/A (no new permission) | The breed pattern and 404 are unchanged. |
| Lambda to S3 client (flow 2, 3) | N/A | N/A | Accepted (M-08) | Mitigated: the error classifier returns a generic body (M-03, M-05) | Mitigated: bounded attempts, deadline, per-request state, resource release (M-01, M-02, M-04, M-09, M-10) | N/A | The HTTPS endpoint and certificate validation are unchanged (SR-022). |
| Warm cached client and deadline state | N/A | Mitigated: no shared mutable deadline (M-09) | N/A | Mitigated: no cross-request state (M-09) | Mitigated: an abandoned attempt cannot poison later requests (M-09, M-10) | N/A | |
| 503 response (flow 4) | N/A | Mitigated: no fallback or partial data (M-07) | N/A | Mitigated (M-05) | N/A | N/A | The SR-004 headers come from the existing header layer (M-06). |
| `/api/health` | N/A | N/A | N/A | N/A | Mitigated: makes no S3 call (M-07) | N/A | |
| Error classifier | N/A | Mitigated: S3-library exceptions only; `HTTPException` and programming errors pass through (M-03) | N/A | Mitigated (M-03, M-05) | N/A | N/A | |

## Abuse cases
| ID | Attacker goal and steps | Impact |
|---|---|---|
| AC-1 | Exhaust Lambda time and cost. Repeatedly call `/api/dogs` while S3 is slow or hung, so each invocation runs to the 10 s timeout and retries stack (about 24 s of attempts). | Concurrency and cost exhaustion. Mitigated by the 8 s deadline, shrinking attempt timeouts and a capped backoff (M-01, M-02, M-04). |
| AC-2 | Slow-drip response. A degraded S3, or a network fault, sends one byte every 4 s so the read timeout never fires. | The request hangs to the function timeout. Mitigated by the deadline bounding the running attempt (M-01). |
| AC-3 | Information leak through errors. Provoke an S3 error (access denied, a malformed key) to read the bucket name, key, host or library text from the response. | Disclosure of infrastructure detail. Mitigated by the fixed body, classification and tests with marker strings (M-03, M-05). |
| AC-4 | Header or ID injection. Send an `X-Request-Id` or a crafted path to have it reflected in the 503. | Reflection or log forging. Mitigated: `request_id` comes only from the Lambda context or a CSPRNG UUID (M-05). |
| AC-5 | Mask a 404 as a 503, or the reverse. Request a malformed or empty breed during an S3 outage. | Wrong semantics, or an S3 call on invalid input. Mitigated (M-03). |
| AC-6 | Serve partial data. Fail the second listing page so a truncated list is returned as 200. | Integrity loss. Mitigated by failing the whole request (M-07). |
| AC-7 | Cross-request poisoning. A slow first request leaves an expired shared deadline or an abandoned attempt on the warm client, so the next request fails immediately or leaks a connection. | A persistent self-inflicted denial of service across warm invocations. Mitigated (M-09, M-10). |
| AC-8 | Hide an outage. Cause S3 failures that leave no log record. | Late detection. Accepted risk, with an alarm on Lambda duration as the detection route (M-08). |

## Required mitigations
| ID (M-xx) | Mitigation | SR / named test | Plan step |
|---|---|---|---|
| M-01 | The 8 s overall deadline bounds a running attempt, including a slow-drip response. | SR-006; `test_s3_slow_drip_returns_503_before_function_timeout`, `test_s3_hang_returns_503_before_function_timeout`, `test_s3_overall_deadline_is_8s` | PLAN-0003 (to be mapped at the plan stage) |
| M-02 | Attempt timeouts shrink to the time left, backoff is cut at 8 s, and no attempt starts at or after 8 s. | SR-006; `test_attempt_started_near_deadline_is_bounded`, `test_backoff_does_not_exceed_deadline`, `test_no_retry_after_deadline` | PLAN-0003 |
| M-03 | Classify by exception type: only S3-client failures become 503. `HTTPException`, a missing `DOGS_BUCKET` and programming errors keep today's behaviour. | SR-005, SR-006; `test_s3_error_response_returns_503`, `test_s3_connection_error_returns_503`, `test_s3_other_client_error_returns_503`, `test_non_s3_error_not_503`, `test_missing_bucket_setting_unchanged`, `test_malformed_breed_404_without_s3_call`, `test_empty_breed_404_passthrough`, `test_dogs_by_breed_s3_failure_returns_503` | PLAN-0003 |
| M-04 | The real client is configured with connect 3 s, read 5 s, standard retry mode and 3 total attempts, checked on the real client. | SR-006; `test_s3_client_timeouts_configured`, `test_s3_client_retries_configured`, `test_at_most_three_attempts` | PLAN-0003 |
| M-05 | Fixed 503 body. `request_id` is the Lambda request ID or else a CSPRNG UUIDv4, with no request data echoed and no `Retry-After`. | SR-005; `test_dogs_s3_failure_returns_503`, `test_s3_failure_body_has_no_detail`, `test_503_request_id_from_lambda_context`, `test_503_request_id_generated_when_missing`, `test_503_ignores_request_id_header`, `test_503_has_no_retry_after` | PLAN-0003 |
| M-06 | The 503 carries the SR-004 headers. | SR-004; `test_503_has_security_headers` | PLAN-0003 |
| M-07 | No fallback, partial list or cache. `/api/health` stays free of S3. | SR-006; `test_s3_failure_midway_returns_503`, `test_health_ok_when_s3_failing`, `test_healthy_s3_responses_unchanged` | PLAN-0003 |
| M-08 | Accepted risk: S3 failures are not logged. Detection is an operator alarm on Lambda duration. It is documented in SPEC section 7 and `decisions.md`. | SR-024 (deferred); no test, by decision | Not applicable (documentation) |
| M-09 | Deadline and attempt state are per request, never in the cached client, a module global or shared state. | SR-006; `test_deadline_is_per_request` (sequential and concurrent) | PLAN-0003 |
| M-10 | An attempt abandoned at the deadline closes its connection and leaves no worker running, and the warm client serves the next request normally. | SR-006; `test_abandoned_attempt_releases_resources` | PLAN-0003 |

The plan-step column is filled at the plan stage. Each M-xx must map to a PLAN task there.

## Impact on the existing system

- No existing control is weakened. There is no IAM, bucket-privacy, CI or infra change. The bucket stays private and presigned URLs are unchanged. The SR-004 header layer is reused.
- The attack surface does not widen: no new entry point or parameter.
- Cost exposure drops: a failing S3 can no longer hold an invocation for the full 10 s. Retries stay at 3 attempts or fewer per request.
- One cached `boto3` client stays shared across warm invocations. Its configuration (timeouts, retries) is the only change to it, and per-request state is kept out of it (M-09).
- Observability does not improve: a 503 leaves no log (M-08). Gaps D-1 and D-9 of change 0002 are handled as stated in the spec (D-9 closed, D-1 still open).

## Residual risk

- Low: S3 outages are not logged (M-08, accepted). Detection depends on an operator alarm that is outside this change and not yet confirmed by the owner.
- Low: the design requires an in-flight attempt to be abandoned and its resources released, but a synchronous boto3 call cannot be forcibly cancelled from outside. Implementation feasibility is bound only by tests M-01, M-09 and M-10. The code stage should confirm the approach (for example, a deadline-aware transport or per-attempt timeouts that shrink to the time left) and update the plan if it departs from the spec.
- Info: the 8 s deadline and the backoff timing are agent defaults, not owner figures.
