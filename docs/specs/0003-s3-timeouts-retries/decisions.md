# Decisions: 0003 S3 timeouts and retries

| # | Stage | Decision | Why |
|---|-------|----------|-----|
| 1 | intent | Per-attempt limits 2 s connect / 3 s read, 8 s overall deadline, backoff 0.2 s doubling (max 1 s) with jitter. | SR-006 gives maxima only; 3 attempts at the maxima exceed the 10 s function timeout (INT-001, AUD-001). |
| 2 | intent | No frontend change for 503. | Out of scope for SR-006 gap; the author's open question resolved conservatively. |
| 3 | intent | New log event `dependency.unavailable` (ERROR). Exception EXC-002 (approved_by: agent) for AUD-002 (info): not in the SR-024 vocabulary, baseline not editable here. | Handled failure must not reuse `error.unhandled`; unresolved after round 3. |
