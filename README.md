# asr-skill

asr-skill provides local speaker-attributed transcription on Apple Silicon. Diarization runs on CPU using nvidia/Nemotron-3-Diarization, and acoustic speech recognition runs through MLX using Qwen/Qwen3-ASR-1.7B. Acoustic inference stays on this machine. If an external editor is configured, that editor may send text to its own service. There is no promise that text never leaves the machine.

## Installation and Setup

The repository is hosted at https://github.com/grapeot/asr-skill . Supported installation is a persistent checkout, such as /path/to/asr-skill . Copied skill files, wheel distributions, and pipx installations are not supported. An agent starts from the host AGENTS.md or CLAUDE.md, follows any routing file, clones or vendors this repository, and registers only skills/asr/SKILL.md. The pointer must locate that checkout.

To set up the environment from the checkout directory, create the virtual environment using uv venv --python 3.12 . Activate the environment with source .venv/bin/activate, or call .venv/bin/asr-skill explicitly. Install dependencies with uv pip install -e '.[dev]' . ffmpeg must be available on PATH.

Execute asr-skill init to create the isolated environments .venvs/diar and .venvs/asr from requirements/diar.txt and requirements/asr.txt. Dependency installation may use the network. Running asr-skill init --no-download does not download model weights; if the local cache is missing, load fails.

Run asr-skill doctor to inspect the environment. It loads both models from the local cache and does not download weights. Running asr-skill doctor --no-load checks imports and declared package pins only.

## Verified Environment

The package is verified on one Apple Silicon machine, CPython 3.12, not on every Apple Silicon OS release. Declared dependency pins are:

- torch 2.14.0 with wheel tag cp312-cp312-macosx_14_0_arm64
- transformers git commit f339035b986aaf719bc6f5ea92342f73c498cb0e reporting 5.18.0.dev0
- librosa 1.0.0
- numpy 2.5.3
- mlx 0.32.3 with wheel tag cp312-cp312-macosx_26_0_arm64
- mlx-qwen3-asr 0.4.4
- nagisa 0.3.0
- soynlp 0.0.493

Diarization is nvidia/Nemotron-3-Diarization on CPU. ASR is Qwen/Qwen3-ASR-1.7B through MLX. Linux CI does not run these models. The doctor command refuses a version or commit mismatch. A failed explicit download is not retried by this package. That does not describe every retry inside an HTTP library.

Version 0.1.1 adds two direct timestamp dependencies from the mlx-qwen3-asr 0.4.4 aligner extra: nagisa 0.3.0 and soynlp 0.0.493, and asr-skill init installs them from requirements/asr.txt. doctor and doctor --no-load refuse a missing or different version, a missing tokenizer is a failure, and the package does not switch models, drop a language, or use another tokenizer.

## Command Line Interface

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

## Editing Workflow

The current agent is the editor. The agent runs prepare-edit, reads instructions.md and segments.jsonl in the task directory, writes edited.json, then runs finalize-edit. An optional external adapter is supported as one executable file plus the task directory as its only argument, specified via --editor-cmd. A shell string is not accepted. The package does not include a semantic editor and does not call a vendor.

The edited.json file uses the keys rows, excluded, uncertain, corrections, and name_map. Use excluded, not deleted. Each source segment id appears once across rows, uncertain, and excluded. An uncertain item is a row object with source_ids, start, end, speaker, and content. It can sit first, in the middle, or last, and the readable CSV keeps it there with speaker unknown.

A combined acoustic label such as 0900:A+0900:B may become one name, such as Alice or Bob, only with reason overlap_attribution and a confidence value. Otherwise, keep the combined label or unknown, and keep the row.

The name_map dictionary maps filename, then label, with status mapped or unknown, and origin caller or editor. A caller entry is not changed. Unknown has an empty name string. Do not invent a name the words in that file do not support.

## Guardrails and String Guard

The string guard rejects an unannotated loss of a digit or negation token. Matching is by token, so 3 inside 13 does not count, and not inside note does not count.

A correction needs before equal to the source token, a non-empty after that appears in the exported text, and a reason. The string guard checks token presence; it does not prove the sentences mean the same thing. equivalence_proven is false.

## Resumption and Checkpointing

Resume skips a file only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. An empty speech result is a completed empty output, not a reason to rerun forever. A failed diarization does not leave the previous combined file as the current result.

A failed diarization or alignment batch still records a checkpoint when that checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. The stage is failed. A partial batch does not replace the combined output or mark it current. The next run sends only files that failed or have no verified checkpoint. A changed input or parameter hash is not reused. The alignment parameter hash now includes the tokenizer pins, so an older alignment checkpoint is not reused. The diarization parameter hash is unchanged. The acoustic algorithm for a successful file is unchanged.

An acoustic rerun moves an existing readable draft to history instead of deleting it. Duplicate basenames in one batch are rejected. Checkpoints use a path hash, not only the basename. Legacy commands keep date_dir and audio_dir and find audio from the diarization JSON. They do not write checkpoints into the date directory, and they refuse to overwrite an existing output that this tool does not own.

## Testing and Data Hygiene

A single file longer than 7200 seconds is rejected before a model loads. Splitting a file makes separate files; a speaker letter does not continue across slices. Several files that add up to a long day are not one file over the limit.

A synthetic smoke test is executed with asr-skill smoke. It uses macOS say voices Eddy and Daniel when they exist. It does not prove who spoke. Overlap attribution is covered by offline fixtures, not by a claim that a real overlapping recording was measured.

Recordings and weights should stay out of git. The ignore rules cover the generated names this tool writes, and they are not a guarantee against every possible path.
