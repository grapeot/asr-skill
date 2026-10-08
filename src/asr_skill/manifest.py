"""Per-file checkpoints. A missing or unreadable product is not treated as done."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from asr_skill.artifacts import read_json, write_json


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def params_hash(params: dict) -> str:
    body = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def source_key(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{digest}_{path.name}"


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        return {"files": {}, "stages": {}}
    return read_json(path)


def save_manifest(path: Path, payload: dict) -> None:
    write_json(path, payload)


def read_checkpoint(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(payload, dict) or payload.get("status") != "complete":
        return None
    return payload


def should_skip(record: dict | None, input_hash: str, param_hash: str, output: Path) -> bool:
    if not record or record.get("status") != "complete":
        return False
    if record.get("input_sha256") != input_hash or record.get("params_sha256") != param_hash:
        return False
    checkpoint = read_checkpoint(output)
    if checkpoint is None:
        return False
    if checkpoint.get("input_sha256") != input_hash or checkpoint.get("params_sha256") != param_hash:
        return False
    if record.get("empty_speech"):
        return checkpoint.get("empty_speech") is True
    return True
