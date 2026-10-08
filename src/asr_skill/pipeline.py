"""Batch diarization and alignment. Each model loads once per batch."""

from __future__ import annotations

import sys
from pathlib import Path

from asr_skill.artifacts import csv_fields, read_json, replace_generation, write_csv, write_json, write_jsonl
from asr_skill.contracts import (
    ASR_MODEL_ID,
    AUDIO_SUFFIXES,
    DIAR_TRANSFORMERS_COMMIT,
    DIARIZATION_MODEL_ID,
    EXIT_MODEL,
    EXIT_OK,
    EXIT_USAGE,
    MLX_QWEN_VERSION,
)
from asr_skill.manifest import (
    load_manifest,
    params_hash,
    read_checkpoint,
    save_manifest,
    sha256_file,
    should_skip,
    source_key,
)
from asr_skill.runtime import asr_python, diar_python, emit_failure, require_python, run_module

CLEAN_NAMES = ("transcript.readable.csv", "source_map.json", "name_map.json")


def discover_audio(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    found = [
        item for item in sorted(path.iterdir())
        if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES
    ]
    if found:
        return found
    raw = path / "raw"
    if raw.is_dir():
        return [
            item for item in sorted(raw.iterdir())
            if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES
        ]
    return []


def discover_date_dir(date_dir: Path) -> tuple[list[Path], str]:
    root = [
        item for item in sorted(date_dir.iterdir())
        if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES
    ] if date_dir.is_dir() else []
    if root:
        return root, "."
    raw = date_dir / "raw"
    if raw.is_dir():
        files = [
            item for item in sorted(raw.iterdir())
            if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES
        ]
        if files:
            return files, "raw"
    return [], "."


def _reject_duplicate_names(paths: list[Path]) -> str | None:
    seen: dict[str, Path] = {}
    for path in paths:
        previous = seen.get(path.name)
        if previous is not None and previous.resolve() != path.resolve():
            return path.name
        seen[path.name] = path
    return None


def _checkpoint(work_dir: Path, key: str, stage: str) -> Path:
    return work_dir / "checkpoints" / f"{key}.{stage}.json"


def _pin_params(stage: str, model_id: str, extra: dict | None = None) -> dict:
    payload = {
        "stage": stage,
        "model": model_id,
        "transformers_commit": DIAR_TRANSFORMERS_COMMIT,
        "mlx_qwen": MLX_QWEN_VERSION,
    }
    if extra:
        payload.update(extra)
    return payload


def retire_clean(work_dir: Path) -> None:
    from asr_skill.artifacts import write_atomic
    import time

    present = [work_dir / name for name in CLEAN_NAMES if (work_dir / name).exists()]
    editor = work_dir / "editor_task"
    if editor.exists():
        present.append(editor)
    if not present:
        return
    history = work_dir / "history" / time.strftime("%Y%m%dT%H%M%SZ")
    history.mkdir(parents=True, exist_ok=True)
    for path in present:
        path.rename(history / path.name)
    write_atomic(work_dir / "clean_stale.txt", "acoustic outputs changed; previous clean draft is in history\n")


def diarize_paths(
    paths: list[Path],
    work_dir: Path,
    model_id: str = DIARIZATION_MODEL_ID,
    date_dir: str = ".",
    audio_dir: str = ".",
) -> tuple[int, dict]:
    duplicate = _reject_duplicate_names(paths)
    if duplicate:
        print(f"duplicate basename {duplicate}; refusing to share a checkpoint", file=sys.stderr)
        return EXIT_USAGE, {}
    python = diar_python()
    code, message = require_python(python, "diarization")
    if code:
        print(message, file=sys.stderr)
        return code, {}
    if model_id != DIARIZATION_MODEL_ID:
        print(f"refusing model {model_id}", file=sys.stderr)
        return EXIT_MODEL, {}
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    param = params_hash(_pin_params("diarize", model_id))
    jobs = []
    skipped = []
    for source in paths:
        key = source_key(source)
        digest = sha256_file(source)
        output = _checkpoint(work_dir, key, "diar")
        record = manifest.setdefault("files", {}).setdefault(key, {})
        if should_skip(record.get("diarize"), digest, param, output):
            skipped.append(read_checkpoint(output)["payload"]["files"][0])
            continue
        jobs.append(
            {
                "input": str(source),
                "output": str(output),
                "key": key,
                "file": source.name,
                "input_sha256": digest,
                "params_sha256": param,
            }
        )
    reran = bool(jobs)
    if jobs:
        job_path = work_dir / "checkpoints" / "diar_jobs.json"
        write_json(job_path, {"model": model_id, "date_dir": date_dir, "audio_dir": audio_dir, "jobs": jobs})
        proc = run_module(python, "asr_skill.runners.diarize", ["--jobs", str(job_path)])
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr or "")
            manifest.setdefault("stages", {})["diarize"] = "failed"
            save_manifest(manifest_path, manifest)
            return emit_failure(proc, "diarize"), {}
    files = []
    for source in paths:
        key = source_key(source)
        output = _checkpoint(work_dir, key, "diar")
        checkpoint = read_checkpoint(output)
        if checkpoint is None or checkpoint.get("status") != "complete":
            manifest.setdefault("stages", {})["diarize"] = "failed"
            save_manifest(manifest_path, manifest)
            print(f"diarization checkpoint missing for {source.name}", file=sys.stderr)
            return EXIT_MODEL, {}
        record = manifest.setdefault("files", {}).setdefault(key, {})
        record["diarize"] = {
            "status": "complete",
            "input_sha256": sha256_file(source),
            "params_sha256": param,
            "empty_speech": checkpoint.get("empty_speech", False),
            "file": source.name,
        }
        files.append(checkpoint["payload"]["files"][0])
    combined = {
        "date_dir": date_dir,
        "audio_dir": audio_dir,
        "model": model_id,
        "files": files,
    }
    staged = work_dir / "checkpoints" / "diarization.staged.json"
    write_json(staged, combined)
    replace_generation([(staged, work_dir / "diarization.json")])
    digest = sha256_file(work_dir / "diarization.json")
    manifest.setdefault("stages", {})["diarize"] = "complete"
    manifest["current_diar_sha256"] = digest
    manifest["params"] = _pin_params("diarize", model_id)
    save_manifest(manifest_path, manifest)
    if reran:
        retire_clean(work_dir)
    return EXIT_OK, combined


def align_paths(
    paths: list[Path],
    work_dir: Path,
    model_id: str = ASR_MODEL_ID,
) -> tuple[int, list[dict]]:
    duplicate = _reject_duplicate_names(paths)
    if duplicate:
        print(f"duplicate basename {duplicate}; refusing to share a checkpoint", file=sys.stderr)
        return EXIT_USAGE, []
    python = asr_python()
    code, message = require_python(python, "asr")
    if code:
        print(message, file=sys.stderr)
        return code, []
    if model_id != ASR_MODEL_ID:
        print(f"refusing model {model_id}", file=sys.stderr)
        return EXIT_MODEL, []
    manifest = load_manifest(work_dir / "manifest.json")
    if manifest.get("stages", {}).get("diarize") != "complete":
        print("diarization is not a completed current result. Refusing to align.", file=sys.stderr)
        return EXIT_USAGE, []
    diar_path = work_dir / "diarization.json"
    if not diar_path.is_file():
        print("diarization.json is missing. Refusing to align.", file=sys.stderr)
        return EXIT_USAGE, []
    diar_sha = sha256_file(diar_path)
    if diar_sha != manifest.get("current_diar_sha256"):
        print("diarization.json does not match the completed run. Refusing to align.", file=sys.stderr)
        return EXIT_USAGE, []
    combined = read_json(diar_path)
    by_name = {item["file"]: item for item in combined.get("files", [])}
    if set(by_name) != {path.name for path in paths}:
        print("diarization file set does not match this input set. Refusing to align.", file=sys.stderr)
        return EXIT_USAGE, []
    param = params_hash(_pin_params("align", model_id, {"diar_sha256": diar_sha}))
    jobs = []
    for source in paths:
        key = source_key(source)
        digest = sha256_file(source)
        output = _checkpoint(work_dir, key, "align")
        record = manifest.setdefault("files", {}).setdefault(key, {})
        if should_skip(record.get("align"), digest, param, output):
            continue
        info = by_name[source.name]
        one = work_dir / "checkpoints" / f"{key}.one.json"
        write_json(one, {**combined, "files": [info]})
        jobs.append(
            {
                "audio": str(source),
                "diarization": str(one),
                "output": str(output),
                "key": key,
                "input_sha256": digest,
                "params_sha256": param,
            }
        )
    if jobs:
        retire_clean(work_dir)
        job_path = work_dir / "checkpoints" / "align_jobs.json"
        write_json(job_path, {"model": model_id, "jobs": jobs})
        proc = run_module(python, "asr_skill.runners.align", ["--jobs", str(job_path)])
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr or "")
            manifest.setdefault("stages", {})["align"] = "failed"
            save_manifest(work_dir / "manifest.json", manifest)
            return emit_failure(proc, "align"), []
    rows: list[dict] = []
    for source in paths:
        key = source_key(source)
        output = _checkpoint(work_dir, key, "align")
        checkpoint = read_checkpoint(output)
        if checkpoint is None:
            print(f"align checkpoint missing for {source.name}", file=sys.stderr)
            return EXIT_MODEL, []
        record = manifest.setdefault("files", {}).setdefault(key, {})
        record["align"] = {
            "status": "complete",
            "input_sha256": sha256_file(source),
            "params_sha256": param,
            "empty_speech": checkpoint.get("empty_speech", False),
            "file": source.name,
        }
        rows.extend(checkpoint.get("rows") or [])
    staged_rich = work_dir / "checkpoints" / "rich.staged.jsonl"
    staged_raw = work_dir / "checkpoints" / "raw.staged.csv"
    staged_timed = work_dir / "checkpoints" / "timed.staged.csv"
    write_jsonl(staged_rich, rows)
    write_csv(staged_raw, rows, csv_fields("legacy"))
    write_csv(staged_timed, rows, csv_fields("timed"))
    replace_generation(
        [
            (staged_rich, work_dir / "transcript.rich.jsonl"),
            (staged_raw, work_dir / "transcript.raw.csv"),
            (staged_timed, work_dir / "transcript.timed.csv"),
        ]
    )
    manifest.setdefault("stages", {})["align"] = "complete"
    manifest["current_align_diar_sha256"] = diar_sha
    save_manifest(work_dir / "manifest.json", manifest)
    return EXIT_OK, rows


def audio_from_diarization(date_dir: Path, payload: dict) -> list[Path]:
    audio_dir = payload.get("audio_dir", ".")
    root = date_dir if audio_dir in (".", "") else date_dir / audio_dir
    paths = []
    for item in payload.get("files", []):
        path = root / item["file"]
        if not path.is_file():
            raise FileNotFoundError(f"audio listed in diarization is missing: {item['file']}")
        paths.append(path)
    return paths
