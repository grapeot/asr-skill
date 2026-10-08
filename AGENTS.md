# AGENTS.md

## Status

This repository is a scaffold. `asr_skill.IMPLEMENTED` is false. Do not tell a user that diarization, transcription, alignment, cleaning, model download, or a smoke test works. `asr-skill version` and `asr-skill doctor` only report that fact. Planned commands exit 3 with `not_implemented`.

## Layout

- `src/asr_skill/`: importable package. No speech-model imports.
- `scripts/asr-skill`: launcher. It prefers `.venv/bin/python`, then `python3`.
- `skills/asr/SKILL.md`: the only skill to expose in a workspace index.
- `docs/`: requirements, design, tests, and the working log.
- `examples/synthetic/`: Alice and Bob fixtures. They are not pipeline output.
- `tests/`: offline import, contract, and hygiene checks.

## Environment

Python 3.12 or newer. Before Python work, check for `.venv`. If it is missing, create it with `uv venv`. If it exists, activate it. Install with `uv pip install -e '.[dev]'`, not `pip install`.

The default install has no PyTorch, Transformers, or MLX dependency. Do not add those to the default dependency list. Ubuntu CI must import the package without them.

## Working log

After a substantive change, add one dated bullet under `docs/working.md` Changelog. Record the command you actually ran and its result. Do not write a pass you did not run. Real pitfalls go under Lessons Learned. Do not invent them.

## Git

Default branch is `master`. Commit only when the user asks. Do not commit `.env`, recordings, logs, model weights, caches, or virtualenvs.

## Compatibility

Later, this library is the only implementation of diarization, alignment, and the cleaning contract. Private daily jobs keep thin wrappers outside this repository. Do not copy those jobs or their recordings into this tree. Do not maintain a second copy of the pipeline here.

## Public text

English only in docs, skills, tests, and examples. Examples use Alice and Bob only. Paths in docs are `/path/to/...`.
