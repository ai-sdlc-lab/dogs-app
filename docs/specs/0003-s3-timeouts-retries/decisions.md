# Decisions for change 0003

| Stage | Decision | Why |
|---|---|---|
| intent | Overall S3 deadline per request is 8 s | Per-attempt limits (3 s connect, 5 s read, 2 retries) allow ~24 s; 8 s keeps a 2 s margin under the 10 s function timeout. Conservative default, not an owner figure. |
| intent | 503 error code is `dependency_unavailable` | SR-005 does not define a code for dependency failure. |
| intent | `request_id` is the Lambda request ID, or a generated UUID if missing | SR-024 allows either; logging is out of scope. |
| intent | No `Retry-After` header | SR-006 does not require it. |
| intent | AUD-001 (malformed breed gives 404 not 422, SR-001) dropped by the auditor in round 2 | Unchanged existing behaviour, out of scope here. |
| intent | A 503 leaves no log record; follow-up suggested | Logging is out of scope (AUD-004). |
| spec | Accepted risk: an S3 failure (503) leaves no log record | Adding an SR-024 dependency-failure event is a separate change; detection route is an operator alarm on Lambda errors and duration (infra, outside this change). Follow-up change suggested. Agent decision, no owner input. |
| spec | Retry mode `standard`; "2 retries" means at most 3 attempts | Pins SR-006's "at most 2 retries" unambiguously (ARC-003). |
| spec | `request_id` is a correlation ID, not a token; no crypto inventory entry | Resolves AUD-004 (SR-021). |
| plan | SPEC-0003 §2 "no new ... file" is read as no new user-facing file or artifact; new source/test modules (`api/app/s3_limits.py`, test files) are intended | Spec stays unchanged (it is merged and reviewed); the deviation is noted in PLAN-0003.md (ARC-007). |
| plan | botocore stays pinned at the existing exact version `botocore==1.43.117`; a test fails loudly if the private internals used go missing | Resolves the private-API risk (ARC-003). |
| spec | Deadline bounds an in-flight attempt, not only new attempts | Slow-drip responses never trip the per-read timeout (ARC-001). |
