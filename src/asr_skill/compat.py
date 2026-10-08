"""Old date-directory flags. Checkpoints go to a separate work directory."""

from __future__ import annotations

from pathlib import Path

from asr_skill.contracts import ASR_MODEL_ID, DIARIZATION_MODEL_ID, EXIT_OK, EXIT_USAGE
from asr_skill.pipeline import align_paths, audio_from_diarization, diarize_paths, discover_date_dir


def _owned(path: Path) -> bool:
    return path.with_name(path.name + ".asr-skill-owned").is_file()


def _recorded_hash(path: Path) -> str | None:
    sidecar = path.with_name(path.name + ".asr-skill-sha256")
    if not sidecar.is_file():
        return None
    return sidecar.read_text(encoding="utf-8").strip()


def _archive(path: Path) -> None:
    import time

    history = path.parent / "history" / time.strftime("%Y%m%dT%H%M%SZ")
    history.mkdir(parents=True, exist_ok=True)
    path.rename(history / path.name)


def _prepare_output(path: Path) -> int | None:
    if not path.exists():
        return None
    from asr_skill.manifest import sha256_file

    recorded = _recorded_hash(path)
    if not _owned(path) or recorded is None:
        print(f"refusing to overwrite existing file: {path.name}", file=__import__("sys").stderr)
        return EXIT_USAGE
    if sha256_file(path) != recorded:
        _archive(path)
    return None


def _mark_owned(path: Path) -> None:
    from asr_skill.manifest import sha256_file

    path.with_name(path.name + ".asr-skill-owned").write_text("asr-skill\n", encoding="utf-8")
    path.with_name(path.name + ".asr-skill-sha256").write_text(sha256_file(path) + "\n", encoding="utf-8")


def diarize_date_dir(
    date_dir: str,
    output: str | None = None,
    model: str = DIARIZATION_MODEL_ID,
    work_dir: str | None = None,
) -> int:
    root = Path(date_dir)
    paths, audio_dir = discover_date_dir(root)
    if not paths:
        return EXIT_USAGE
    dest = Path(output) if output else root / "diarization.json"
    refused = _prepare_output(dest)
    if refused:
        return refused
    work = Path(work_dir) if work_dir else dest.parent / ".asr-skill-work"
    if work.resolve() == root.resolve():
        print("work directory must not be the date directory", file=__import__("sys").stderr)
        return EXIT_USAGE
    code, _payload = diarize_paths(paths, work, model, date_dir=str(root), audio_dir=audio_dir)
    if code != EXIT_OK:
        return code
    produced = work / "diarization.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(produced.read_text(encoding="utf-8"), encoding="utf-8")
    _mark_owned(dest)
    return EXIT_OK


def align_date_dir(
    date_dir: str,
    diarization: str,
    output: str,
    rich_output: str | None = None,
    model: str = ASR_MODEL_ID,
    work_dir: str | None = None,
) -> int:
    from asr_skill.artifacts import csv_fields, read_json, write_csv, write_jsonl

    payload = read_json(Path(diarization))
    try:
        paths = audio_from_diarization(Path(date_dir), payload)
    except FileNotFoundError as exc:
        print(str(exc), file=__import__("sys").stderr)
        return EXIT_USAGE
    dest = Path(output)
    rich = Path(rich_output) if rich_output else dest.with_suffix(".rich.jsonl")
    for path in (dest, rich):
        refused = _prepare_output(path)
        if refused:
            return refused
    work = Path(work_dir) if work_dir else dest.parent / ".asr-skill-work"
    if work.resolve() == Path(date_dir).resolve():
        print("work directory must not be the date directory", file=__import__("sys").stderr)
        return EXIT_USAGE
    work.mkdir(parents=True, exist_ok=True)
    target = work / "diarization.json"
    if Path(diarization).resolve() != target.resolve():
        target.write_text(Path(diarization).read_text(encoding="utf-8"), encoding="utf-8")
    from asr_skill.manifest import load_manifest, save_manifest, sha256_file

    manifest = load_manifest(work / "manifest.json")
    manifest.setdefault("stages", {})["diarize"] = "complete"
    manifest["current_diar_sha256"] = sha256_file(target)
    save_manifest(work / "manifest.json", manifest)
    code, rows = align_paths(paths, work, model)
    if code != EXIT_OK:
        return code
    write_csv(dest, rows, csv_fields("legacy"))
    write_jsonl(rich, rows)
    _mark_owned(dest)
    _mark_owned(rich)
    return EXIT_OK
