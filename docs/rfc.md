# Request for Comments: asr-skill Architecture and Design

## Abstract

This document specifies a later implementation. It is not a description of the scaffold. `init`, `diarize`, `align`, `clean`, `run`, and `smoke` exit 3 today.

The design is local speech transcription with speaker attribution. Stages stay separate. Traceability from acoustic segments to readable text is a required sidecar, not an extra CSV column. Validation checks are specified here and are not implemented yet.

## Problem Context and Design Goals

Acoustic speech transcription pipelines often fail when deployed in personal or offline environments because they couple disparate machine learning frameworks, audio processing tools, and text heuristics into undivided scripts. This architecture resolves these failure modes through explicit separation:

1. Temporal Integrity: Diarization runs on the original timeline of each recording. Concatenating audio or stripping silence first replaces that timeline, so later word times no longer match the file.
2. Isolated Runtimes: Machine learning runtimes are isolated into dedicated Python environments. The core CLI package remains free of heavy deep learning dependencies, enabling installation and testing in minimal environments without GPU hardware.
3. Strict Traceability: Every step from acoustic frame detection through semantic cleaning maintains an auditable link. Downstream edits must never silently discard dialogue segments, numerical figures, or negation tokens.
4. Deterministic Contracts: Interfaces between stages rely on fixed JSON and CSV schemas rather than in-memory object references. This enables independent testing, resumption through execution manifests, and wrapper compatibility with legacy batch systems.

## Pipeline Architecture

The transcription lifecycle comprises three sequential processing stages: Diarization, Alignment, and Semantic Cleaning, followed by the emission of finalized data products.

### Stage 1: Timeline Diarization

Diarization identifies speaker segments across the original timeline of each audio recording. The system strictly forbids running diarization on audio that has already been cut up, spliced, or concatenated. Speaker integers are assigned locally per audio file based solely on their order of first appearance. These integer identifiers are strictly local to each file and are never assumed to be stable across separate recordings.

#### Audio Ingestion and Discovery

The public `diarize` command takes an explicit `--input` file or directory. It does not require a date directory. Directory discovery is a compatibility-wrapper rule: look for `.m4a`, `.mp4`, and `.wav` in the date directory, and if none are there, look in an immediate `raw/` child.

Direct audio decoding is attempted first using the runtime's native audio loader. If direct decoding fails due to container or codec anomalies, the pipeline invokes `ffmpeg` to transcode the source file into a temporary 16 kHz single-channel mono WAV file. This temporary WAV file is deleted immediately after the diarization step concludes.

#### Diarization Model and Signal Processing

The diarization runtime uses `nvidia/Nemotron-3-Diarization` running on CPU inside a dedicated Python environment configured via `ASR_SKILL_DIAR_PYTHON`. Signal processing parameters are defined as follows:

- Frame Resolution: 10 milliseconds per evaluation frame.
- Fragment Pruning: Any isolated speaker fragment shorter than 0.15 seconds is dropped.
- Same-Speaker Smoothing: Adjacent speech segments attributed to the same speaker separated by silence gaps up to 0.3 seconds are merged into a single segment.
- Speech Region Aggregation: To allow downstream ASR to skip prolonged periods of silence efficiently, distinct speech segments separated by gaps up to 1.0 second are aggregated into unified speech regions.

#### Diarization Output Schema

The output of Stage 1 is written as a structured JSON file. The schema contract is detailed below:

| Field Path | Type | Description |
| :--- | :--- | :--- |
| `date_dir` | string | Compatibility field. For an explicit file, the parent directory. |
| `audio_dir` | string | `.` when audio sits in `date_dir`, otherwise `raw`. |
| `model` | string | Canonical model identifier: `nvidia/Nemotron-3-Diarization`. |
| `generated_at` | string | Local timestamp `YYYY-MM-DD HH:MM:SS`, not a timezone-aware value. |
| `files[].file` | string | Filename of the analyzed audio recording. |
| `files[].duration_s` | float | Audio duration in seconds. |
| `files[].frame_ms` | number | Frame step, 10. |
| `files[].speakers` | list of integers | Speaker ids in this file, not a count. |
| `files[].segments` | list | List of objects with `start`, `end`, and integer `speaker`. |
| `files[].speech_regions` | list | List of bounding objects with `start` and `end` times for ASR slicing. |

### Stage 2: Word Alignment and Acoustic Attribution

Stage 2 aligns transcribed words with the acoustic segments identified in Stage 1, assigns permanent acoustic labels, and groups consecutive words into coherent utterances.

#### Speech Slicing and Recognition Runtime

The pipeline uses `ffmpeg` to slice each bounding region defined in `speech_regions`. Each audio slice is submitted to the speech recognition runtime. ASR is executed by `Qwen/Qwen3-ASR-1.7B` running via MLX on Apple Silicon inside a dedicated Python environment configured via `ASR_SKILL_ASR_PYTHON`. MLX executes locally on Apple Silicon and is excluded from non-Apple environments such as Linux continuous integration runners.

#### Word-Level Temporal Mapping

The recognition engine yields text tokens accompanied by word-level start and end timestamps. Each word is mapped to a diarization segment using its temporal midpoint:

`t_midpoint = (t_start + t_end) / 2.0`

1. Segment Intersection: If `t_midpoint` falls within an existing diarization segment, the word receives that segment's speaker attribution.
2. Tolerance Window: If `t_midpoint` falls outside all segments (for instance, during brief pause boundaries), the word is assigned to the nearest speaker segment within a 1.5-second window.
3. Unassigned State: If the nearest segment is further than 1.5 seconds away, the word remains unassigned.
4. Overlap Handling: When more than one segment contains the midpoint, the word receives a combined label such as `0900:A+0900:B`. Overlap is not resolved to one speaker.

#### Acoustic Labeling Convention

Acoustic identifiers encode temporal and file context to avoid cross-file collisions:

- Prefix Derivation: If the audio filename stem ends in four digits preceded by an underscore (matching `_HHMM`, such as `session_0900`), those four digits become the label prefix (`0900`). Otherwise, the entire filename stem is used as the prefix.
- Speaker Suffix: Sequential letters (A, B, C, ...) are appended based on the speaker's first chronological appearance within that specific file.
- Composite Formatting: Simultaneous speech retains both speaker letters joined by a plus sign, such as `0900:A+0900:B`.

#### Mechanical Utterance Grouping

Words are aggregated into dialogue lines through mechanical, non-semantic grouping rules:

- Speaker Continuity: Consecutive words sharing the identical acoustic label are grouped sequentially.
- Pause Splitting: A temporal silence gap exceeding 3.0 seconds between consecutive words terminates the current line and begins a new utterance.
- Micro-Fragment Merging: An utterance fragment containing fewer than 3 characters may merge into an adjacent line attributed to the same speaker if the temporal gap does not exceed 15.0 seconds.
- Sentence Length Limiting: Any utterance exceeding 400 characters is split at sentence-ending punctuation marks, with intermediate timestamps linearly interpolated across the split segments.

### Stage 3: Product Artifacts and Schema Contracts

Alignment writes the rich segments and the raw CSV. Cleaning writes the readable CSV and the source map. This diagram is the later data flow, not a command that runs today:

```
[Audio Input]
      │
      ▼
Stage 1: Diarize ──► diarization.json
      │
      ▼
Stage 2: Align ────► 1. Canonical Rich JSONL (.rich.jsonl)
      │              2. Raw Verbatim CSV (.raw.csv)
      ▼
Stage 3: Clean ────► 3. Readable Cleaned CSV (.readable.csv)
                     4. Sidecar Source Map (.source_map.json)
```

#### Canonical Rich Segments (`.rich.jsonl`)

The canonical rich JSONL file serves as the permanent source of truth for all acoustic and temporal data. It records individual segments with the following schema:

```json
{
  "segment_id": "seg_0900_0001",
  "file": "session_0900.m4a",
  "start": 12.45,
  "end": 15.80,
  "speaker": "0900:A",
  "content": "Good morning Bob, did you review the report?"
}
```

The canonical rich file retains acoustic speaker labels permanently. It is never rewritten when display names are resolved.

#### Raw Verbatim CSV (`.raw.csv`)

The raw CSV file contains unedited recognized text before semantic filtering. Its structure is strictly constrained to two columns:

```csv
speaker,content
0900:A,"Good morning Bob, did you review the report?"
0900:B,"Yes Alice, that was checked not three minutes ago."
```

No additional columns are permitted.

#### Readable Cleaned CSV (`.readable.csv`)

The readable CSV provides normalized text with resolved display names. Its structure is likewise strictly constrained to two columns:

```csv
speaker,content
Alice,"Good morning Bob, did you review the report?"
Bob,"Yes Alice, that was checked not three minutes ago."
```

#### Sidecar Source Map and Name Map

Traceability lives in sidecar JSON files, not in extra CSV columns:

- Name Map (`name_map.json`): Each acoustic label is tracked with a status of either `mapped` or `unknown`. A display name is assigned only when conversational evidence is conclusive. If evidence is ambiguous, the label remains `unknown`, and the readable CSV retains the acoustic identifier. Acoustic labels are never merged by guesswork or keyword lists. Overlapping speaker labels are never assigned a single name. Display name substitution occurs solely during CSV emission.
- Source Map (`source_map.json`): Maps each row index in the readable CSV to an array of canonical `segment_id` references. Any `segment_id` omitted from the readable output must appear in a `deleted` array accompanied by an explicit reason string.

### Stage 4: Semantic Cleaning and Validation Protocol

Semantic cleaning transforms raw transcribed speech into readable text while preserving historical meaning.

#### Execution Boundary

Cleaning is treated as a semantic task executed by an external AI reader. The `asr_skill` library does not bundle LLM client libraries, does not make remote API calls, and does not read LLM API keys. When invoked, the future `clean` subcommand prepares a isolated task directory containing the raw text, acoustic labels, and instructions, then executes a user-configured command. If no cleaning command is configured in the environment, the CLI fails closed.

#### Permitted Editorial Actions

The external editor is restricted to the following transformations:
- Removing acoustic stutter loops and repetition cycles that do not form grammatical utterances.
- Dropping adjacent duplicate lines caused by recognition decoding traps.
- Merging fragmented clauses belonging to a single broken sentence into a unified utterance.
- Inserting appropriate punctuation and capitalization.
- Correcting obvious transcription errors identifiable from conversational context.
- Converting traditional Chinese characters to simplified Chinese characters when applicable as part of semantic reading.
- Retaining short replies (such as "yes", "no", "okay") that carry affirmative or negative communicative intent.

#### Deterministic Validation Gate

Before any cleaned output is accepted, the CLI applies an automated deterministic validation check:

1. Segment Completeness: Every `segment_id` in the input rich file must appear either in the source map or in the deleted list with an explicit reason. Silent omissions trigger immediate failure.
2. Invariant Token Preservation: If a source segment contains numerical digits or negation tokens (`not`, `no`, `never`, `不`, `没`, `未`, `别`), the corresponding output text must retain them. If the editor eliminates all instances of numbers or negations present in the source segment, the validation check rejects the output.
3. Atomic State Management: The CLI writes prospective outputs to temporary sibling files. Only upon passing all deterministic checks are files atomically renamed into place. If validation fails, the existing files remain unmodified.

### Stage 5: Execution Engine and Run Manifest

Pipeline orchestration is managed through a local JSON manifest stored in the working directory. The manifest tracks three discrete stages: `diarize`, `align`, and `clean`.

```json
{
  "stages": {
    "diarize": {
      "status": "complete",
      "input_hash": "sha256-of-inputs",
      "output_paths": ["/path/to/asr-work/diarization.json"],
      "start_time": null,
      "finish_time": null
    }
  }
}
```

Stage states include `pending`, `running`, `complete`, and `failed`. The object above shows the field shape. The null times are not a recorded run. When a later `run` command is invoked, it hashes the stage inputs. If a stage is marked `complete` and its input hash is unchanged, execution skips to the subsequent stage.

## Command-Line Interface and Compatibility Wrappers

The project distinguishes between its explicit CLI interface and external compatibility wrappers required by legacy consumers.

### Public CLI Interface

The standalone CLI provides explicit file-based arguments:

```bash
asr-skill diarize --input /path/to/recordings/audio.m4a --output /path/to/workdir/diarization.json
asr-skill align --diarization /path/to/workdir/diarization.json --output-rich /path/to/workdir/transcript.rich.jsonl --output-csv /path/to/workdir/transcript.raw.csv
asr-skill clean --rich /path/to/workdir/transcript.rich.jsonl --output-csv /path/to/workdir/transcript.readable.csv --source-map /path/to/workdir/source_map.json
asr-skill run --input /path/to/recordings/audio.m4a --work-dir /path/to/workdir
```

### External Compatibility Wrappers

Existing scheduled jobs consume daily recording folders using date-directory flags. These legacy workflows are serviced through thin external wrapper scripts that translate arguments and call this library as their sole underlying implementation:

- Diarize Wrapper: Requires `--date-dir <dir>`. Optional `--output` defaults to `<date-dir>/diarization.json`. Optional `--model` defaults to `nvidia/Nemotron-3-Diarization`.
- Align Wrapper: Requires `--date-dir <dir>`, `--diarization <json>`, and `--output <csv>`. Optional `--rich-output` defaults to the CSV path with suffix `.rich.jsonl`. Optional `--model` defaults to `Qwen/Qwen3-ASR-1.7B`.
- Daily Artifact Conventions: Artifacts under the date directory follow standard naming: `diarization.json`, `transcript_<date>.csv`, and `transcript_<date>.rich.jsonl`.
- Atomic CSV Updates: Rewriting CSV transcripts is atomic. If alignment or cleaning fails, the previous CSV remains intact.

These wrappers exist outside this repository and are not distributed here.

## Rejected Alternatives

1. Regular-Expression Cleaning: Heuristic regex scripts that strip filler tokens invariably damage conversational meaning by stripping modal particles, negation words, and numerical qualifiers. Semantic editing must be performed by contextual language understanding paired with deterministic invariant validation.
2. Keyword Speaker Assignment: Inferring speaker names by matching spoken keywords produces high error rates and incorrect speaker merges. Speaker identity must remain tied to acoustic clustering unless explicit evidence confirms an assignment.
3. Diarizing Concatenated Audio: Stripping silence and concatenating audio prior to diarization destroys temporal rhythm, distorts frame analysis, and makes downstream alignment impossible. Diarization must occur on the unedited timeline.
4. Default Inclusion of Heavy ML Libraries: Bundling PyTorch, Transformers, and MLX into default dependencies creates large installation overhead, introduces binary conflicts, and prevents testing on Linux CI runners. Isolating model execution into distinct environments ensures modularity.
5. Vendor Lock-In for Semantic Cleaning: Hardcoding specific commercial LLM APIs into the core library compromises offline usability and introduces vendor dependency. The task directory model allows any local agent or external command to serve as the editor.
6. Maintaining Duplicate Implementations: Forking or maintaining parallel private and public transcription implementations leads to code drift and synchronisation defects. This library serves as the single reference implementation, accessed by legacy jobs via thin adapters.
7. Adding Metadata Columns to Legacy CSVs: Adding timestamps or confidence columns to output CSVs breaks downstream consumers expecting exactly `speaker,content`. Detailed metadata is properly housed in the canonical rich JSONL file and source map sidecars.
8. Modifying Acoustic Labels in Canonical Records: Replacing acoustic labels inside rich segment records destroys auditability. Acoustic labels remain immutable; display names are mapped via external tables and applied only during final readable CSV generation.
