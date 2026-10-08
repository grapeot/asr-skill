# Transcript Editor Instructions

Read `segments.jsonl` in this directory and write `edited.json` here. Process raw ASR segments into clean, readable text using semantic judgment. Correct misrecognized speech, clean fillers and stutters, and insert punctuation. Semantic equivalence is not automatically proven.

## Inputs and Schema

Inputs include source segments (IDs, acoustic labels, timestamps, text) and optional speaker mappings in `confirmed_name_map.json`.

Emit a JSON object containing `rows`, `uncertain`, `excluded`, `corrections`, and `name_map`. Absent collections default to empty. Each emitted row has `source_ids`, `start`, `end`, `speaker`, and `content`.

In `name_map[filename][acoustic_label]`, mapped names use `status: "mapped"` and a non-empty string `name`. Missing mappings default to unknown or supplied caller mappings; provided mappings may be modified.

## Enforced Validation Rules

Only three rules are enforced:

1. **Speaker Validity**: A published speaker must be `unknown`, one of that row's known source acoustic labels, or a non-empty mapped name corresponding to one of those source labels.
2. **Uncertain Rows**: Every row in `uncertain` must have `speaker` set exactly to `unknown`.
3. **Envelope and Monotonic Order**: Row `start` and `end` must be finite with `start <= end`, inside the envelope of referenced known source intervals (0.05-second tolerance). Sorted by first source position, referenced source positions cannot go backwards, nor can row start times within a source file. Sources may be omitted or repeated across multiple rows.
