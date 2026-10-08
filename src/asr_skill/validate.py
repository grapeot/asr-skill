"""Checks for one editor result. They do not prove semantic equivalence."""

from __future__ import annotations

import math
import re

from asr_skill.contracts import NAME_MAP_STATUSES

_NUMBER = re.compile(r"(?<!\d)\d+(?:\.\d+)?(?!\d)")
_LATIN_NEGATION = ("not", "no", "never", "n't")
_CJK_NEGATION = ("不", "没", "未", "别")


def number_tokens(text: str) -> list[str]:
    return _NUMBER.findall(text)


def negation_tokens(text: str) -> list[str]:
    found = []
    for token in _LATIN_NEGATION:
        if re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", text, re.IGNORECASE):
            found.append(token.lower())
    for token in _CJK_NEGATION:
        if token in text:
            found.append(token)
    return found


def _by_id(segments: list[dict]) -> dict[str, dict]:
    return {row["segment_id"]: row for row in segments}


def _placements(edited: dict) -> list[tuple[str, dict]]:
    placed = []
    for key in ("rows", "uncertain", "excluded"):
        for item in edited.get(key, []):
            for segment_id in item.get("source_ids", []):
                placed.append((segment_id, item))
    return placed


def _exported_text(segment_id: str, edited: dict) -> str:
    chunks = []
    for key in ("rows", "uncertain"):
        for row in edited.get(key, []):
            if segment_id in row.get("source_ids", []):
                chunks.append(str(row.get("content", "")))
    return "\n".join(chunks)


def required_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def exclusion_reason_ok(value) -> bool:
    return required_text(value)


def confidence_ok(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)) and math.isfinite(value):
        return 0 <= value <= 1
    return False


def _excluded(segment_id: str, edited: dict) -> bool:
    for item in edited.get("excluded", []):
        if segment_id in item.get("source_ids", []) and exclusion_reason_ok(item.get("reason")):
            return True
    return False


def token_in_text(token: str, text: str) -> bool:
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return token in number_tokens(text)
    if token in _CJK_NEGATION or re.fullmatch(r"[A-Za-z']+", token):
        return token.lower() in [item.lower() for item in negation_tokens(text)] or bool(
            re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", text, re.IGNORECASE)
        )
    return token in text


def _correction_ok(token: str, segment: dict, output: str, corrections: list[dict]) -> bool:
    for item in corrections:
        if not required_text(item.get("reason")):
            continue
        before = item.get("before")
        after = item.get("after")
        if not required_text(before) or not required_text(after):
            continue
        before_tokens = set(number_tokens(before) + negation_tokens(before))
        if token not in before_tokens and token != before:
            continue
        if token not in number_tokens(segment["content"]) + negation_tokens(segment["content"]):
            continue
        if not token_in_text(after, output):
            continue
        return True
    return False


def _envelope_ok(row: dict, sources: list[dict]) -> bool:
    try:
        start = float(row["start"])
        end = float(row["end"])
    except (KeyError, TypeError, ValueError):
        return False
    lo = min(float(item["start"]) for item in sources)
    hi = max(float(item["end"]) for item in sources)
    return start <= end and start >= lo - 0.05 and end <= hi + 0.05


def _overlap_ok(row: dict, sources: list[dict]) -> bool:
    combined = [item for item in sources if "+" in str(item.get("speaker", ""))]
    if not combined:
        return True
    speaker = str(row.get("speaker", ""))
    acoustic = {item["speaker"] for item in combined}
    if speaker in acoustic or speaker == "unknown":
        return True
    return row.get("reason") == "overlap_attribution" and confidence_ok(row.get("confidence"))


def _file_text(segments: list[dict], filename: str) -> str:
    return "\n".join(segment["content"] for segment in segments if segment["file"] == filename)


def _name_in_file(name: str, text: str) -> bool:
    if re.search(r"[A-Za-z]", name):
        return bool(re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", text))
    return name in text


def ordered_exports(segments: list[dict], edited: dict) -> list[tuple[str, dict]]:
    index: dict[str, tuple[str, dict]] = {}
    for key in ("rows", "uncertain"):
        for row in edited.get(key, []):
            for segment_id in row.get("source_ids", []):
                index.setdefault(segment_id, (key, row))
    ordered = []
    seen: set[int] = set()
    for segment in segments:
        found = index.get(segment["segment_id"])
        if found is None or id(found[1]) in seen:
            continue
        if segment["segment_id"] in {
            sid
            for item in edited.get("excluded", [])
            if exclusion_reason_ok(item.get("reason"))
            for sid in item.get("source_ids", [])
        }:
            continue
        seen.add(id(found[1]))
        ordered.append(found)
    return ordered


def _name_problems(segments: list[dict], edited: dict, confirmed: dict | None) -> list[str]:
    problems = []
    name_map = edited.get("name_map")
    if not isinstance(name_map, dict):
        return ["name_map missing"]
    needed: dict[str, set[str]] = {}
    for segment in segments:
        needed.setdefault(segment["file"], set()).add(segment["speaker"])
    for filename, labels in needed.items():
        file_map = name_map.get(filename)
        if not isinstance(file_map, dict):
            problems.append(f"missing file {filename}")
            continue
        for label in labels:
            entry = file_map.get(label)
            if not isinstance(entry, dict):
                problems.append(f"missing label {filename}:{label}")
                continue
            status = entry.get("status")
            if status not in NAME_MAP_STATUSES:
                problems.append(f"bad status {filename}:{label}")
                continue
            name = entry.get("name")
            if status == "unknown" and name not in (None, ""):
                problems.append(f"unknown has a name {filename}:{label}")
            if status == "mapped" and not required_text(name):
                problems.append(f"mapped name empty {filename}:{label}")
            origin = entry.get("origin")
            if origin not in ("caller", "editor"):
                problems.append(f"origin missing {filename}:{label}")
                continue
            if origin == "editor" and status == "mapped":
                spoken = _file_text(segments, filename)
                if not _name_in_file(name, spoken):
                    problems.append(f"editor name not in file text {filename}:{label}")
                source_id = entry.get("source_id")
                known_ids = {segment["segment_id"] for segment in segments if segment["file"] == filename}
                if source_id not in known_ids and not required_text(entry.get("evidence")):
                    problems.append(f"editor name has no evidence {filename}:{label}")
    if confirmed:
        for filename, labels in confirmed.items():
            for label, entry in labels.items():
                if entry.get("origin") != "caller":
                    continue
                current = name_map.get(filename, {}).get(label, {})
                if current.get("name") != entry.get("name") or current.get("status") != entry.get("status"):
                    problems.append(f"caller map changed {filename}:{label}")
                if current.get("origin") != "caller":
                    problems.append(f"caller origin lost {filename}:{label}")
    return problems


def _speaker_allowed(row: dict, sources: list[dict], name_map: dict) -> bool:
    speaker = str(row.get("speaker", ""))
    if speaker == "unknown":
        return True
    for source in sources:
        if speaker == source["speaker"]:
            return True
        entry = name_map.get(source["file"], {}).get(source["speaker"], {})
        mapped_name = entry.get("name")
        if entry.get("status") == "mapped" and required_text(mapped_name) and speaker == mapped_name:
            if "+" in str(source["speaker"]) and row.get("reason") != "overlap_attribution":
                return False
            return True
    return False


def review(segments: list[dict], edited: dict, confirmed: dict | None = None) -> dict:
    by_id = _by_id(segments)
    problems: list[str] = []
    seen: list[str] = []
    for item in edited.get("excluded", []):
        if not exclusion_reason_ok(item.get("reason")):
            problems.append("excluded reason empty")
    for segment_id, item in _placements(edited):
        if segment_id not in by_id:
            problems.append(f"unknown id {segment_id}")
            continue
        if item in edited.get("excluded", []) and not exclusion_reason_ok(item.get("reason")):
            continue
        seen.append(segment_id)
    expected = [row["segment_id"] for row in segments]
    if sorted(seen) != sorted(expected) or len(seen) != len(set(seen)):
        problems.append("source ids must appear exactly once")
    missing = [segment_id for segment_id in expected if segment_id not in seen]
    losses = []
    emitted_ids = []
    for key, row in ordered_exports(segments, edited):
        ids = [segment_id for segment_id in row.get("source_ids", []) if segment_id in by_id]
        if not ids:
            continue
        sources = [by_id[segment_id] for segment_id in ids]
        if len({item["speaker"] for item in sources}) > 1:
            if not (row.get("reason") == "overlap_attribution" and confidence_ok(row.get("confidence"))):
                problems.append("cross-speaker merge")
        if not _envelope_ok(row, sources):
            problems.append(f"time envelope {ids}")
        if not _overlap_ok(row, sources):
            problems.append(f"overlap attribution {ids}")
        if not _speaker_allowed(row, sources, edited.get("name_map") or {}):
            problems.append(f"speaker not allowed {ids}")
        if key == "uncertain" and row.get("speaker") != "unknown":
            problems.append("uncertain speaker must be unknown")
        emitted_ids.extend(ids)
    excluded_ids = {
        sid
        for item in edited.get("excluded", [])
        if exclusion_reason_ok(item.get("reason"))
        for sid in item.get("source_ids", [])
    }
    expected_order = [segment["segment_id"] for segment in segments if segment["segment_id"] not in excluded_ids]
    if emitted_ids != expected_order:
        problems.append("rows are out of source time order")
    for segment in segments:
        segment_id = segment["segment_id"]
        if _excluded(segment_id, edited) and segment_id not in {
            sid for row in edited.get("rows", []) + edited.get("uncertain", []) for sid in row.get("source_ids", [])
        }:
            continue
        output = _exported_text(segment_id, edited)
        corrections = [
            item for item in edited.get("corrections", []) if segment_id in item.get("source_ids", [])
        ]
        for token in number_tokens(segment["content"]) + negation_tokens(segment["content"]):
            present = token in number_tokens(output) + negation_tokens(output)
            if present:
                continue
            if _correction_ok(token, segment, output, corrections):
                continue
            losses.append({"segment_id": segment_id, "token": token})
    name_problems = _name_problems(segments, edited, confirmed)
    ok = not problems and not missing and not losses and not name_problems
    return {
        "ok": ok,
        "equivalence_proven": False,
        "missing_source_ids": missing,
        "problems": problems,
        "unannotated_losses": losses,
        "name_map_problems": name_problems,
        "warnings": [] if not losses else ["string guard is not a semantic proof"],
    }
