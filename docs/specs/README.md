# Feature specs

One directory per change: `docs/specs/<id>/`.

| File | Stage | Written by |
|---|---|---|
| `INT-<NNNN>.md` | 1 intent | author agent, from the owner's idea and answers |
| `SPEC-<NNNN>.md`, `TRACE-<NNNN>.md`, `THREAT-<NNNN>.md` | 2 spec | author agent; traceability by the requirements auditor, threat model by the security architect |
| `PLAN-<NNNN>.md` | 3 plan | author agent |
| `reviews/<reviewer>.json` | every stage | each reviewer: verdict, findings, file hashes |

Files carry the change ID (`INT-0001.md`, `SPEC-0001.md`, `TRACE-0001.md`, `THREAT-0001.md`, `PLAN-0001.md`). One feature branch per change; each stage is a PR into it, merged by the session once its checks pass; one final PR to `main`, approved by the owner, when the change is implemented and validated. What each stage produces and how it is evaluated: `docs/pipeline.md` → "Agreed process".
