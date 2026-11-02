# Decisions: 0003 S3 timeouts and retries

| # | Stage | Decision | Why |
|---|-------|----------|-----|
| 1 | intent | Per-attempt limits 2 s connect / 3 s read, 8 s overall deadline, backoff 0.2 s doubling (max 1 s) with jitter. | SR-006 gives maxima only; 3 attempts at the maxima exceed the 10 s function timeout (INT-001, AUD-001). |
| 2 | intent | No frontend change for 503. | Out of scope for SR-006 gap; the author's open question resolved conservatively. |
| 3 | intent | New log event `dependency.unavailable` (ERROR). Exception EXC-002 (approved_by: agent) for AUD-002 (info): not in the SR-024 vocabulary, baseline not editable here. | Handled failure must not reuse `error.unhandled`; unresolved after round 3. |
| 4 | spec | `version` log field = commit SHA that `make build` writes into a file in the Lambda zip; `unknown` if absent or invalid. | SR-024 requires the SHA (AUD-007, high); this needs no infra/CI change. |
| 5 | spec | Exception EXC-003 (approved_by: agent) for ARC-002 (low): fixed path, 64-byte read cap and unreadable-file cases for the version file not in the spec after round 3. | Code stage must implement them (fixed path, small cap, `unknown` on any error). |
| 6 | spec | Deferred old debt, not fixed here: SR-005 other error bodies/`error.unhandled` (AUD-001), SR-022 S3 TLS-version policy (AUD-002), other mandatory SR-024 events (AUD-003). | Existing gaps on `main` in code this change doesn't alter; `report` files the issues. |
| 7 | spec | Retryable S3 errors: connect/read timeouts, connection errors, 5xx, SlowDown, RequestTimeout; 4xx like AccessDenied/NoSuchBucket give 503 without retry. Hanging-stub test runs on a controllable clock. | Conservative defaults chosen by the session; owner not asked after intent. |
