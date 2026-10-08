---
name: asr
description: Local speaker-attributed transcription with Nemotron diarization on CPU and Qwen3-ASR on Apple Silicon. The current agent can prepare, edit, and finalize a transcript. Acoustic inference stays on the machine. A configured editor may send text to its own service.
---

# ASR Skill

This skill enables local speaker-attributed speech transcription and guarded editing on Apple Silicon. Diarization runs on CPU using nvidia/Nemotron-3-Diarization, and speech recognition runs on Apple Silicon via MLX using Qwen/Qwen3-ASR-1.7B. Acoustic inference stays on this machine. If an external editor is configured, that editor may send text to its own service. There is no promise that text never leaves the machine.

## Repository and Registration

The repository is located at https://github.com/grapeot/asr-skill . Supported installation is a persistent checkout, such as /path/to/asr-skill . Copied skill files, wheel distributions, and pipx installations are not supported.

An agent starts from the host AGENTS.md or CLAUDE.md, follows any routing file, clones or vendors this repository, and registers only skills/asr/SKILL.md. The pointer must locate that persistent checkout.

## Environment and Sub-Environments

Within the persistent checkout, set up the primary environment using uv venv --python 3.12 . Activate the environment with source .venv/bin/activate, or invoke .venv/bin/asr-skill explicitly. Install development dependencies using uv pip install -e '.[dev]' . ffmpeg must be available on PATH.

Execute asr-skill init to build the isolated sub-environments .venvs/diar and .venvs/asr from requirements/diar.txt and requirements/asr.txt. Dependency installation may use the network. When using asr-skill init --no-download, model weights are not downloaded; if the local cache is missing, load fails.

Run asr-skill doctor to inspect the environment. It loads both models from the local cache and does not download weights. The command asr-skill doctor --no-load checks imports and declared pins only.

## Target Platform and Pins

The package is verified on one Apple Silicon machine, CPython 3.12, not on every Apple Silicon OS release. Linux CI does not run these acoustic models. The doctor command refuses a version or commit mismatch. Explicit download failures are not retried by this package, though HTTP libraries may implement transport retries.

The declared pins are:

- torch 2.14.0 with wheel tag cp312-cp312-macosx_14_0_arm64
- transformers git commit f339035b986aaf719bc6f5ea92342f73c498cb0e reporting 5.18.0.dev0
- librosa 1.0.0
- numpy 2.5.3
- mlx 0.32.3 with wheel tag cp312-cp312-macosx_26_0_arm64
- mlx-qwen3-asr 0.4.4
- nagisa 0.3.0
- soynlp 0.0.493

## Command Set

The CLI provides the following commands:

- version
- doctor
- init
- diarize --input --work-dir
- align --input --work-dir
- prepare-edit --rich --task-dir [--confirmed-name-map]
- finalize-edit --rich --task-dir --output-csv --source-map --name-map [--csv-format legacy|timed]
- clean --editor-cmd
- run
- smoke
- legacy-diarize --date-dir [--output] [--model] [--work-dir]
- legacy-align --date-dir --diarization --output [--rich-output] [--model] [--work-dir]

The align command always writes transcript.raw.csv as speaker,content and transcript.timed.csv as start,end,speaker,content. The legacy-align command defaults to the two-column CSV. The --csv-format option accepts legacy or timed. It applies to clean, finalize-edit, and the readable CSV produced by run. The default readable format is timed.

## The Agent as Editor Without External Binary

The current agent is the editor. The agent performs semantic editing without requiring an external binary through the following steps.

First, run the prepare-edit command to stage editing inputs:
.venv/bin/asr-skill prepare-edit --rich /path/to/rich.json --task-dir /path/to/task_dir

You may optionally include --confirmed-name-map /path/to/name_map.json to seed confirmed speaker mappings.

Second, read instructions.md and segments.jsonl inside /path/to/task_dir . Review each segment text and speaker label.

Third, construct and write /path/to/task_dir/edited.json . The JSON structure must include the following keys:
- rows: list of active segment objects.
- excluded: list of segment objects excluded from the transcript. Use excluded, not deleted. Each source segment id must appear exactly once across rows, uncertain, and excluded.
- uncertain: a list of row objects, not a list of ids. Each object has source_ids, start, end, speaker, and content. It can be first, middle, or last, and the readable CSV keeps that row at the source position with speaker unknown.
- corrections: list of explicit token modifications. If a digit or negation token is changed or removed, provide before matching the source token, a non-empty after that appears in exported text, and a reason. The string guard does not prove semantic equivalence; equivalence_proven is false.
- name_map: mapping of filename to speaker label. Each entry specifies status (mapped or unknown) and origin (caller or editor). A caller entry is not changed. An unknown entry has an empty name string. Do not invent a name that the words in that file do not support, such as Alice or Bob.

A combined acoustic label such as 0900:A+0900:B may become one name only with reason overlap_attribution and a confidence value. Otherwise, keep the combined label or unknown, and keep the row.

Fourth, run finalize-edit to export results:
.venv/bin/asr-skill finalize-edit --rich /path/to/rich.json --task-dir /path/to/task_dir --output-csv /path/to/output.csv --source-map /path/to/source_map.json --name-map /path/to/name_map.json --csv-format timed

An optional external adapter may be supplied to clean via --editor-cmd /path/to/adapter . The adapter must be one executable file plus the task directory as its only argument. A shell string is not accepted. The package does not include a semantic editor and does not call a vendor.

## String Guard Rules

The string guard rejects an unannotated loss of a digit or negation token. Matching is evaluated by token, so 3 inside 13 does not count, and not inside note does not count. Any unannotated drop of digits or negation words triggers validation failure.

## Resumption, Caching, and Legacy Support

Resume skips a file only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. Checkpoints use a path hash, not only the basename. Duplicate basenames in one batch are rejected.

A failed diarization or alignment batch still records a checkpoint when that checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. The stage is failed. A partial batch does not replace the combined output or mark it current. The next run sends only files that failed or have no verified checkpoint. A changed input or parameter hash is not reused. The alignment parameter hash now includes the tokenizer pins, so an older alignment checkpoint is not reused. The diarization parameter hash is unchanged. The acoustic algorithm for a successful file is unchanged.

An empty speech result is a completed empty output, not a reason to rerun forever. A failed diarization does not leave the previous combined file as the current result. An acoustic rerun moves an existing readable draft to history instead of deleting it.

Legacy commands keep date_dir and audio_dir and find audio from the diarization JSON. They do not write checkpoints into the date directory, and they refuse to overwrite an existing output that this tool does not own.

## Testing and Boundaries

A single file longer than 7200 seconds is rejected before a model loads. Splitting a file makes separate files; a speaker letter does not continue across slices. Several files that add up to a long day are not one file over the limit.

A synthetic smoke test is executed with asr-skill smoke. It uses macOS say voices Eddy and Daniel when they exist. It does not prove who spoke. Overlap attribution is covered by offline fixtures, not by a claim that a real overlapping recording was measured.

Recordings and weights should stay out of git. The ignore rules cover the generated names this tool writes, and they are not a guarantee against every possible path.
