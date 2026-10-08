"""Generic checks for files that belong in a public source checkout.

The scan is limited to source, docs, skills, tests, examples, scripts,
.github, and root metadata. It does not walk virtualenvs, model caches, or
local runtime data. This module is omitted from the tree scan because it
contains the generic markers it searches for.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("src", "docs", "skills", "tests", "examples", "scripts", ".github")
SCAN_FILES = (
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "pyproject.toml",
    ".gitignore",
    ".env.example",
)
SKIP_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "models",
    "data",
    "logs",
    "cache",
}
MEDIA_SUFFIXES = {".m4a", ".mp3", ".wav", ".flac", ".mp4", ".mov", ".pt", ".safetensors"}
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}

_USER_PATH = re.compile(r"/Users/|/home/|[A-Za-z]:[\\/]Users[\\/]")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
)
_CREDENTIAL_URI = re.compile(r"op://")
_ASSIGNED_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"][^'\"]+['\"]"
)
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
)
_INTRANET_IP = re.compile(
    r"(?<![0-9])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|169\.254(?:\.\d{1,3}){2})(?![0-9])"
)
_INTRANET_HOST = re.compile(
    r"(?i)(?<![A-Za-z0-9-])(?:[A-Za-z0-9-]+\.)+"
    r"(?:local|internal|corp|lan|home\.arpa|ts\.net)\b"
)


def _publishable_files() -> list[Path]:
    found: list[Path] = []
    for name in SCAN_FILES:
        path = ROOT / name
        if path.is_file():
            found.append(path)
    for dirname in SCAN_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name == "test_public_hygiene.py":
                continue
            found.append(path)
    return found


def _path_hits(text: str) -> list[str]:
    return _USER_PATH.findall(text)


def _key_hits(text: str) -> list[str]:
    return _PRIVATE_KEY.findall(text) + _CREDENTIAL_URI.findall(text)


def _secret_hits(text: str) -> list[str]:
    return _ASSIGNED_SECRET.findall(text)


def _email_hits(text: str) -> list[str]:
    hits = []
    for match in _EMAIL.finditer(text):
        domain = match.group(2).lower().rstrip(".")
        if domain not in ALLOWED_EMAIL_DOMAINS:
            hits.append(match.group(0))
    return hits


def _intranet_hits(text: str) -> list[str]:
    return _INTRANET_IP.findall(text) + _INTRANET_HOST.findall(text)


def test_scan_scope_skips_local_runtime():
    rels = [path.relative_to(ROOT).as_posix() for path in _publishable_files()]
    assert rels
    assert "tests/test_public_hygiene.py" not in rels
    assert all(".venv" not in Path(rel).parts for rel in rels)
    assert all("models" not in Path(rel).parts for rel in rels)
    assert ".env.example" in rels
    assert any(rel.startswith("src/") for rel in rels)


def test_detectors_accept_placeholders_and_reject_generic_leaks():
    assert _path_hits("/path/to/recordings") == []
    assert _path_hits("/Users/alice/notes.txt")
    assert _path_hits("/home/bob/notes.txt")
    assert _path_hits("C:\\Users\\alice\\notes.txt")
    assert _key_hits("-----BEGIN PRIVATE KEY-----\n")
    assert _key_hits("op://your-vault/your-item/your-field")
    assert _secret_hits("api_key = 'replace-with-your-real-key'")
    assert _email_hits("alice@example.com") == []
    assert _email_hits("bob@example.net") == []
    assert _email_hits("carol@example.org") == []
    assert _email_hits("alice@other.invalid") == ["alice@other.invalid"]
    assert _intranet_hits("a gap of 10.0 seconds") == []
    assert _intranet_hits("10.1.2.3")
    assert _intranet_hits("192.168.0.2")
    assert _intranet_hits("172.16.0.4")
    assert _intranet_hits("printer.local")
    assert _intranet_hits("https://github.com/grapeot/asr-skill") == []


def test_publishable_tree_has_no_generic_private_markers():
    hits: list[str] = []
    for path in _publishable_files():
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix in MEDIA_SUFFIXES:
            hits.append(f"media:{rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, found in (
            ("path", _path_hits(text)),
            ("key", _key_hits(text)),
            ("secret", _secret_hits(text)),
            ("email", _email_hits(text)),
            ("intranet", _intranet_hits(text)),
        ):
            for item in found:
                hits.append(f"{label}:{rel}:{item}")
    assert hits == []
