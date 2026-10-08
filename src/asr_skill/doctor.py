"""Check the verified runtimes. A missing piece is a failure, not a different model."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from asr_skill.contracts import ASR_MODEL_ID, DIARIZATION_MODEL_ID, EXIT_OK, EXIT_RUNTIME
from asr_skill.runtime import apple_silicon, asr_python, diar_python, platform_note, require_python, run_module


def _ffmpeg() -> dict:
    binary = shutil.which("ffmpeg")
    if not binary:
        return {"ok": False, "error": "ffmpeg is not on PATH"}
    proc = subprocess.run([binary, "-version"], check=False, capture_output=True, text=True)
    line = (proc.stdout or proc.stderr or "").splitlines()
    return {"ok": proc.returncode == 0, "version": line[0] if line else ""}


def _probe(python: Path | None, role: str, module: str, load: bool, extra: list[str]) -> dict:
    code, message = require_python(python, role)
    if code:
        return {"ok": False, "loaded": False, "error": message}
    args = ["--load", *extra] if load else ["--check"]
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    proc = run_module(python, module, args, env=env)
    report = {
        "ok": proc.returncode == 0,
        "loaded": load and proc.returncode == 0,
        "exit": proc.returncode,
    }
    if proc.returncode != 0:
        report["error"] = (proc.stderr or proc.stdout or "").strip()
    else:
        report["detail"] = (proc.stdout or "").strip()
    return report


def doctor(load: bool = True) -> tuple[int, dict]:
    ffmpeg = _ffmpeg()
    diar = _probe(
        diar_python(),
        "diarization",
        "asr_skill.runners.diarize",
        load,
        [],
    )
    asr_extra: list[str] = []
    if load:
        if not apple_silicon():
            asr = {
                "ok": False,
                "loaded": False,
                "error": "MLX ASR is supported on Apple Silicon only. No other ASR model will be used.",
            }
        else:
            try:
                with tempfile.TemporaryDirectory(prefix="asr-skill-") as temp:
                    wav = Path(temp) / "warmup.wav"
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", "anullsrc=r=16000:cl=mono", "-t", "0.4", str(wav),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    asr = _probe(
                        asr_python(),
                        "asr",
                        "asr_skill.runners.align",
                        True,
                        ["--warmup", str(wav)],
                    )
            except subprocess.CalledProcessError as exc:
                asr = {
                    "ok": False,
                    "loaded": False,
                    "error": exc.stderr or str(exc),
                }
    else:
        asr = _probe(asr_python(), "asr", "asr_skill.runners.align", False, asr_extra)
    payload = {
        "command": "doctor",
        "platform": platform_note(),
        "fallback": False,
        "ffmpeg": ffmpeg,
        "diar_model": DIARIZATION_MODEL_ID,
        "asr_model": ASR_MODEL_ID,
        "diar": diar,
        "asr": asr,
    }
    ok = ffmpeg["ok"] and diar.get("ok") and asr.get("ok")
    if load:
        ok = ok and diar.get("loaded") and asr.get("loaded")
    return (EXIT_OK if ok else EXIT_RUNTIME), payload


def print_doctor(load: bool = True) -> int:
    code, payload = doctor(load)
    print(json.dumps(payload, ensure_ascii=False))
    if code != EXIT_OK:
        print("doctor failed. See the error fields. No other model was tried.", file=sys.stderr)
    return code
