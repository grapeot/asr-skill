# Test Plan and Verification Protocol: asr-skill

## Test Strategy Overview

The testing methodology for asr-skill is separated into distinct phases corresponding to the project development status. The primary objective for the current scaffold phase is verifying operational truthfulness: ensuring that the repository imports cleanly as a Python package, reports its unready status accurately through its CLI entry points, strictly refuses to execute unimplemented pipeline stages, and contains no committed secrets or private file paths.

All test procedures specified for this phase run strictly offline. They do not download model weights, invoke machine learning inference engines, or read live audio recordings.

## Offline Unit Checks

Automated testing for the scaffold relies on fast, offline unit checks:

1. Package Import Verification: Confirms that `import asr_skill` succeeds in an isolated Python 3.12 environment that lacks PyTorch, Transformers, or Apple MLX. This check verifies that the core package maintains zero heavy machine learning dependencies.
2. CLI Version Text Match: Executes `asr-skill version` and asserts that stdout matches the expected line: `asr-skill 0.0.0 phase=scaffold implemented=false`. The test also checks that the version string matches the version declared in `pyproject.toml`.
3. CLI Doctor Diagnostic Check: Runs `asr-skill doctor` and parses the output as JSON. It asserts that `command` is `doctor`, `phase` is `scaffold`, and that `implemented`, `models_ready`, and `network` are false. The test confirms that the doctor command does not attempt network connections or external process calls to ffmpeg.
4. Planned Command Refusal: Sequentially invokes all planned pipeline commands: `init`, `diarize`, `align`, `clean`, `run`, and `smoke`. The test asserts that each command terminates with exit code 3 and outputs a JSON object whose `error` field equals `not_implemented`.
5. Synthetic Contract Fixture Validation: Validates the synthetic test files in `examples/synthetic/`:
   - `alice_bob_rich.jsonl`
   - `alice_bob_raw.csv`
   - `alice_bob_readable.csv`
   - `alice_bob_name_map.json`
   - `alice_bob_source_map.json`
   The check ensures that the CSV schemas contain exactly two columns (`speaker,content`), confirms that Alice and Bob are mapped while an unmapped acoustic speaker remains `unknown` and appears in the source map deletion list, and asserts that the number 3 and the word "not" are present in the corresponding raw and readable rows.
6. Repository Sanitization Scan: A static analysis test scans the entire repository tree to ensure that no private paths, password-manager references, or real email domains exist in tracked files.

## Deferred Integration and Model Tests

Integration tests and end-to-end model inference runs do not exist in this phase. The scaffold must not claim that transcription works or fabricate synthetic test results. End-to-end tests require multi-gigabyte neural network weights, hardware acceleration via Apple Silicon MLX, and specialized audio frame classification builds. Executing these tests during scaffold evaluation would violate project boundaries and distort operational readiness.

Before any integration or model-level tests are introduced in subsequent phases, the test suite will first implement deterministic contract tests:
- Source Map Accounting Validator: Asserts that 100% of canonical rich segment identifiers appear either in readable rows or within the deleted list with an explicit reason.
- Invariant Token Retention Validator: Injects synthetic transcript segments containing numbers or negation tokens (`not`, `no`, `never`, `不`, `没`, `未`, `别`) and verifies that any simulated cleaning output that drops all instances of these tokens triggers an immediate test failure.

## Manual Verification Procedure Today

Manual verification of the repository is limited to running the two implemented CLI commands from a local checkout:

```bash
asr-skill version
asr-skill doctor
```

Equivalent invocations via `python -m asr_skill version` and `scripts/asr-skill version` may also be executed. The tester observes the returned output to confirm that the package reports its scaffold status. Pass or fail results must not be invented.
