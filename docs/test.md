# Verification and Testing Guide

## Scope of Verification

Testing for asr-skill verifies environment configuration, acoustic pipeline execution, editor protocol compliance, string guard rules, and resume semantics. Verification has been conducted on one Apple Silicon machine, CPython 3.12, not on every Apple Silicon OS release. Linux CI does not run these acoustic models. The tests do not assert word error rates, benchmark numbers, latency claims, or speaker-identity proofs.

Supported testing requires a persistent checkout at /path/to/asr-skill from https://github.com/grapeot/asr-skill . Copied skill files, wheel distributions, and pipx installations are not supported.

## Environment and Dependency Verification

Run asr-skill doctor to inspect the runtime environment. The command verifies local caching by loading both models, nvidia/Nemotron-3-Diarization on CPU and Qwen/Qwen3-ASR-1.7B through MLX, directly from local storage without downloading weights.

Run asr-skill doctor --no-load to test package imports and declared dependency pins without loading model weights into memory. The doctor command refuses any version or commit mismatch against the declared pins:

- torch 2.14.0 with wheel tag cp312-cp312-macosx_14_0_arm64
- transformers git commit f339035b986aaf719bc6f5ea92342f73c498cb0e reporting 5.18.0.dev0
- librosa 1.0.0
- numpy 2.5.3
- mlx 0.32.3 with wheel tag cp312-cp312-macosx_26_0_arm64
- mlx-qwen3-asr 0.4.4
- nagisa 0.3.0
- soynlp 0.0.493

If an explicit model download fails during initialization, this package does not retry the download, although underlying HTTP libraries may execute transport retries.

## Synthetic Smoke Verification

Run asr-skill smoke to test the end-to-end processing pipeline. On macOS environments where say voices Eddy and Daniel exist, the command generates audio samples, runs diarization and alignment, and produces formatted transcripts.

The smoke test validates pipeline integrity. It does not prove who spoke.

## Overlap Attribution Testing

Overlap attribution behavior is covered by offline fixtures, not by a claim that a real overlapping recording was measured. Static fixture tests verify that a combined acoustic label such as 0900:A+0900:B may become one name, such as Alice or Bob, only with reason overlap_attribution and a confidence score.

The test fixtures verify that when a confidence score is missing or the attribution reason is absent, the system retains the combined label or unknown, and preserves the row.

## String Guard Unit Tests

The test suite validates string guard tokenization and rejection rules. The string guard rejects an unannotated loss of a digit or negation token.

Token matching tests confirm that 3 inside 13 does not count, and not inside note does not count. Test cases assert that a correction record requires before equal to the source token, a non-empty after appearing in the exported text, and an explicit reason. Assertions verify that the string guard does not prove semantic equivalence, and equivalence_proven remains false.

## Checkpoint, Resumption, and Legacy Command Tests

Resumption tests confirm that a file is skipped only when the checkpoint parses, status is complete, and the input hash, parameter hash, and current diarization hash match. Checkpoints use a path hash, not only the basename. Tests assert that batches containing duplicate basenames are rejected.

Tests assert that an empty speech result produces a completed empty output, rather than triggering repeated executions. Tests verify that a failed diarization does not leave the previous combined file as the current result, and an acoustic rerun moves an existing readable draft to history instead of deleting it.

Legacy command tests verify legacy-diarize and legacy-align. The tests ensure that date_dir and audio_dir structures are preserved, audio files are located using the diarization JSON, checkpoints are not written into date_dir, and outputs not owned by the tool are not overwritten.

Output tests ensure that align always writes transcript.raw.csv as speaker,content and transcript.timed.csv as start,end,speaker,content. The tests check that legacy-align defaults to the two-column CSV, while --csv-format controls clean, finalize-edit, and run, defaulting to timed.
