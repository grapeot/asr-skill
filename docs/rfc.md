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

The edited.json collections are rows, excluded, uncertain, corrections, and name_map; absent collections default to empty. Each emitted row defines source_ids, start, end, speaker, and content. Sources may be omitted or reused across rows. All split rows are exported.

A combined acoustic label may use its mapped name without an attribution reason or confidence value.

The name_map object indexes filename, then acoustic label. To publish a mapped name, its entry uses status mapped and a non-empty name string. Provided entries may be modified. Omitted mappings are filled as unknown or seeded from caller mappings.

## Edit Validation

Only three validation rules are enforced:

1. A published speaker must be unknown, one of that row's known source acoustic labels, or a non-empty mapped name for one of those source labels.
2. Every uncertain row must have speaker exactly unknown.
3. Row start/end must be finite with start <= end, inside the envelope of known source intervals within 0.05 seconds. Exports are sorted by first source position; referenced source positions cannot go backwards, nor can row start times within a source file.

Other checks, including token guards, mandatory reasons/evidence, mapping completeness, caller immutability, and cross-label merge bans, are removed. Semantic equivalence is not automatically proven; equivalence_proven remains false. Compatibility result fields missing_source_ids, unannotated_losses, name_map_problems, and warnings remain empty lists.

## Checkpoint Design and State Resumption

The resume subsystem skips processing an input file only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. Checkpoints use a path hash, not only the basename. Batches containing duplicate basenames are rejected.

An empty speech result is treated as a completed empty output, not a reason to rerun forever. A failed diarization does not leave the previous combined file as the current result. An acoustic rerun moves an existing readable draft to history instead of deleting it.

Legacy commands preserve date_dir and audio_dir structures, finding audio from the diarization JSON. They do not write checkpoints into the date directory, and they refuse to overwrite an existing output that this tool does not own.

## Testing, Verification, and Git Boundaries

A synthetic smoke test is executed with asr-skill smoke. When macOS say voices Eddy and Daniel exist on the system, the smoke pipeline runs end-to-end synthesis and transcription. It does not prove who spoke. Overlap attribution is covered by offline fixtures, not by a claim that a real overlapping recording was measured.

Recordings and model weights should stay out of git. The repository ignore rules cover generated file names written by this tool, but they do not guarantee exclusion for arbitrary paths.
