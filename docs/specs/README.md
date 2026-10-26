# Feature specs

One directory per change: `docs/specs/<id>/`.

| File | Stage | Written by |
|---|---|---|
| `intent.md` | 1 intent | author agent, from the owner's idea and answers |
| `spec.md`, `security-traceability.md`, `threat-model.md` | 2 spec | author agent; traceability by the requirements auditor, threat model by the security architect |
| `plan.md` | 3 plan | author agent |
| `reviews/<reviewer>.json` | every stage | each reviewer: verdict, findings, file hashes |

One PR per stage; the owner's merge is the gate. What each stage produces and how it is evaluated: `docs/pipeline.md` → "Agreed process".
