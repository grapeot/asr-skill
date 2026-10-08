# Agent Integration Guide

This guide describes how coding agents and language model agents interact with asr-skill.

## Agent Discovery and Repository Registration

An agent starts from the host AGENTS.md or CLAUDE.md, follows any routing file, clones or vendors this repository to a persistent location such as /path/to/asr-skill, and registers only skills/asr/SKILL.md. The pointer must locate that checkout.

Supported installation is a persistent checkout, not a copied skill file and not a wheel or pipx install. The repository is available at https://github.com/grapeot/asr-skill .

## Environment Setup and Maintenance

Inside the persistent checkout directory, initialize the environment using uv venv --python 3.12 . Activate the environment using source .venv/bin/activate, or execute commands directly using .venv/bin/asr-skill . Install dependencies in editable mode using uv pip install -e '.[dev]' . ffmpeg must be available on PATH.

Execute asr-skill init to create the two isolated runtime environments .venvs/diar and .venvs/asr from requirements/diar.txt and requirements/asr.txt. Dependency installation may use the network. When initializing without downloading model weights, run asr-skill init --no-download; note that if cached weights are missing, subsequent model loading fails.

Run asr-skill doctor to inspect the environment. The doctor command loads both models from the local cache and does not download weights. Run asr-skill doctor --no-load to check imports and declared dependency pins only.

## Target Platform and Pins

The package is verified on one Apple Silicon machine, CPython 3.12, not on every Apple Silicon OS release. Linux CI does not run these acoustic models. The doctor command refuses a version or commit mismatch. Explicit download failures are not retried by this package, though transport libraries may have internal retries.

The exact dependency pins are:

- torch 2.14.0 with wheel tag cp312-cp312-macosx_14_0_arm64
- transformers git commit f339035b986aaf719bc6f5ea92342f73c498cb0e reporting 5.18.0.dev0
- librosa 1.0.0
- numpy 2.5.3
- mlx 0.32.3 with wheel tag cp312-cp312-macosx_26_0_arm64
- mlx-qwen3-asr 0.4.4

Acoustic models are nvidia/Nemotron-3-Diarization on CPU and Qwen/Qwen3-ASR-1.7B through MLX.

## The Agent as Editor

The current agent is the editor. The agent handles transcript post-processing using prepare-edit and finalize-edit.

First, execute prepare-edit --rich /path/to/rich.json --task-dir /path/to/task_dir . You may optionally supply --confirmed-name-map /path/to/name_map.json .

Second, inspect instructions.md and segments.jsonl inside /path/to/task_dir . Generate edited.json adhering strictly to the schema described below.

Third, execute finalize-edit --rich /path/to/rich.json --task-dir /path/to/task_dir --output-csv /path/to/output.csv --source-map /path/to/source_map.json --name-map /path/to/name_map.json . The option --csv-format accepts legacy or timed, defaulting to timed.

An optional external adapter is supported by passing --editor-cmd /path/to/adapter to clean. The adapter must be one executable file plus the task directory as its only argument. A shell string is not accepted. The package does not include a semantic editor and does not call a vendor.

## Schema and Rules for edited.json

The keys required in edited.json are rows, excluded, uncertain, corrections, and name_map. Use excluded, not deleted. Each source segment id from segments.jsonl must appear exactly once across rows, uncertain, and excluded. An uncertain row can be first, middle, or last, and the readable CSV keeps it at that source position with speaker unknown.

Uncertain rows are exported to the readable CSV with speaker unknown.

A combined acoustic label such as 0900:A+0900:B may become one name, such as Alice or Bob, only with reason overlap_attribution and a confidence value. Otherwise, keep the combined label or unknown, and keep the row.

The name_map object indexes filename, then label, with status mapped or unknown, and origin caller or editor. An entry with origin caller is not changed. An unknown entry has an empty name string. Do not invent a name that the words in that file do not support.

## String Guard Rules

The string guard rejects an unannotated loss of a digit or negation token. Matching is evaluated by token, so 3 inside 13 does not count, and not inside note does not count.

When modifying text containing digits or negation tokens, provide an entry in corrections. A correction entry requires before equal to the source token, a non-empty after that appears in the exported text, and a reason. The string guard does not prove the sentences mean the same thing; equivalence_proven is recorded as false.

## Resumption, Caching, and Legacy Commands

Resume skips a file only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. Checkpoints use a path hash, not only the basename. Duplicate basenames in one batch are rejected.

An empty speech result is treated as a completed empty output, not a reason to rerun forever. A failed diarization does not leave the previous combined file as the current result. An acoustic rerun moves an existing readable draft to history instead of deleting it.

Legacy commands legacy-diarize and legacy-align keep date_dir and audio_dir and find audio from the diarization JSON. They do not write checkpoints into the date directory, and they refuse to overwrite an existing output that this tool does not own.

## Privacy, Network, and Testing Boundaries

Acoustic inference stays on this machine. A configured editor may send text to its own service. There is no promise that text never leaves the machine. Dependency install may use the network.

Recordings and weights should stay out of git. The ignore rules cover the generated names this tool writes, and they are not a guarantee against every possible path.

A synthetic smoke test is executed with asr-skill smoke. It uses macOS say voices Eddy and Daniel when they exist. It does not prove who spoke. Overlap attribution is covered by offline fixtures, not by a claim that a real overlapping recording was measured.
