from pathlib import Path

from asr_skill.artifacts import write_atomic
from asr_skill.manifest import should_skip


def test_missing_output_is_not_skipped(tmp_path: Path):
    output = tmp_path / "out.json"
    record = {"status": "complete", "input_sha256": "abc", "params_sha256": "def"}
    assert should_skip(record, "abc", "def", output) is False
    output.write_text(
        '{"status":"complete","input_sha256":"abc","params_sha256":"def","rows":[{"content":"ok"}]}\n',
        encoding="utf-8",
    )
    assert should_skip(record, "abc", "def", output) is True
    assert should_skip(record, "changed", "def", output) is False
    failed = {"status": "failed", "input_sha256": "abc", "params_sha256": "def"}
    assert should_skip(failed, "abc", "def", output) is False


def test_failed_replace_leaves_the_previous_file(tmp_path: Path):
    path = tmp_path / "transcript.csv"
    path.write_text("speaker,content\n0900:A,keep\n", encoding="utf-8")
    try:
        raise RuntimeError("validation failed")
    except RuntimeError:
        pass
    assert path.read_text(encoding="utf-8").startswith("speaker,content")
    write_atomic(path, "speaker,content\n0900:A,next\n")
    assert "next" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "transcript.csv.tmp").exists()
