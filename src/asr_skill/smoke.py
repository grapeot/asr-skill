"""Build a short synthetic recording and run the real models. Identity is not certified."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from asr_skill.contracts import EXIT_RUNTIME


def _say(voice: str, text: str, dest: Path) -> None:
    subprocess.run(["say", "-v", voice, "-o", str(dest), text], check=True)


def _to_wav(source: Path, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-ar", "16000", "-ac", "1", str(dest)],
        check=True,
    )


def make_fixture(work_dir: Path) -> list[Path]:
    if shutil.which("say") is None or shutil.which("ffmpeg") is None:
        raise RuntimeError("say and ffmpeg are required to build the synthetic recording")
    work_dir.mkdir(parents=True, exist_ok=True)
    alice = work_dir / "alice.aiff"
    bob = work_dir / "bob.aiff"
    _say("Eddy", "Hello Bob. The count is 3. This is not optional.", alice)
    _say("Daniel", "No, Alice. The count is not 3.", bob)
    alice_wav = work_dir / "alice.wav"
    bob_wav = work_dir / "bob.wav"
    silence = work_dir / "silence.wav"
    _to_wav(alice, alice_wav)
    _to_wav(bob, bob_wav)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.8", str(silence)],
        check=True,
    )
    listing = work_dir / "concat.txt"
    listing.write_text(
        f"file '{alice_wav.name}'\nfile '{silence.name}'\nfile '{bob_wav.name}'\n",
        encoding="utf-8",
    )
    meeting = work_dir / "meeting_0900.wav"
    other = work_dir / "meeting_1000.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(meeting)],
        check=True,
        cwd=work_dir,
    )
    other.write_bytes(alice_wav.read_bytes())
    for item in (alice, bob, alice_wav, bob_wav, silence, listing):
        item.unlink(missing_ok=True)
    return [meeting, other]


def acoustic_notes(rows: list[dict]) -> dict:
    return {
        "row_count": len(rows),
        "files": sorted({row["file"] for row in rows}),
        "labels": sorted({row["speaker"] for row in rows}),
        "identity_verified": False,
        "note": "Non-empty text and in-range times do not prove who spoke.",
    }


def require_tools() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is missing", file=sys.stderr)
        return EXIT_RUNTIME
    return 0
