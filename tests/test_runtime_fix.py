import json
import subprocess
import sys
from pathlib import Path

from asr_skill.artifacts import write_json
from asr_skill.contracts import NAGISA_VERSION, SOYNLP_VERSION
from asr_skill.manifest import load_manifest, save_manifest, sha256_file
from asr_skill.pipeline import align_paths, diarize_paths
from asr_skill.runners.align import pin_mismatch

ROOT = Path(__file__).resolve().parents[1]


def test_timestamp_pins_are_declared_and_missing_pin_refuses(monkeypatch):
    import importlib.metadata as metadata

    text = (ROOT / "requirements" / "asr.txt").read_text(encoding="utf-8")
    runner = (ROOT / "src" / "asr_skill" / "runners" / "align.py").read_text(encoding="utf-8")
    assert f"nagisa=={NAGISA_VERSION}" in text
    assert f"soynlp=={SOYNLP_VERSION}" in text
    assert "pyannote" not in text
    assert "tokenize_space_lang" not in runner

    def missing(name):
        if name == "nagisa":
            raise metadata.PackageNotFoundError
        return "0"

    monkeypatch.setattr("asr_skill.runners.align.metadata.version", missing)
    message = pin_mismatch("nagisa", NAGISA_VERSION)
    assert message is not None
    assert "not installed" in message
    assert "fallback" not in message.lower()


def _completed(proc_args, jobs_key, fail_name, payload_for):
    spec = json.loads(Path(proc_args[1]).read_text(encoding="utf-8"))
    names = []
    for job in spec["jobs"]:
        source = Path(job.get("audio") or job["input"])
        names.append(source.name)
        output = Path(job["output"])
        if source.name == fail_name:
            write_json(output, {"status": "failed", "error": "injected"})
            continue
        body = {
            "status": "complete",
            "input_sha256": job["input_sha256"],
            "params_sha256": job["params_sha256"],
            "empty_speech": True,
        }
        body.update(payload_for(source.name))
        write_json(output, body)
    return names


def test_failed_align_records_only_verified_checkpoints(tmp_path, monkeypatch):
    names = ["a.wav", "b.wav", "c.wav"]
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(name.encode())
        paths.append(path)
    work = tmp_path / "work"
    work.mkdir()
    diar = {
        "files": [{"file": name, "segments": [], "speech_regions": []} for name in names],
    }
    write_json(work / "diarization.json", diar)
    save_manifest(
        work / "manifest.json",
        {
            "files": {},
            "stages": {"diarize": "complete"},
            "current_diar_sha256": sha256_file(work / "diarization.json"),
        },
    )
    previous = work / "transcript.raw.csv"
    previous.write_text("speaker,content\nold\n", encoding="utf-8")
    monkeypatch.setenv("ASR_SKILL_ASR_PYTHON", sys.executable)
    seen = []

    def fake_run(python, module, args, env=None):
        seen.append(
            _completed(
                args,
                "jobs",
                "c.wav",
                lambda name: {"rows": [{"speaker": "A", "content": "synthetic"}]},
            )
        )
        return subprocess.CompletedProcess(args, 5, "", "injected failure")

    monkeypatch.setattr("asr_skill.pipeline.run_module", fake_run)
    code, rows = align_paths(paths, work)
    assert code != 0
    assert rows == []
    assert previous.read_text(encoding="utf-8") == "speaker,content\nold\n"
    manifest = load_manifest(work / "manifest.json")
    assert manifest["stages"]["align"] == "failed"
    assert "current_align_diar_sha256" not in manifest
    complete = [
        item.get("align", {}).get("file")
        for item in manifest["files"].values()
        if item.get("align", {}).get("status") == "complete"
    ]
    assert sorted(complete) == ["a.wav", "b.wav"]
    assert seen == [["a.wav", "b.wav", "c.wav"]]

    def resume(python, module, args, env=None):
        names_seen = _completed(args, "jobs", "", lambda name: {"rows": []})
        seen.append(names_seen)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("asr_skill.pipeline.run_module", resume)
    code, rows = align_paths(paths, work)
    assert code == 0
    assert seen[-1] == ["c.wav"]
    assert (work / "transcript.raw.csv").is_file()

    paths[0].write_bytes(b"changed-input")
    code, rows = align_paths(paths, work)
    assert code == 0
    assert seen[-1] == ["a.wav"]

    monkeypatch.setattr("asr_skill.pipeline.NAGISA_VERSION", "9.9.9")
    code, rows = align_paths(paths, work)
    assert code == 0
    assert sorted(seen[-1]) == names


def test_failed_diarize_does_not_publish_partial_combined(tmp_path, monkeypatch):
    paths = []
    for name in ("a.wav", "b.wav"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        paths.append(path)
    work = tmp_path / "work"
    monkeypatch.setenv("ASR_SKILL_DIAR_PYTHON", sys.executable)
    seen = []

    def fake_run(python, module, args, env=None):
        seen.append(
            _completed(
                args,
                "jobs",
                "b.wav",
                lambda name: {"payload": {"files": [{"file": name, "segments": []}]}},
            )
        )
        return subprocess.CompletedProcess(args, 5, "", "injected")

    monkeypatch.setattr("asr_skill.pipeline.run_module", fake_run)
    code, payload = diarize_paths(paths, work)
    assert code != 0
    assert payload == {}
    assert not (work / "diarization.json").exists()
    manifest = load_manifest(work / "manifest.json")
    assert manifest["stages"]["diarize"] == "failed"
    assert "current_diar_sha256" not in manifest

    def resume(python, module, args, env=None):
        seen.append(_completed(args, "jobs", "", lambda name: {"payload": {"files": [{"file": name, "segments": []}]}}))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("asr_skill.pipeline.run_module", resume)
    code, payload = diarize_paths(paths, work)
    assert code == 0
    assert seen[-1] == ["b.wav"]
    assert [item["file"] for item in payload["files"]] == ["a.wav", "b.wav"]
