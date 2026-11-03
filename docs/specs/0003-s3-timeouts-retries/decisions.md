# Decisions for change 0003

| Stage | Decision | Why |
|---|---|---|
| intent | Overall S3 deadline per request is 8 s | Per-attempt limits (3 s connect, 5 s read, 2 retries) allow ~24 s; 8 s keeps a 2 s margin under the 10 s function timeout. Conservative default, not an owner figure. |
| intent | 503 error code is `dependency_unavailable` | SR-005 does not define a code for dependency failure. |
| intent | `request_id` is the Lambda request ID, or a generated UUID if missing | SR-024 allows either; logging is out of scope. |
| intent | No `Retry-After` header | SR-006 does not require it. |
| intent | AUD-001 (malformed breed gives 404 not 422, SR-001) dropped by the auditor in round 2 | Unchanged existing behaviour, out of scope here. |
| intent | A 503 leaves no log record; follow-up suggested | Logging is out of scope (AUD-004). |
