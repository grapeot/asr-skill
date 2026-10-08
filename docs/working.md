# Changelog

## 2026-10-07

- Review fixes landed.

Local verification: `ruff check src tests` passed. `python -m pytest tests/` passed, including the round-2 regressions. The independent rereview repro also passed after these fixes. Acoustic model code was not rerun. `prepare-edit` and `finalize-edit` were rerun on the previous synthetic rich file in a new work directory; the middle-uncertain contract is covered by offline tests, and the earlier fresh smoke remains the acoustic evidence. Validation still records `equivalence_proven` false.

## 0.1.1

Version 0.1.1 adds two direct timestamp dependencies from the mlx-qwen3-asr 0.4.4 aligner extra: nagisa 0.3.0 and soynlp 0.0.493. asr-skill init installs them from requirements/asr.txt. doctor and doctor --no-load refuse a missing or different version. A missing tokenizer is a failure. The package does not switch models, drop a language, or use another tokenizer. A failed diarization or alignment batch still records a checkpoint when that checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. The stage is failed. A partial batch does not replace the combined output or mark it current. The next run sends only files that failed or have no verified checkpoint. A changed input or parameter hash is not reused. The alignment parameter hash now includes the tokenizer pins, so an older alignment checkpoint is not reused. The diarization parameter hash is unchanged. The acoustic algorithm for a successful file is unchanged.
