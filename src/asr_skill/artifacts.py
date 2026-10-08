"""Artifact readers and writers. Paths are caller-supplied."""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

from asr_skill.contracts import RAW_CSV_FIELDS, TIMED_CSV_FIELDS


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    write_atomic(path, body or "\n")


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})
    os.replace(temporary, path)


def replace_generation(staged: list[tuple[Path, Path]]) -> None:
    """Replace a set of outputs together. A failure restores the previous set."""
    backups: list[tuple[Path, Path]] = []
    try:
        for source, dest in staged:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                backup = dest.with_name(dest.name + ".prev")
                os.replace(dest, backup)
                backups.append((backup, dest))
            os.replace(source, dest)
    except Exception:
        for backup, dest in reversed(backups):
            if dest.exists():
                dest.unlink()
            if backup.exists():
                os.replace(backup, dest)
        raise
    if backups:
        history = staged[0][1].parent / "history" / time.strftime("%Y%m%dT%H%M%SZ")
        history.mkdir(parents=True, exist_ok=True)
        for backup, _dest in backups:
            if backup.exists():
                os.replace(backup, history / backup.name.removesuffix(".prev"))


def csv_fields(fmt: str) -> tuple[str, ...]:
    if fmt == "legacy":
        return RAW_CSV_FIELDS
    if fmt == "timed":
        return TIMED_CSV_FIELDS
    raise ValueError(f"unknown csv format: {fmt}")


def display_rows(rows: list[dict], name_for) -> list[dict]:
    output = []
    for row in rows:
        speaker = name_for(row["file"], row["speaker"])
        output.append({**row, "speaker": speaker})
    return output
