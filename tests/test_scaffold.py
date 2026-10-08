import subprocess
import sys
from pathlib import Path

import pytest

import asr_skill
from asr_skill.cli import main
from asr_skill.contracts import EXIT_RUNTIME, EXIT_USAGE

ROOT = Path(__file__).resolve().parents[1]


def test_package_version():
    assert asr_skill.__version__ == "0.1.0"
    assert asr_skill.IMPLEMENTED is True
    assert asr_skill.PHASE == "local"


def test_version_command(capsys):
    assert main(["version"]) == 0
    text = capsys.readouterr().out
    assert "asr-skill 0.1.0" in text
    assert "scaffold" not in text
    assert "implemented=false" not in text


def test_help_describes_local_models():
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_missing_audio_is_usage(capsys):
    code = main(["diarize", "--input", "/path/to/recordings", "--work-dir", "/path/to/asr-work"])
    assert code == EXIT_USAGE
    assert "no audio" in capsys.readouterr().err


def test_missing_runtime_does_not_fall_back(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASR_SKILL_DIAR_PYTHON", "/path/to/missing-diar-python")
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    code = main(["diarize", "--input", str(audio), "--work-dir", str(tmp_path / "work")])
    assert code == EXIT_RUNTIME
    err = capsys.readouterr().err
    assert "No other model" in err
    assert "init" in err


def test_clean_without_editor_does_not_regex(tmp_path, capsys):
    rich = tmp_path / "rich.jsonl"
    rich.write_text('{"segment_id":"a","content":"Hi."}\n', encoding="utf-8")
    code = main(
        [
            "clean",
            "--rich",
            str(rich),
            "--output-csv",
            str(tmp_path / "out.csv"),
            "--source-map",
            str(tmp_path / "map.json"),
            "--name-map",
            str(tmp_path / "names.json"),
            "--editor-cmd",
            "/path/to/missing-editor",
        ]
    )
    assert code == EXIT_RUNTIME
    assert "regex" in capsys.readouterr().err
    assert not (tmp_path / "out.csv").exists()


def test_module_entrypoint():
    proc = subprocess.run(
        [sys.executable, "-m", "asr_skill", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "0.1.0" in proc.stdout


def test_launcher_script():
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "asr-skill"), "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "0.1.0" in proc.stdout
