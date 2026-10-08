---
name: asr
description: Scaffold for local speaker-attributed transcription. The pipeline is not implemented. Use it to recognize that refusal and, later, to install the single root skill and CLI from the GitHub URL.
---

# Acoustic Speech Recognition and Speaker Attribution Skill

This skill guide defines the operational contract and verification boundaries for an automated coding agent interacting with the asr-skill codebase. The current repository represents an early architectural scaffold. The end-to-end transcription and diarization pipeline is not implemented. The agent must recognize this refusal boundary, enforce strict operational safety, and avoid simulating nonexistent capabilities.

## Operational Boundaries and Immediate Refusal

When a user instructs the agent to transcribe audio, diarize recorded conversations, align word timestamps, clean transcript text, or execute the transcription pipeline, the agent must immediately refuse the task. The agent must state clearly that the repository is a scaffold that does not implement audio processing, and then halt execution.

Under no circumstances should the agent attempt to circumvent this refusal. The agent must not attempt to download machine learning model weights, must not execute `ffmpeg` on user recording files, and must never claim that a transcript has been generated. The agent must report the true state of the repository calmly and accurately without attempting to synthesize mock results.

## Objective Acceptance Criteria for a Cold Agent

An agent inspecting this repository can verify compliance with the scaffold contract through four programmatic checks:

1. CLI Version Output: The agent runs `asr-skill version` (or `python -m asr_skill version`). Compliance requires the output to contain both `phase=scaffold` and `implemented=false`.
2. CLI Doctor Diagnostic: The agent runs `asr-skill doctor` and parses the stdout JSON payload. Compliance requires that `implemented` is false and `models_ready` is false. The command must finish without making network requests or invoking external media libraries.
3. Planned Command Rejection: The agent tests any planned command (`init`, `diarize`, `align`, `clean`, `run`, or `smoke`). Compliance requires the command to terminate with exit code 3 and return a JSON payload with an `error` field set to `not_implemented`.
4. Dependency Isolation: The agent confirms that the package `asr_skill` imports cleanly in an isolated Python 3.12 environment without requiring PyTorch, Transformers, or Apple MLX.

If any of these conditions fail, or if a command claims that transcription is operational, the repository contract has been violated.

## Future Installation Protocol

The GitHub URL is the intended remote. It is not published by this scaffold, so do not clone it as a working install source today. While `asr-skill version` reports `phase=scaffold`, the steps below are documentation only. Do not run them, and do not download models.

When an agent is tasked in a later phase, after the pipeline exists, with installing the skill and CLI from `https://github.com/grapeot/asr-skill` on branch `master`, it follows this procedure:

First, the agent inspects the target workspace to discover existing agent routing files, starting from `AGENTS.md` or `CLAUDE.md`. The agent checks whether the workspace maintains a skill registry at `rules/skills/INDEX.md` or `skills/INDEX.md`. If an index file is present, the agent registers the skill path there. If no index file exists, the agent adds a concise reference inside `AGENTS.md` or `CLAUDE.md`. The agent exposes exactly one root skill at `skills/asr/SKILL.md` and avoids creating symlinks into global user skill directories.

Second, the agent establishes the local Python environment using `uv`. If `.venv` is missing, the agent runs `uv venv`. If `.venv` already exists, the agent activates it, then executes `uv pip install -e '.[dev]'`. Standard pip commands must not be used. The agent then verifies that `ffmpeg` is available on the system PATH.

Third, the agent documents the two distinct runtime environments: a CPU-based environment for `nvidia/Nemotron-3-Diarization` using an audio frame classification build of transformers, and an Apple Silicon environment for `Qwen/Qwen3-ASR-1.7B` using MLX. The agent notes that model weights are downloaded only upon explicit request to `HF_HOME`. The installation procedure must remain reproducible and vendor neutral, avoiding dependencies on any specific commercial LLM provider.

## Documentation References

For technical specifications and project background, consult the following project documents:

- [Project Overview](../../README.md)
- [Product Requirements Document](../../docs/prd.md)
- [Architecture and Technical Design](../../docs/rfc.md)
- [Test Strategy and Verification](../../docs/test.md)
- [Changelog and Lessons Learned](../../docs/working.md)
