"""Create the two verified environments. One attempt; no model substitution."""

from __future__ import annotations

import shutil
import subprocess
import sys

from asr_skill.contracts import ASR_MODEL_ID, DIARIZATION_MODEL_ID, EXIT_NETWORK, EXIT_OK, EXIT_RUNTIME
from asr_skill.doctor import print_doctor
from asr_skill.runtime import project_root


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _install(python: str, requirements: str) -> int:
    proc = _run(["uv", "pip", "install", "--python", python, "-r", requirements])
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
        sys.stderr.write(proc.stdout or "")
        print("install failed once. Not retrying and not selecting another model.", file=sys.stderr)
        return EXIT_NETWORK
    proc = _run(["uv", "pip", "install", "--python", python, "-e", str(project_root())])
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
        print("editable install failed. Not retrying.", file=sys.stderr)
        return EXIT_RUNTIME
    return EXIT_OK


def init_runtimes(download: bool = True) -> int:
    if shutil.which("uv") is None:
        print("uv is not on PATH", file=sys.stderr)
        return EXIT_RUNTIME
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not on PATH", file=sys.stderr)
        return EXIT_RUNTIME
    root = project_root()
    diar = root / ".venvs" / "diar"
    asr = root / ".venvs" / "asr"
    if not (diar / "bin" / "python").is_file():
        proc = _run(["uv", "venv", "--python", "3.12", str(diar)])
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr or "")
            return EXIT_RUNTIME
    if not (asr / "bin" / "python").is_file():
        proc = _run(["uv", "venv", "--python", "3.12", str(asr)])
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr or "")
            return EXIT_RUNTIME
    code = _install(str(diar / "bin" / "python"), str(root / "requirements" / "diar.txt"))
    if code != EXIT_OK:
        return code
    code = _install(str(asr / "bin" / "python"), str(root / "requirements" / "asr.txt"))
    if code != EXIT_OK:
        return code
    if download:
        for python, model in (
            (diar / "bin" / "python", DIARIZATION_MODEL_ID),
            (asr / "bin" / "python", ASR_MODEL_ID),
        ):
            proc = _run(
                [
                    str(python),
                    "-c",
                    "from huggingface_hub import snapshot_download; "
                    f"snapshot_download({model!r})",
                ]
            )
            if proc.returncode != 0:
                sys.stderr.write(proc.stderr or "")
                print(f"download failed for {model}. Not retrying.", file=sys.stderr)
                return EXIT_NETWORK
    else:
        print(
            "dependency install may use the network. Model weights will not be downloaded.",
            file=sys.stderr,
        )
    return print_doctor(load=True)
