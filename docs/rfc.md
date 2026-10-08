# RFC: Technical Architecture for asr-skill

## Architectural Overview

The asr-skill architecture decouples acoustic inference from transcript post-processing while keeping acoustic compute on Apple Silicon hardware. Diarization is executed on CPU using nvidia/Nemotron-3-Diarization, and acoustic speech recognition is executed on Apple Silicon via MLX using Qwen/Qwen3-ASR-1.7B. Acoustic inference stays on this machine. If an external editor is configured, that editor may send text to its own service. There is no promise that text never leaves the machine.

The supported deployment model requires a persistent checkout from https://github.com/grapeot/asr-skill located at /path/to/asr-skill . Copied skill files, wheel distributions, and pipx installations are not supported. An agent starts from the host AGENTS.md or CLAUDE.md, follows any routing file, clones or vendors this repository, and registers only skills/asr/SKILL.md. The pointer must locate that checkout.

## Sub-Environment Isolation and Dependency Pins

To avoid dependency conflicts between PyTorch on CPU and MLX, the system isolates runtime dependencies under .venvs/ within the checkout directory. The primary environment is created with uv venv --python 3.12, activated via source .venv/bin/activate or called via .venv/bin/asr-skill, and installed using uv pip install -e '.[dev]' . ffmpeg must be available on PATH.

The command asr-skill init builds the isolated sub-environments .venvs/diar and .venvs/asr from requirements/diar.txt and requirements/asr.txt. Dependency installation may use the network. When executed with --no-download, asr-skill init skips downloading model weights; if cached weights are missing, subsequent model loading fails.

The command asr-skill doctor verifies the environment by loading both models from the local cache without downloading weights. The option asr-skill doctor --no-load verifies package imports and declared dependency pins only.

Verification has been conducted on one Apple Silicon machine, CPython 3.12, not on every Apple Silicon OS release. Linux CI does not run these acoustic models. The doctor command refuses any version or commit mismatch. If an explicit download fails, this package does not retry the download, although underlying HTTP libraries may implement transport retries.

The declared dependency pins are:

- torch 2.14.0 with wheel tag cp312-cp312-macosx_14_0_arm64
- transformers git commit f339035b986aaf719bc6f5ea92342f73c498cb0e reporting 5.18.0.dev0
- librosa 1.0.0
- numpy 2.5.3
- mlx 0.32.3 with wheel tag cp312-cp312-macosx_26_0_arm64
- mlx-qwen3-asr 0.4.4
- nagisa 0.3.0
- soynlp 0.0.493

## Execution Pipeline and Output Contracts

The CLI offers: version, doctor, init, diarize --input --work-dir, align --input --work-dir, prepare-edit --rich --task-dir [--confirmed-name-map], finalize-edit --rich --task-dir --output-csv --source-map --name-map [--csv-format legacy|timed], clean --editor-cmd, run, smoke, legacy-diarize --date-dir [--output] [--model] [--work-dir], and legacy-align --date-dir --diarization --output [--rich-output] [--model] [--work-dir].

The align command generates two standard CSV exports: transcript.raw.csv as speaker,content and transcript.timed.csv as start,end,speaker,content. The legacy-align command defaults to the two-column CSV format. The flag --csv-format accepts legacy or timed. It governs clean, finalize-edit, and the readable CSV created by run. The default readable format is timed.

## Editing Protocol and Task Directory Layout

The current agent is the editor. Post-processing operates through a staging task directory. The agent invokes prepare-edit, inspects instructions.md and segments.jsonl in the task directory, writes edited.json, and executes finalize-edit. An optional external adapter may be supplied via clean --editor-cmd /path/to/adapter . The adapter must be one executable file taking the task directory as its only argument. A shell string is not accepted. The package does not include a semantic editor and does not call a vendor.

The edited.json file must provide five top-level keys: rows, excluded, uncertain, corrections, and name_map. Deletions must be represented using excluded, not deleted. Every segment id in segments.jsonl must appear exactly once across rows, uncertain, and excluded. An uncertain row can be first, middle, or last, and the readable CSV keeps it at that source position with speaker unknown.

A combined acoustic label such as 0900:A+0900:B may be resolved to a single name, such as Alice or Bob, only with reason overlap_attribution and a confidence score. If those conditions are not met, the combined label or unknown must be retained, and the row must remain.

The name_map object maps filename, then label, with status mapped or unknown, and origin caller or editor. Any caller entry is immutable. An unknown entry contains an empty name string. Editors must not invent a name that the words in that file do not support.

## String Guard Implementation

The guard is a limited string-loss check for digits and negation tokens. It does not prove the sentences mean the same thing. equivalence_proven is false and that field is the interface, not a disclaimer pile. Matching is evaluated by token, so 3 inside 13 does not count, and not inside note does not count.

Any modification to a digit or negation token requires a corresponding record in corrections. Each correction record must specify before matching the source token, a non-empty after that appears in the exported text, and a reason. The guard validates token presence but does not prove semantic equivalence; equivalence_proven is set to false.

## Checkpoint Design and State Resumption

The resume subsystem skips processing an input file only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. Checkpoints use a path hash, not only the basename. Batches containing duplicate basenames are rejected.

An empty speech result is treated as a completed empty output, not a reason to rerun forever. A failed diarization does not leave the previous combined file as the current result. An acoustic rerun moves an existing readable draft to history instead of deleting it.

Legacy commands preserve date_dir and audio_dir structures, finding audio from the diarization JSON. They do not write checkpoints into the date directory, and they refuse to overwrite an existing output that this tool does not own.

## Testing, Verification, and Git Boundaries

A synthetic smoke test is executed with asr-skill smoke. When macOS say voices Eddy and Daniel exist on the system, the smoke pipeline runs end-to-end synthesis and transcription. It does not prove who spoke. Overlap attribution is covered by offline fixtures, not by a claim that a real overlapping recording was measured.

Recordings and model weights should stay out of git. The repository ignore rules cover generated file names written by this tool, but they do not guarantee exclusion for arbitrary paths.
