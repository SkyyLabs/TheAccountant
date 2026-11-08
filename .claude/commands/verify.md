---
description: Run the TheAccountant verification suite and report pass/fail per step
---

Run `make verify` and report pass/fail per step. The step list lives only in the `Makefile` `verify` target — do not restate it here or elsewhere. (The Makefile arrives in M1; before that, say there is nothing to verify.)

```bash
make verify
```

On failure, quote the shortest decisive line, not the whole log. This suite is read-only and build-only: it never touches `data/accountant.db` and never calls a real LLM (tests use the mock provider).
