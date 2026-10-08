# Product Requirements Document: asr-skill

## Overview and Purpose

The asr-skill project specifies a modular, local-first system for speaker-attributed speech transcription. The intended system converts multi-speaker audio into structured, auditable text. Audio processing, diarization, recognition, and file writes stay on the machine. None of that processing is implemented in this scaffold.

This document specifies user personas, current operational limitations, phased requirements, success criteria, and non-goals.

## Users and Target Personas

The system serves three primary groups:

1. Software Engineers and Researchers: Technical users who record discussions, interviews, and voice memos on workstations. These users require speaker labels tied to the original recording timeline, local processing, predictable execution, and control over the model environments.
2. Autonomous Coding Agents: Tool-using software agents (including Codex, Claude Code, Cursor, and OpenCode) that inspect repositories, install command-line tools, configure workspace skills, and verify operational boundaries. These agents require unambiguous operational contracts, structured exit codes, machine-readable diagnostics, and deterministic installation steps independent of any specific LLM vendor.
3. Downstream Automation Pipelines: Existing external scheduled jobs and daily processing scripts that consume transcript data. These consumers depend on fixed column contracts and backward-compatible flag semantics.

## Problem Statement

Automated transcription tools commonly suffer from three core limitations:

Cloud-based transcription APIs introduce privacy risks for proprietary discussions or personal audio. Local alternatives often bundle diarization, speech recognition, and text cleaning into monolithic scripts that cannot be isolated or tested independently.

Second, existing local pipelines introduce silent data corruption. Heuristic text cleaners strip filler words with regular expressions, accidentally removing negative qualifiers, conditions, or numbers. Tools frequently merge speaker labels based on speculative keyword matching, destroying speaker boundaries. When audio is cut and concatenated prior to diarization, the true temporal timeline is corrupted.

Third, deep learning libraries such as PyTorch, Transformers, and MLX introduce massive binary dependencies that conflict with system packages. Forcing these libraries into default installs breaks continuous integration on Linux runners and prevents clean adoption across diverse platforms.

## Success Criteria

Project success is evaluated across two distinct development phases:

### Current Phase: Project Scaffold

1. Package Scaffolding: The core package installs and imports cleanly as `asr_skill` in a Python 3.12+ environment without requiring PyTorch, Transformers, or MLX.
2. Truthful Execution Boundaries: The command-line interface explicitly refuses to execute unimplemented capabilities. The `version` command reports `asr-skill 0.0.0 phase=scaffold implemented=false`. The `doctor` command prints JSON with `implemented` set to false, `models_ready` set to false, and `network` set to false, without invoking ffmpeg, machine learning models, or network sockets.
3. Stub Refusal: All planned pipeline subcommands (`init`, `diarize`, `align`, `clean`, `run`, and `smoke`) exit immediately with return code 3 and return a JSON payload with an error field set to `not_implemented`.
4. Documentation Accuracy: All documentation, test plans, and skill manifests consistently state that transcription is not yet implemented.

### Future Phase: Full Pipeline Implementation

1. Deterministic Artifact Generation: Given an input audio file, the pipeline produces three primary artifacts: a canonical rich JSONL segment record, a verbatim raw CSV, and a readable cleaned CSV with exactly two columns (`speaker,content`).
2. Complete Traceability: A sidecar source map accounts for every segment identifier from the canonical rich record, verifying that each segment either maps to a readable row or appears in a deleted list with an explicit reason.
3. Speaker Integrity: Speaker assignment maintains a strict distinction between mapped names and unknown speakers. Acoustic labels with insufficient evidence remain labeled by their acoustic identifier. No speaker identities are assigned by keyword heuristics or guesswork.
4. Semantic Invariant Preservation: The cleaning stage preserves all conditional phrases, numerical figures, and negation tokens. Any dropped number or negation token triggers deterministic validation failure.
5. External Compatibility: External daily jobs can call this library through thin wrappers that keep the legacy flags and artifact names, without a second implementation.

## Functional Requirements

The core package is released under the MIT license with package name `asr-skill`, importable as `asr_skill`. It requires Python 3.12+ and uses `uv` for environment management. The default installation omits heavy machine learning libraries, allowing continuous integration jobs on Ubuntu runners to import the package without GPU hardware.

Model runtimes operate in two isolated environments outside the core package:
- Diarization: `nvidia/Nemotron-3-Diarization` on CPU in a dedicated environment with matching audio frame classification libraries.
- Speech Recognition: `Qwen/Qwen3-ASR-1.7B` through MLX on Apple Silicon in an independent environment. Absence of MLX on Linux CI is not an installation failure.

Weights download only on explicit user request to standard cache locations (`HF_HOME`). Weights, recordings, and local environments are never committed.

Diarization runs on the original recording timeline without prior cutting or concatenation. Analysis uses 10 ms frames, drops fragments shorter than 0.15 seconds, merges same-speaker segments separated by up to 0.3 seconds, and groups speech regions across pauses up to 1.0 second. If direct audio decoding fails, ffmpeg converts the input to a temporary 16 kHz mono WAV file, which is deleted immediately after inference.

Speech regions are sliced with ffmpeg and transcribed with word timestamps. Each word is mapped to a diarization segment by its midpoint time. Words outside segments map to the nearest segment within 1.5 seconds or remain unassigned. Overlapping speech receives composite acoustic labels (such as `0900:A+0900:B`).

Acoustic labels derive prefixes from filename stems: stems ending in `_HHMM` provide four digits; otherwise the full stem is used. Sequential letters (A, B, C) reflect first appearance in that file. Words are grouped into utterances using mechanical boundaries: pauses over 3.0 seconds start a new line; fragments under 3 characters merge into neighboring lines if within 15.0 seconds; lines over 400 characters split at punctuation.

The pipeline outputs three artifacts: canonical rich JSONL segments (`segment_id`, `file`, `start`, `end`, `speaker`, `content`), raw CSV (`speaker,content`), and readable CSV (`speaker,content`). A sidecar source map tracks each rich segment to readable rows or records deletion reasons. Acoustic labels have status `mapped` or `unknown`. Display names replace acoustic labels only in the readable CSV at emission time; canonical rich files are never modified.

Semantic cleaning runs via an external AI reader through an isolated task directory. The core library holds no LLM credentials. The cleaner fixes repetitions, duplicate lines, and recognition errors while keeping conditions, numbers, and negations (`not`, `no`, `never`, `不`, `没`, `未`, `别`). A deterministic validation gate enforces complete segment accounting and fails if numbers or negation tokens are lost. Successful validation triggers atomic artifact replacement.

A local JSON run manifest tracks stage states (`pending`, `running`, `complete`, `failed`), input hashes, and outputs for idempotent execution. External legacy wrappers adapt date-directory flags (`--date-dir`, `--output`, `--rich-output`, `--model`) and artifact names (`diarization.json`, `transcript_<date>.csv`, `transcript_<date>.rich.jsonl`) to explicit CLI arguments.

## Non-Goals

1. Remote Services: No hosted transcription APIs, cloud storage adapters, or remote telemetry.
2. Direct LLM Dependencies: The core package does not bundle LLM client libraries or read LLM API keys.
3. Heavy ML in Core: PyTorch and MLX are excluded from the default package install.
4. Cross-File Identity: The system does not perform global voice biometrics or automatic cross-file identity linking.
5. Heuristic Regex Cleaning: The package will not implement regular-expression filler stripping or keyword-based speaker assignment.
6. Downstream Life Daemons: Background recording services, audio ingestion daemons, and daily summary generators remain external to this repository.
