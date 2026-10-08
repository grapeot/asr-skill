"""Reject a single file before a model is loaded. This is not a chunker."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from asr_skill.contracts import MAX_INPUT_SECONDS


def max_seconds() -> float:
    raw = os.environ.get("ASR_SKILL_MAX_SECONDS")
    if not raw:
        return float(MAX_INPUT_SECONDS)
    return float(raw)


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
    return float(proc.stdout.strip())


def over_limit(paths: list[Path]) -> str | None:
    limit = max_seconds()
    for path in paths:
        try:
            seconds = probe_duration(path)
        except (RuntimeError, ValueError):
            continue
        if seconds > limit:
            return (
                f"{path.name} is {seconds:.0f}s, over the {limit:.0f}s single-file limit. "
                "Split it into separate files or set ASR_SKILL_MAX_SECONDS. "
                "A speaker letter does not continue across slices. "
                "A long day made of several files is not one file over the limit."
            )
    return None
