# asr-skill

asr-skill is a scaffold for local speaker-attributed transcription. The intended pipeline keeps audio on the machine and writes structured, traceable transcripts. That pipeline is not implemented in this build. The design keeps diarization, speech recognition, and semantic text editing as separate phases, joined by fixed data contracts and sidecars.

## Current Project Status

The repository is currently an initial scaffold. The transcription and diarization pipeline is not implemented. Acoustic diarization, speech recognition, timestamp alignment, semantic cleaning, automatic model downloading, and synthetic audio smoke tests are not implemented. The package imports as a standard Python module, but its operational functionality is limited to reporting its current scaffold state.

Today, the working surface of the repository consists strictly of the package import and two informational CLI subcommands:

```
asr-skill version
asr-skill doctor
```

These entry points can also be invoked as `python -m asr_skill version` or through the standalone shell wrapper `scripts/asr-skill version`. Running the version command emits a single diagnostic line:

```
asr-skill 0.0.0 phase=scaffold implemented=false
```

Running the doctor command outputs a JSON object documenting the current execution readiness without calling ffmpeg, invoking any machine learning model, or making network requests:

```json
{
  "command": "doctor",
  "phase": "scaffold",
  "implemented": false,
  "models_ready": false,
  "network": false
}
```

All other planned subcommands (`init`, `diarize`, `align`, `clean`, `run`, and `smoke`) are defined as command stubs that immediately terminate with exit code 3 and return a JSON error payload:

```json
{
  "error": "not_implemented"
}
```

Neither the CLI nor any internal script will attempt to process audio or claim that transcripts can be generated in this phase.

## Future Installation Workflow

The intended public repository will be hosted at `https://github.com/grapeot/asr-skill` on branch `master`. That remote repository has not been published yet, and cloning from GitHub is not supported today. The project is released under the MIT license, with package name `asr-skill` and Python import name `asr_skill`. It requires Python 3.12 or newer.

The core package does not include PyTorch, Transformers, or Apple MLX as default dependencies. This design ensures that the base package can be quickly installed and imported in lightweight continuous integration environments, such as standard Ubuntu CI runners, without requiring GPU drivers or large binary wheels.

Package management relies exclusively on `uv`. Standard `pip install` commands must not be used. If the virtual environment does not exist, initialize it with `uv venv`. If `.venv` already exists, activate it, then install the package in editable mode with development dependencies:

```bash
uv pip install -e '.[dev]'
```

In future phases, installation by automated coding agents (such as Codex, Claude Code, Cursor, or OpenCode) will follow a structured onboarding protocol. When directed to the repository URL, an agent inspects the target workspace documentation (`AGENTS.md` or `CLAUDE.md`) and any existing index file (`rules/skills/INDEX.md` or `skills/INDEX.md`). The agent exposes exactly one root skill: `skills/asr/SKILL.md`. If an index file is present, the agent registers the skill path there; otherwise, it appends a concise reference inside `AGENTS.md` or `CLAUDE.md`. The installer avoids creating symlinks into global user skill directories. The installer then configures the local uv environment, verifies that `ffmpeg` is available on the system PATH, and documents the two specialized model runtimes. This installation process is fully reproducible and vendor neutral.

## Model Runtime Architecture

The planned processing pipeline relies on two separate execution environments, which are intentionally decoupled from the core Python package:

1. Diarization Runtime: Speaker diarization is assigned to `nvidia/Nemotron-3-Diarization` running on CPU within its own isolated Python environment. This environment requires a specialized build of the transformers library capable of audio frame classification. The exact package versions will be captured in a local, uncommitted manifest during the future environment initialization step.
2. Speech Recognition Runtime: ASR is assigned to `Qwen/Qwen3-ASR-1.7B` executing via MLX on Apple Silicon within a separate isolated environment. MLX does not support Linux environments, and its absence on an Ubuntu CI runner does not constitute an installation failure for the core package.

Model weights are never bundled into the git tree and are never downloaded automatically upon package installation. Downloads will occur only when a user explicitly initiates an initialization command. Weights are stored strictly in the standard Hugging Face cache directory or a user-defined `HF_HOME`. Recordings, model weights, and local environment files stay on the machine. This package does not upload them.

## Environment Configuration

The CLI and pipeline tools are configured through environment variables. The package reads no proprietary LLM API credentials and performs no remote API authentication. The following placeholders define the primary operational directories and runtime paths:

```bash
export ASR_SKILL_RECORDINGS_DIR="/path/to/recordings"
export ASR_SKILL_WORK_DIR="/path/to/asr-work"
export ASR_SKILL_DIAR_PYTHON="/path/to/diarization-venv/bin/python"
export ASR_SKILL_ASR_PYTHON="/path/to/asr-venv/bin/python"
export HF_HOME="/path/to/huggingface-cache"
```

In all documentation and configuration templates, input paths are represented with explicit `/path/to/...` placeholders rather than user home directories or hardcoded machine paths.

## Illustrative Synthetic Fixtures

The repository includes a set of synthetic test fixtures located in `examples/synthetic/`:

- `alice_bob_rich.jsonl`: Canonical rich segment records containing timestamps and acoustic labels.
- `alice_bob_raw.csv`: Raw transcript containing speaker identifiers and verbatim recognized text.
- `alice_bob_readable.csv`: Cleaned, readable transcript formatted with speaker names.
- `alice_bob_name_map.json`: Mapping table resolving acoustic labels to validated display names.
- `alice_bob_source_map.json`: Deterministic audit record mapping output rows back to rich segment identifiers.

These fixtures demonstrate the intended data contracts for multi-speaker dialogues featuring speakers Alice and Bob. In this example, a third acoustic speaker label remains unresolved as `unknown` and is documented as deleted filler within the source map. The number 3 and the negation token "not" are explicitly preserved across both the raw CSV and readable CSV files. These fixture files serve solely as illustrative examples of the required schema contracts; they were not generated by the CLI.
