"""Hand a transcript to a caller-supplied editor. This module does not edit text."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from asr_skill.artifacts import read_json, read_jsonl, write_atomic, write_csv, write_json, write_jsonl
from asr_skill.contracts import EXIT_OK, EXIT_RUNTIME, EXIT_VALIDATION
from asr_skill.validate import ordered_exports, review


def instructions_path() -> Path:
    return Path(__file__).with_name("editor_instructions.md")


def prepare_task(task_dir: Path, segments: list[dict], confirmed: dict | None = None) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(task_dir / "segments.jsonl", segments)
    write_atomic(task_dir / "instructions.md", instructions_path().read_text(encoding="utf-8"))
    if confirmed:
        write_json(task_dir / "confirmed_name_map.json", confirmed)


def run_editor(command: str, task_dir: Path) -> subprocess.CompletedProcess[str]:
    timeout = int(os.environ.get("ASR_SKILL_EDITOR_TIMEOUT", "1800"))
    return subprocess.run(
        [command, str(task_dir)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def apply_edit(
    segments: list[dict],
    edited: dict,
    csv_format: str,
    confirmed: dict | None = None,
) -> tuple[list[dict], dict, dict]:
    result = review(segments, edited, confirmed)
    if not result["ok"]:
        return [], result, {}
    rows = []
    source_rows = []
    uncertain = []

    def add(row: dict, kind: str) -> None:
        speaker = "unknown" if kind == "uncertain" else row.get("speaker", "unknown")
        item = {
            "start": row.get("start", ""),
            "end": row.get("end", ""),
            "speaker": speaker,
            "content": row.get("content", ""),
        }
        source_rows.append(
            {"output_index": len(rows), "source_ids": row.get("source_ids", []), "kind": kind}
        )
        if kind == "uncertain":
            uncertain.append(
                {**item, "source_ids": row.get("source_ids", []), "reason": row.get("reason", "")}
            )
        rows.append(item)

    for key, row in ordered_exports(segments, edited):
        add(row, "uncertain" if key == "uncertain" else "row")
    source_map = {
        "rows": source_rows,
        "excluded": edited.get("excluded", []),
        "uncertain": uncertain,
        "corrections": edited.get("corrections", []),
        "equivalence_proven": False,
    }
    return rows, result, {
        "source_map": source_map,
        "name_map": edited.get("name_map", {}),
        "csv_format": csv_format,
    }


def clean_files(
    rich_path: Path,
    output_csv: Path,
    source_map_path: Path,
    name_map_path: Path,
    editor_cmd: str,
    csv_format: str,
    task_dir: Path,
) -> int:
    if not editor_cmd:
        print("clean requires an editor command. No regex cleaner will run.", file=sys.stderr)
        return EXIT_RUNTIME
    if not Path(editor_cmd).is_file():
        print(
            f"editor command does not exist: {editor_cmd}. No regex cleaner will run.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME
    segments = read_jsonl(rich_path)
    confirmed_path = task_dir / "confirmed_name_map.json"
    confirmed = read_json(confirmed_path) if confirmed_path.is_file() else None
    prepare_task(task_dir, segments, confirmed)
    try:
        proc = run_editor(editor_cmd, task_dir)
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"command": "clean", "ok": False, "error": f"editor timed out: {exc}"}))
        return EXIT_RUNTIME
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
        sys.stderr.write(proc.stdout or "")
        print(json.dumps({"command": "clean", "ok": False, "error": "editor failed", "exit": proc.returncode}))
        return EXIT_RUNTIME
    edited_path = task_dir / "edited.json"
    if not edited_path.is_file():
        print("editor exited 0 but did not write edited.json", file=sys.stderr)
        return EXIT_VALIDATION
    return finalize_edit(
        rich_path, edited_path, output_csv, source_map_path, name_map_path, csv_format, task_dir
    )


def finalize_edit(
    rich_path: Path,
    edited_path: Path,
    output_csv: Path,
    source_map_path: Path,
    name_map_path: Path,
    csv_format: str,
    task_dir: Path,
) -> int:
    segments = read_jsonl(rich_path)
    if not edited_path.is_file():
        print("edited.json is missing", file=sys.stderr)
        return EXIT_VALIDATION
    edited = read_json(edited_path)
    confirmed_path = task_dir / "confirmed_name_map.json"
    confirmed = read_json(confirmed_path) if confirmed_path.is_file() else None
    rows, result, extras = apply_edit(segments, edited, csv_format, confirmed)
    write_json(task_dir / "validation.json", result)
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        print("validation rejected the edit. Previous outputs were left in place.", file=sys.stderr)
        return EXIT_VALIDATION
    from asr_skill.artifacts import csv_fields, replace_generation

    staging = task_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    staged_csv = staging / output_csv.name
    staged_source = staging / source_map_path.name
    staged_names = staging / name_map_path.name
    write_csv(staged_csv, rows, csv_fields(csv_format))
    write_json(staged_source, extras["source_map"])
    write_json(staged_names, extras["name_map"])
    replace_generation(
        [(staged_csv, output_csv), (staged_source, source_map_path), (staged_names, name_map_path)]
    )
    return EXIT_OK
