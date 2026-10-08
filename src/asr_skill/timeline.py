"""Timeline grouping. No speech models are imported here."""

from __future__ import annotations

import re

from asr_skill.contracts import (
    LONG_LINE_CHARS,
    MIN_SEGMENT_SEC,
    NEAR_SEGMENT_SEC,
    SAME_SPEAKER_MERGE_GAP_SEC,
    SHORT_LINE_CHARS,
    SHORT_MERGE_GAP_SEC,
    SPEECH_REGION_MERGE_GAP_SEC,
    UNASSIGNED_LABEL,
    UTTERANCE_GAP_SEC,
)

SENT_END_CHARS = set("。！？!?.")
_PREFIX = re.compile(r"_(\d{4})$")


def file_prefix(name: str) -> str:
    stem = name.rsplit(".", 1)[0]
    match = _PREFIX.search(stem)
    return match.group(1) if match else stem


def acoustic_labels(speaker_ids: list[int], prefix: str) -> dict[int, str]:
    seen: dict[int, str] = {}
    letters = "ABCDEFGH"
    for speaker_id in speaker_ids:
        if speaker_id not in seen:
            index = len(seen)
            letter = letters[index] if index < len(letters) else f"S{index}"
            seen[speaker_id] = f"{prefix}:{letter}"
    return seen


def merge_intervals(
    segments: list[tuple[float, float, int]],
    gap: float,
) -> list[tuple[float, float, int]]:
    merged: list[list[float | int]] = []
    for start, end, speaker in segments:
        if merged and speaker == merged[-1][2] and start - float(merged[-1][1]) <= gap:
            merged[-1][1] = max(float(merged[-1][1]), end)
        else:
            merged.append([start, end, speaker])
    return [(float(a), float(b), int(c)) for a, b, c in merged]


def smooth_diarization(
    raw: list[tuple[float, float, int]],
) -> tuple[list[dict], list[dict], list[int]]:
    kept = [item for item in raw if item[1] - item[0] >= MIN_SEGMENT_SEC]
    segments = merge_intervals(kept, SAME_SPEAKER_MERGE_GAP_SEC)
    regions = merge_intervals([(a, b, -1) for a, b, _ in segments], SPEECH_REGION_MERGE_GAP_SEC)
    speakers = sorted({item[2] for item in segments})
    segment_rows = [
        {"start": round(a, 2), "end": round(b, 2), "speaker": speaker}
        for a, b, speaker in segments
    ]
    region_rows = [{"start": round(a, 2), "end": round(b, 2)} for a, b, _ in regions]
    return segment_rows, region_rows, speakers


def assign_speaker(
    moment: float,
    segments: list[tuple[float, float, int]],
    near_sec: float = NEAR_SEGMENT_SEC,
) -> list[int]:
    hits = sorted({speaker for start, end, speaker in segments if start <= moment < end})
    if hits:
        return hits
    best_dist = None
    best_speaker = None
    for start, end, speaker in segments:
        dist = min(abs(moment - start), abs(moment - end))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_speaker = speaker
    if best_speaker is not None and best_dist is not None and best_dist <= near_sec:
        return [best_speaker]
    return []


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf"


def join_words(words: list[str]) -> str:
    parts: list[str] = []
    for word in words:
        if parts:
            prev = parts[-1]
            if prev and word and not _is_cjk(prev[-1]) and not _is_cjk(word[0]):
                parts.append(" ")
        parts.append(word)
    return "".join(parts).strip()


def _label_for(speaker_ids: list[int], labels: dict[int, str]) -> str:
    if not speaker_ids:
        return UNASSIGNED_LABEL
    return "+".join(labels[item] for item in speaker_ids)


def merge_words(
    words: list[dict],
    labels: dict[int, str],
    filename: str,
    gap_sec: float = UTTERANCE_GAP_SEC,
) -> list[dict]:
    lines: list[dict] = []
    current = None
    buf: list[str] = []
    start = None
    end = None

    def flush() -> None:
        nonlocal current, buf, start, end
        content = join_words(buf)
        if content and start is not None and end is not None:
            lines.append(
                {
                    "file": filename,
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "speaker": current or UNASSIGNED_LABEL,
                    "content": content,
                }
            )
        current = None
        buf = []
        start = None
        end = None

    for word in words:
        label = _label_for(list(word["speaker_ids"]), labels)
        if current is None or label != current or word["start"] - end > gap_sec:
            flush()
            current = label
            start = float(word["start"])
        buf.append(word["text"])
        end = float(word["end"])
    flush()
    return lines


def absorb_short_lines(
    lines: list[dict],
    short_chars: int = SHORT_LINE_CHARS,
    gap_sec: float = SHORT_MERGE_GAP_SEC,
) -> list[dict]:
    rows = [dict(item) for item in lines]
    changed = True
    while changed:
        changed = False
        for index, line in enumerate(rows):
            if len(line["content"]) >= short_chars:
                continue
            for other_index in (index + 1, index - 1):
                if other_index < 0 or other_index >= len(rows):
                    continue
                other = rows[other_index]
                if other["speaker"] != line["speaker"]:
                    continue
                if other_index == index + 1:
                    if other["start"] - line["end"] > gap_sec:
                        continue
                    other["content"] = line["content"] + other["content"]
                    other["start"] = line["start"]
                else:
                    if line["start"] - other["end"] > gap_sec:
                        continue
                    other["content"] = other["content"] + line["content"]
                    other["end"] = line["end"]
                rows.pop(index)
                changed = True
                break
            if changed:
                break
    return rows


def split_long_lines(lines: list[dict], limit: int = LONG_LINE_CHARS) -> list[dict]:
    output: list[dict] = []
    for line in lines:
        content = line["content"]
        if len(content) <= limit:
            output.append(dict(line))
            continue
        parts: list[str] = []
        buf = ""
        for char in content:
            buf += char
            if char in SENT_END_CHARS:
                parts.append(buf)
                buf = ""
        if buf:
            parts.append(buf)
        chunks: list[str] = []
        current = ""
        for part in parts:
            if current and len(current) + len(part) > limit:
                chunks.append(current)
                current = part
            else:
                current += part
        if current:
            chunks.append(current)
        span = float(line["end"]) - float(line["start"])
        total = max(len(content), 1)
        pos = 0
        for chunk in chunks:
            output.append(
                {
                    **line,
                    "content": chunk,
                    "start": round(line["start"] + span * pos / total, 2),
                    "end": round(line["start"] + span * (pos + len(chunk)) / total, 2),
                }
            )
            pos += len(chunk)
    return output


def assign_segment_ids(lines: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    output = []
    for line in lines:
        counts[line["file"]] = counts.get(line["file"], 0) + 1
        output.append({**line, "segment_id": f"{line['file']}:{counts[line['file']]:04d}"})
    return output


def words_to_segments(words: list[dict], labels: dict[int, str], filename: str) -> list[dict]:
    ordered = sorted(words, key=lambda item: (item["start"], item["end"]))
    merged = merge_words(ordered, labels, filename)
    return assign_segment_ids(split_long_lines(absorb_short_lines(merged)))
