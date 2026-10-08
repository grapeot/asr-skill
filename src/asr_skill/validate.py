"""Checks for one editor result. They do not prove semantic equivalence."""

from __future__ import annotations

import math
from copy import deepcopy


def _by_id(segments: list[dict]) -> dict[str, dict]:
    return {row["segment_id"]: row for row in segments}


def required_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _envelope_ok(row: dict, sources: list[dict]) -> bool:
    if not sources:
        return False
    try:
        start = float(row["start"])
        end = float(row["end"])
    except (KeyError, TypeError, ValueError):
        return False
    lo = min(float(item["start"]) for item in sources)
    hi = max(float(item["end"]) for item in sources)
    return math.isfinite(start) and math.isfinite(end) and start <= end and start >= lo - 0.05 and end <= hi + 0.05


def complete_name_map(segments: list[dict], edited: dict, confirmed: dict | None = None) -> dict:
    """Fill omitted labels without inventing names or changing supplied entries."""
    normalized = {**edited, "name_map": deepcopy(edited.get("name_map", {}))}
    name_map = normalized["name_map"]
    if not isinstance(name_map, dict):
        return normalized
    for segment in segments:
        filename, label = segment["file"], segment["speaker"]
        file_map = name_map.setdefault(filename, {})
        if not isinstance(file_map, dict) or label in file_map:
            continue
        caller_entry = (confirmed or {}).get(filename, {}).get(label)
        if caller_entry and caller_entry.get("origin") == "caller":
            file_map[label] = deepcopy(caller_entry)
        else:
            file_map[label] = {"status": "unknown", "name": "", "origin": "editor"}
    return normalized


def ordered_exports(segments: list[dict], edited: dict) -> list[tuple[str, dict]]:
    index = {segment["segment_id"]: i for i, segment in enumerate(segments)}
    exports = [(key, row) for key in ("rows", "uncertain") for row in edited.get(key, [])]
    return sorted(
        exports,
        key=lambda item: min((index[sid] for sid in item[1].get("source_ids", []) if sid in index),
                             default=len(segments)),
    )


def _speaker_allowed(row: dict, sources: list[dict], name_map: dict) -> bool:
    speaker = str(row.get("speaker", ""))
    if speaker == "unknown":
        return True
    for source in sources:
        if speaker == source["speaker"]:
            return True
        file_map = name_map.get(source["file"], {}) if isinstance(name_map, dict) else {}
        entry = file_map.get(source["speaker"], {}) if isinstance(file_map, dict) else {}
        if not isinstance(entry, dict):
            continue
        mapped_name = entry.get("name")
        if entry.get("status") == "mapped" and required_text(mapped_name) and speaker == mapped_name:
            return True
    return False


def review(segments: list[dict], edited: dict, confirmed: dict | None = None) -> dict:
    edited = complete_name_map(segments, edited, confirmed)
    by_id = _by_id(segments)
    problems: list[str] = []
    index = {segment["segment_id"]: i for i, segment in enumerate(segments)}
    emitted_indices = []
    starts_by_file: dict[str, list[float]] = {}
    for key, row in ordered_exports(segments, edited):
        ids = [segment_id for segment_id in row.get("source_ids", []) if segment_id in by_id]
        sources = [by_id[segment_id] for segment_id in ids]
        if not _envelope_ok(row, sources):
            problems.append(f"time envelope {ids}")
        else:
            for filename in {source["file"] for source in sources}:
                starts_by_file.setdefault(filename, []).append(float(row["start"]))
        if not _speaker_allowed(row, sources, edited.get("name_map") or {}):
            problems.append(f"speaker not allowed {ids}")
        if key == "uncertain" and row.get("speaker") != "unknown":
            problems.append("uncertain speaker must be unknown")
        emitted_indices.extend(index[sid] for sid in ids)
    if emitted_indices != sorted(emitted_indices) or any(
        starts != sorted(starts) for starts in starts_by_file.values()
    ):
        problems.append("rows are out of source time order")
    return {
        "ok": not problems,
        "equivalence_proven": False,
        "missing_source_ids": [],
        "problems": problems,
        "unannotated_losses": [],
        "name_map_problems": [],
        "warnings": [],
    }
