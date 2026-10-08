# Changelog

## 2026-10-07

- This scaffold was created and models were not run.
- Docs were checked against the CLI: planned commands are specified, not shipped.

Local verification: `ruff check .` passed. `python -m pytest tests/ -q` passed, 13 tests. `asr-skill version` printed `phase=scaffold implemented=false`. `asr-skill doctor` printed `implemented` false. `asr-skill diarize` exited 3. Models were not run.

## Lessons Learned

- Do not describe the scaffold as a working transcriber.
- Do not add PyTorch or MLX to the default dependencies.
- Do not clean with a filler expression or assign speakers by keyword.
- Do not commit audio, logs, weights, or environment files.
- Compatibility wrappers are later and do not live in this repository.
