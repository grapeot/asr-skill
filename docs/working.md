# Changelog

## 2026-10-07

- Review fixes landed.

Local verification: `ruff check src tests` passed. `python -m pytest tests/` passed, including the round-2 regressions. The independent rereview repro also passed after these fixes. Acoustic model code was not rerun. `prepare-edit` and `finalize-edit` were rerun on the previous synthetic rich file in a new work directory; the middle-uncertain contract is covered by offline tests, and the earlier fresh smoke remains the acoustic evidence. Validation still records `equivalence_proven` false.
