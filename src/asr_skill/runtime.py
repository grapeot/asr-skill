"""Locate the two model interpreters. Never substitute one model for another."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

from asr_skill.contracts import EXIT_MODEL, EXIT_RUNTIME, EXIT_UNSUPPORTED, VERIFIED_PLATFORM


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _from_env_or_project(env_name: str, relative: str) -> Path | None:
    if os.environ.get(env_name):
        return Path(os.environ[env_name])
    candidate = project_root() / relative
    if candidate.is_file():
        return candidate
    return None


def diar_python() -> Path | None:
    return _from_env_or_project("ASR_SKILL_DIAR_PYTHON", ".venvs/diar/bin/python")


def asr_python() -> Path | None:
    return _from_env_or_project("ASR_SKILL_ASR_PYTHON", ".venvs/asr/bin/python")


def require_python(path: Path | None, role: str) -> tuple[int, str]:
    if path is None:
        return EXIT_RUNTIME, (
            f"{role} interpreter is missing. Run `asr-skill init` in this checkout. "
            "No other model will be used."
        )
    if not path.is_file():
        return (
            EXIT_RUNTIME,
            f"{role} interpreter does not exist: {path}. Run asr-skill init. No other model will be used.",
        )
    return 0, ""


def run_module(
    python: Path,
    module: str,
    args: list[str],
    env: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(python), "-m", module, *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def emit_failure(proc: subprocess.CompletedProcess[str], role: str) -> int:
    sys.stderr.write(proc.stderr or "")
    if proc.stdout:
        sys.stderr.write(proc.stdout)
    sys.stderr.write(f"{role} failed with exit {proc.returncode}. The error above was kept. No retry.\n")
    if proc.returncode in {EXIT_RUNTIME, EXIT_UNSUPPORTED, EXIT_MODEL}:
        return proc.returncode
    return EXIT_MODEL


def platform_note() -> str:
    return VERIFIED_PLATFORM
