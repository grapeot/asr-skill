# Product Requirements Document: asr-skill

## Overview and Purpose

The asr-skill package provides local speaker-attributed speech transcription on Apple Silicon hardware. Diarization is performed on CPU using nvidia/Nemotron-3-Diarization, and acoustic speech recognition is performed through MLX using Qwen/Qwen3-ASR-1.7B. Acoustic inference stays on this machine. If an external editor is configured, that editor may send text to its own service. There is no promise that text never leaves the machine.

The target audience includes autonomous agents and engineers, such as Alice and Bob, who require local transcription with structured, guarded post-processing.

## Installation and Environment Requirements

The repository is hosted at https://github.com/grapeot/asr-skill . Supported installation is a persistent checkout, such as /path/to/asr-skill . Copied skill files, wheel distributions, and pipx installations are not supported. An agent starts from the host AGENTS.md or CLAUDE.md, follows any routing file, clones or vendors this repository, and registers only skills/asr/SKILL.md. The pointer must locate that checkout.

The host environment requires CPython 3.12 configured through uv venv --python 3.12 . Users activate the environment with source .venv/bin/activate or invoke .venv/bin/asr-skill directly. Project installation requires uv pip install -e '.[dev]' . The system PATH must include the ffmpeg binary.

The asr-skill init command creates two distinct virtual environments, .venvs/diar and .venvs/asr, using requirements/diar.txt and requirements/asr.txt. Dependency installation may use the network. When executed with --no-download, asr-skill init omits downloading model weights; if the local cache is missing, subsequent model loading fails.

The asr-skill doctor command inspects the installation by loading both models from the local cache without downloading weights. The lightweight check asr-skill doctor --no-load verifies package imports and declared pins only.

## Target Platform and Verification Scope

The implementation is verified on one Apple Silicon machine, CPython 3.12, not on every Apple Silicon OS release. Linux CI does not run these acoustic models. The doctor command refuses any version or commit mismatch. Explicit download failures are not retried by this package, though underlying HTTP libraries may handle internal retries.

The exact environment pins are:

- torch 2.14.0 with wheel tag cp312-cp312-macosx_14_0_arm64
- transformers git commit f339035b986aaf719bc6f5ea92342f73c498cb0e reporting 5.18.0.dev0
- librosa 1.0.0
- numpy 2.5.3
- mlx 0.32.3 with wheel tag cp312-cp312-macosx_26_0_arm64
- mlx-qwen3-asr 0.4.4

## Command Specifications and Output Formats

The CLI supports the following commands: version, doctor, init, diarize --input --work-dir, align --input --work-dir, prepare-edit --rich --task-dir [--confirmed-name-map], finalize-edit --rich --task-dir --output-csv --source-map --name-map [--csv-format legacy|timed], clean --editor-cmd, run, smoke, legacy-diarize --date-dir [--output] [--model] [--work-dir], and legacy-align --date-dir --diarization --output [--rich-output] [--model] [--work-dir].

The align command always produces two CSV files: transcript.raw.csv with columns speaker,content and transcript.timed.csv with columns start,end,speaker,content. The legacy-align command defaults to the two-column CSV. The option --csv-format accepts legacy or timed. It governs clean, finalize-edit, and the readable CSV created by run. The default readable format is timed.

## Editing Protocol and Data Contracts

The current agent is the editor. The editing workflow runs prepare-edit, inspects instructions.md and segments.jsonl in the task directory, writes edited.json, and runs finalize-edit. An optional external adapter is supported as one executable file plus the task directory as its only argument, passed via --editor-cmd. A shell string is not accepted. The package does not include a semantic editor and does not call a vendor.

The edited.json payload requires keys rows, excluded, uncertain, corrections, and name_map. The schema mandates excluded, not deleted. Each source segment id must appear exactly once across rows, uncertain, and excluded. An uncertain row can be first, middle, or last, and the readable CSV keeps it at that source position with speaker unknown.

A combined acoustic label such as 0900:A+0900:B may become one name, such as Alice or Bob, only with reason overlap_attribution and a confidence score. Otherwise, the combined label or unknown must be retained, and the row must not be dropped.

The name_map object maps filename, then label, with status mapped or unknown, and origin caller or editor. A caller entry is not changed. Unknown has an empty name string. The editor must not invent a name that the words in that file do not support.

## Guardrails, Resumption, and Data Integrity

The string guard rejects an unannotated loss of a digit or negation token. Token matching ensures that 3 inside 13 does not count, and not inside note does not count. A valid correction requires before equal to the source token, a non-empty after appearing in exported text, and an explanatory reason. The string guard does not prove semantic equivalence; equivalence_proven is recorded as false.

Resumption skips an input file only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. Checkpoints use a path hash, not only the basename. Duplicate basenames in one batch are rejected.

An empty speech result is treated as a completed empty output, not a reason to rerun forever. A failed diarization does not leave the previous combined file as the current result. An acoustic rerun moves an existing readable draft to history instead of deleting it.

Legacy commands preserve date_dir and audio_dir and locate audio from diarization JSON. They do not write checkpoints into the date directory, and they refuse to overwrite an existing output that this tool does not own.

## Privacy, Version Control, and Testing

Acoustic inference stays on this machine. A configured editor may send text to its own service. There is no promise that text never leaves the machine. Dependency install may use the network.

Recordings and weights should stay out of git. The repository ignore rules cover generated names this tool writes, but they are not a guarantee against every possible path.

A synthetic smoke test is executed with asr-skill smoke. It uses macOS say voices Eddy and Daniel when they exist. It does not prove who spoke. Overlap attribution is covered by offline fixtures, not by a claim that a real overlapping recording was measured.
