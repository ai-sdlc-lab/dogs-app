# THREAT-0004: Invalid input returns 422 and is logged as `input.rejected`

## 1. Change summary
The only external input is the `breed` path segment of `GET /api/dogs/{breed}`. `GET /api/dogs` and `GET /api/health` take no input. The change adds or modifies:
- A `422` with the fixed body `{"error":"invalid_input","request_id":"<id>"}` for invalid input. The framework default 422 body is replaced.
- A whole-value breed match, which closes the trailing-newline hole (`pug%0A`). The same match is applied to the breed segment of S3 listing keys.
- One `input.rejected` JSON line per rejected request on stdout. It goes to the existing Lambda CloudWatch log group (7-day retention, AWS-managed encryption). Fields include `source_ip`, `http.path` (up to 200 characters), `service` and `version`.
- A fallback request ID of 32 hex characters (128 random bits from a CSPRNG). It replaces UUID v4 and also affects the `503` path.
- A build step that embeds the git SHA in the Lambda zip (`version`).

No new AWS service, IAM permission, identity, CI permission, dependency or route is added.

## 2. Trust boundaries and data flows
- Browser or attacker -> Lambda function URL (public, untrusted) -> FastAPI validation. The next hop is either S3, reached only after validation passes with the fixed `dogs/` prefix plus the validated breed, or the 422 response.
- Lambda -> stdout -> CloudWatch Logs (7 days). The logged path is attacker-written text. Operators and possibly AI agents read it later (SR-031: data, not instructions).
- The Lambda platform context (request ID, source IP) is trusted. Headers and the query string are untrusted: `X-Forwarded-For`, `X-Request-Id` and the others are never used.
- S3 listing keys cross a boundary back into the process. They are re-checked with the same whole-value rule before a presigned URL is made.
- Build -> Lambda zip carries the git SHA. This is not attacker-controlled.

## 3. STRIDE per element
| Element | S | T | R | I | D | E |
|---|---|---|---|---|---|---|
| Breed path input to the validator | n/a (anonymous API) | Mitigated: whole-value match, UTF-8, control characters out of set (M-01) | Mitigated: `input.rejected` event (M-03, M-06, M-07) | Mitigated: fixed body, no echo (M-04) | Residual: invalid-request flood raises log ingestion cost (see ARC-001; M-09 means no S3 work) | n/a (no roles) |
| S3 listing keys | n/a | Mitigated: same whole-value match (M-02) | n/a | Mitigated: no presigned URL for a bad key (M-02) | n/a | n/a |
| 422 response | n/a | n/a | n/a | Mitigated: two fixed keys, no request data, SR-004 headers (M-04, M-10) | n/a | n/a |
| Log pipeline (stdout -> CloudWatch) | Mitigated: IP from context only, never from `X-Forwarded-For` (M-06) | Mitigated: JSON encoder, one line per event, 200-character cap, no query string (M-03, M-07) | Mitigated: log `request_id` equals the body ID (M-05); failure to write cannot change the response (M-08) | Mitigated: never-logged list (headers, body, query, exception text) (M-07) | Residual: ingestion cost, no alarm (ARC-001) | n/a |
| Request ID generation | Mitigated: never from a header or query value (M-05) | n/a | n/a | Mitigated: 128-bit CSPRNG ID is unguessable (M-05) | n/a | n/a |
| Build info / `version` | n/a | Mitigated: SHA embedded at build and tested (M-11) | Mitigated: lets events be traced to a build (M-11) | n/a | n/a | n/a |

## 4. Abuse cases
1. Send `pug%0A`, `pu%00g`, `%FF`, `h%C3%BCnd`, `pug%22` or `%2e%2e` to bypass the regex or reach S3 with a crafted prefix. Mitigated by M-01 and M-09.
2. Plant an S3 key whose breed segment ends in a newline so a presigned URL is made for it. Mitigated by M-02.
3. Put newlines, quotes or fake JSON in the path to forge or split log entries. Mitigated by M-03.
4. Put instructions for an AI agent in the path, which is logged. Mitigated by SPEC 7.3b (SR-031). Readers treat the path as data.
5. Send a spoofed `X-Forwarded-For` or `X-Request-Id` to poison the log or the request ID. Mitigated by M-05 and M-06.
6. Send a huge path or query string to grow log lines. Mitigated by the 200-character cap and by no query string in the line (M-03, M-07).
7. Trigger a framework validation error to leak the submitted value or field name through the default 422 body. Mitigated by M-04.
8. Make the log write fail (for example an oversized or odd value) to force a stack trace or a 500 in the response. Mitigated by M-08.
9. Flood invalid requests to raise CloudWatch ingestion cost. The spec bounds it (200-character cap, account concurrency 10, about 5.4 GB per hour worst case) but adds no alarm. See ARC-001. Alarm: #38.
10. Send hostile paths that match no route (`a%2Fb`, empty breed) so they leave no log line. Accepted: they keep the unchanged `404` with no S3 access.
11. Send an invalid breed while S3 is failing, to turn a client error into a `503` or a dependency call. Mitigated by M-09.
12. Read the `version` or `service` fields to learn about the build. They appear only in the log, not in responses, so there is no exposure.

## 5. Required mitigations
Tests are in `api/tests/test_invalid_input.py` unless stated. Plan steps do not exist yet (spec stage). Each row must be mapped to a PLAN-0004 task at the plan stage. An unmapped row is a finding there.

| ID | Mitigation | SR | Named test(s) | Plan step |
|---|---|---|---|---|
| M-01 | Breed rule is a whole-value match. `pug%0A`, `pu%00g`, `%FF` and 41 characters are rejected. Boundaries (`a`, 40 characters, `a-1`) are accepted. | SR-001 | `test_dogs_by_breed_rejects_malformed_breed`, `test_dogs_by_breed_accepts_boundary_breeds` | PLAN-0004: validator task (to be mapped) |
| M-02 | The re-check of returned S3 keys uses the same whole-value match. A key with a newline-suffixed breed is skipped. | SR-002 | `test_listing_skips_key_with_trailing_newline` (`api/tests/test_api.py`) | PLAN-0004: listing re-check task (to be mapped) |
| M-03 | One JSON object per line from the JSON encoder. Path capped at 200 characters, no query string. A hostile path parses back exactly. | SR-024 | `test_rejected_log_is_single_line_json_for_hostile_path`, `test_rejected_log_path_truncated_to_200`, `test_rejected_log_path_has_no_query_string` | PLAN-0004: logging task (to be mapped) |
| M-04 | The 422 body has exactly two fixed keys. It never holds the submitted value, field names, `detail` or exception text. The framework default 422 is never sent. | SR-005, SR-003 | `test_rejected_body_has_no_request_data`, `test_framework_validation_error_uses_invalid_input_body` | PLAN-0004: error-handler task (to be mapped) |
| M-05 | Request ID comes from the Lambda context, else 32 lowercase hex characters (128 random bits, CSPRNG). Never from a header or query value. The log ID equals the body ID. | SR-005, SR-021 | `test_rejected_request_id_from_lambda_context`, `test_rejected_request_id_generated_when_missing`, `test_generated_request_id_is_128_bit_hex`, `test_rejected_request_id_ignores_request_headers`, `test_rejected_log_request_id_matches_body`, updated `test_503_request_id_generated_when_missing` | PLAN-0004: request-ID task (to be mapped) |
| M-06 | `source_ip` comes from the platform context, never from `X-Forwarded-For`. It is `unknown` when absent. | SR-024 | `test_rejected_log_source_ip_from_context_not_xff` | PLAN-0004: logging task (to be mapped) |
| M-07 | Query strings and headers are never logged. The path is length-capped. Only the SPEC 7.2 fields are logged. | SR-024, SR-025 | `test_rejected_logs_input_rejected_event` (exact key set), `test_valid_requests_write_no_input_rejected` | PLAN-0004: logging task (to be mapped) |
| M-08 | A log-write failure cannot change the 422 body, status or headers and cannot put a trace in the response. | SR-005 | `test_rejected_still_422_when_log_write_fails` | PLAN-0004: logging task (to be mapped) |
| M-09 | No S3 call for a rejected breed, even when S3 is failing. | SR-001, SR-006 | `test_dogs_by_breed_rejects_without_s3_call` (`api/tests/test_s3_503.py`) | PLAN-0004: validator task (to be mapped) |
| M-10 | The 422 carries the exact SR-004 headers, including `Content-Type: application/json; charset=utf-8`. | SR-004 | `test_security_headers` (422 case, `api/tests/test_headers.py`) | PLAN-0004: error-handler task (to be mapped) |
| M-11 | `version` is the git SHA of the build. The Lambda zip contains the build info and the event carries it. It is `unknown` only when there is no build info. | SR-024 | `test_build_zip_contains_build_info`, `test_rejected_log_version_from_build_info` | PLAN-0004: build / Makefile task (to be mapped) |
| M-12 (added) | Ingestion-cost bound for floods: path cap, account concurrency 10, worst case quantified. The alarm or budget alert stays with #38. | NEW (cost; SR-007 for concurrency) | None for the alarm (deferred). The cap is covered by `test_rejected_log_path_truncated_to_200`. | None. See ARC-001. |

## 6. Impact on the existing system
- Existing controls are not weakened. Bucket privacy, IAM, CI permissions and the lab BASELINE are untouched. The Lambda role still cannot read or delete logs.
- The attack surface does not grow. There is no new route, input, identity, permission or dependency. The whole-value match narrows the accepted input (it closes `pug%0A`).
- Cost exposure grows by one log event per rejected request. The spec gives a worst-case bound of about 5.4 GB per hour, but there is no alarm or budget alert until #38.
- The fallback request ID format changes from UUID v4 to 32 hex. The existing `503` test is updated. Clients should not depend on the format.
- The 422 body replaces the framework default. The web app gets a different status for malformed breeds and has no change.
- The source IP is now stored for 7 days, which is personal data under many regimes. It is justified in SPEC section 6 (SR-025, SR-024 lab exception).
- Known gap, unchanged: the `404` and `500` bodies are not the SR-005 body. They stay with #30.
