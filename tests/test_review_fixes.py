import json
from pathlib import Path

import pytest

from asr_skill.clean import apply_edit
from asr_skill.cli import main
from asr_skill.contracts import ASR_MODEL_ID, EXIT_OK
from asr_skill.pipeline import discover_date_dir
from asr_skill.validate import review


def _segment(segment_id: str, speaker: str, content: str, start: float, end: float) -> dict:
    return {
        "segment_id": segment_id,
        "file": segment_id.split(":")[0],
        "start": start,
        "end": end,
        "speaker": speaker,
        "content": content,
    }


def _map(segments: list[dict]) -> dict:
    payload: dict[str, dict] = {}
    for segment in segments:
        payload.setdefault(segment["file"], {})[segment["speaker"]] = {
            "name": None,
            "status": "unknown",
            "origin": "editor",
        }
    return payload


def _row(segment: dict, content: str | None = None, speaker: str | None = None) -> dict:
    return {
        "source_ids": [segment["segment_id"]],
        "start": segment["start"],
        "end": segment["end"],
        "speaker": speaker or segment["speaker"],
        "content": segment["content"] if content is None else content,
    }


def test_smoke_dispatch_uses_the_asr_model(tmp_path, monkeypatch):
    monkeypatch.setattr("asr_skill.smoke.make_fixture", lambda _work: [tmp_path / "meeting_0900.wav"])
    monkeypatch.setattr("asr_skill.pipeline.diarize_paths", lambda *args, **kwargs: (EXIT_OK, {}))
    seen = {}

    def fake_align(paths, work, model_id=ASR_MODEL_ID):
        seen["model_id"] = model_id
        return EXIT_OK, [
            {
                "file": "meeting_0900.wav",
                "speaker": "0900:A",
                "content": "Hello",
                "start": 0.0,
                "end": 1.0,
            }
        ]

    monkeypatch.setattr("asr_skill.pipeline.align_paths", fake_align)
    code = main(["smoke", "--work-dir", str(tmp_path / "work")])
    assert seen["model_id"] == ASR_MODEL_ID
    assert code == EXIT_OK


def test_uncertain_row_is_kept_in_the_readable_csv():
    segment = _segment("meeting_0900.wav:0001", "0900:A+0900:B", "not 3", 0.0, 1.0)
    edited = {
        "rows": [],
        "uncertain": [
            {
                "source_ids": [segment["segment_id"]],
                "speaker": "unknown",
                "content": "not 3",
                "start": 0.0,
                "end": 1.0,
                "reason": "unsure",
            }
        ],
        "excluded": [],
        "corrections": [],
        "name_map": _map([segment]),
    }
    result = review([segment], edited)
    assert result["ok"] is True
    rows, _result, _extras = apply_edit([segment], edited, "timed")
    assert rows[0]["speaker"] == "unknown"
    assert rows[0]["content"] == "not 3"


def test_overlap_label_can_use_its_mapped_name_without_reason():
    segment = _segment("meeting_0900.wav:0001", "0900:A+0900:B", "Hello Alice.", 0.0, 1.0)
    edited = {
        "rows": [_row(segment, speaker="Alice")],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "meeting_0900.wav": {
                "0900:A+0900:B": {
                    "name": "Alice",
                    "status": "mapped",
                    "origin": "editor",
                    "source_id": segment["segment_id"],
                }
            }
        },
    }
    assert review([segment], edited)["ok"] is True
    edited["rows"][0]["reason"] = "overlap_attribution"
    edited["rows"][0]["confidence"] = "low"
    assert review([segment], edited)["ok"] is True


def test_editor_can_replace_caller_mapping():
    segment = _segment("meeting_0900.wav:0001", "0900:A", "Hello Bob.", 0.0, 1.0)
    confirmed = {
        "meeting_0900.wav": {
            "0900:A": {"name": "Alice", "status": "mapped", "origin": "caller"}
        }
    }
    invented = {
        "rows": [_row(segment, speaker="Charlie")],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "meeting_0900.wav": {
                "0900:A": {"name": "Charlie", "status": "mapped", "origin": "editor"}
            }
        },
    }
    assert review([segment], invented, confirmed)["ok"] is True


def test_token_substrings_and_empty_corrections_are_not_checked():
    segment = _segment("meeting_0900.wav:0001", "0900:A", "See the note and 13.", 0.0, 1.0)
    edited = {
        "rows": [_row(segment, content="See the note and 1.")],
        "uncertain": [],
        "excluded": [],
        "corrections": [
            {"source_ids": [segment["segment_id"]], "before": "note", "after": "", "reason": "filler"}
        ],
        "name_map": _map([segment]),
    }
    result = review([segment], edited)
    assert result["ok"] is True
    assert result["unannotated_losses"] == []


def test_repeated_sources_and_omitted_sources_are_allowed():
    first = _segment("a.wav:0001", "0900:A", "One.", 0.0, 1.0)
    second = _segment("a.wav:0002", "0900:A", "Two.", 1.0, 2.0)
    edited = {
        "rows": [
            _row(second),
            {
                "source_ids": ["missing", second["segment_id"]],
                "start": 1.0,
                "end": 2.0,
                "speaker": "0900:A",
                "content": "Two.",
            },
        ],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": _map([first, second]),
    }
    rows, result, _extras = apply_edit([first, second], edited, "timed")
    assert result["ok"] is True
    assert len(rows) == 2


def test_align_refuses_a_changed_diarization_file(tmp_path, monkeypatch):
    from asr_skill.artifacts import write_json
    from asr_skill.manifest import save_manifest, sha256_file
    from asr_skill.pipeline import align_paths

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    work = tmp_path / "work"
    work.mkdir()
    write_json(
        work / "diarization.json",
        {
            "model": "nvidia/Nemotron-3-Diarization",
            "files": [{"file": "clip.wav", "segments": [], "speech_regions": []}],
        },
    )
    save_manifest(
        work / "manifest.json",
        {"files": {}, "stages": {"diarize": "complete"}, "current_diar_sha256": "stale"},
    )
    monkeypatch.setenv("ASR_SKILL_ASR_PYTHON", "/path/to/missing-asr-python")
    code, rows = align_paths([audio], work)
    assert code != 0
    assert rows == []
    assert sha256_file(work / "diarization.json") != "stale"


def test_raw_discovery_keeps_audio_dir(tmp_path: Path):
    day = tmp_path / "day"
    raw = day / "raw"
    raw.mkdir(parents=True)
    (raw / "clip.wav").write_bytes(b"R")
    paths, audio_dir = discover_date_dir(day)
    assert audio_dir == "raw"
    assert paths[0].name == "clip.wav"


def test_duplicate_basename_is_rejected(tmp_path, monkeypatch):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "clip.wav").write_bytes(b"a")
    (right / "clip.wav").write_bytes(b"b")
    monkeypatch.setenv("ASR_SKILL_DIAR_PYTHON", "/path/to/missing-diar-python")
    code = main(
        [
            "diarize",
            "--input",
            str(left),
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )
    assert code != 0
    from asr_skill.pipeline import diarize_paths

    code, payload = diarize_paths([left / "clip.wav", right / "clip.wav"], tmp_path / "work")
    assert code != 0
    assert payload == {}


def test_doctor_reports_ffmpeg_warmup_failure(monkeypatch):
    import subprocess

    from asr_skill.doctor import doctor

    monkeypatch.setattr("asr_skill.doctor._ffmpeg", lambda: {"ok": True, "version": "ffmpeg test"})
    monkeypatch.setattr(
        "asr_skill.doctor._probe",
        lambda *args, **kwargs: {"ok": True, "loaded": True, "detail": "ok"},
    )
    monkeypatch.setattr("asr_skill.doctor.apple_silicon", lambda: True)

    def fail_ffmpeg(*args, **kwargs):
        raise subprocess.CalledProcessError(183, args, stderr="Invalid data found")

    monkeypatch.setattr("asr_skill.doctor.subprocess.run", fail_ffmpeg)
    code, payload = doctor(load=True)
    assert code != 0
    assert "Invalid data found" in payload["asr"]["error"]


def test_middle_uncertain_stays_in_source_order():
    segments = [
        _segment("a.wav:0001", "0900:A", "Hello", 0.0, 1.0),
        _segment("a.wav:0002", "0900:A+0900:B", "maybe", 1.0, 2.0),
        _segment("a.wav:0003", "0900:B", "No", 2.0, 3.0),
    ]
    edited = {
        "rows": [_row(segments[0]), _row(segments[2])],
        "uncertain": [
            {
                "source_ids": ["a.wav:0002"],
                "start": 1.0,
                "end": 2.0,
                "speaker": "unknown",
                "content": "maybe",
                "reason": "unsure",
            }
        ],
        "excluded": [],
        "corrections": [],
        "name_map": _map(segments),
    }
    assert review(segments, edited)["ok"] is True
    rows, _result, _extras = apply_edit(segments, edited, "timed")
    assert [row["content"] for row in rows] == ["Hello", "maybe", "No"]
    assert rows[1]["speaker"] == "unknown"


@pytest.mark.parametrize("reason", [None, "", "   ", 123, True, False, [], {}])
def test_exclusion_reason_is_not_checked(reason):
    segment = _segment("a.wav:0001", "0900:A", "Hello.", 0.0, 1.0)
    edited = {
        "rows": [],
        "uncertain": [],
        "excluded": [{"source_ids": [segment["segment_id"]], "reason": reason}],
        "corrections": [],
        "name_map": _map([segment]),
    }
    assert review([segment], edited)["ok"] is True


def _correction(segment: dict, content: str, reason) -> dict:
    return {
        "rows": [_row(segment, content=content)],
        "uncertain": [],
        "excluded": [],
        "corrections": [
            {
                "source_ids": [segment["segment_id"]],
                "before": "3",
                "after": "5",
                "reason": reason,
            }
        ],
        "name_map": _map([segment]),
    }


@pytest.mark.parametrize("reason", [None, "", "   ", 123, True, False, [], {}])
def test_correction_reason_is_not_checked(reason):
    segment = _segment("a.wav:0001", "0900:A", "the count is 3", 0.0, 1.0)
    result = review([segment], _correction(segment, "the count is 5", reason))
    assert result["ok"] is True
    assert result["unannotated_losses"] == []


def test_correction_reason_string_still_allows_replacement():
    segment = _segment("a.wav:0001", "0900:A", "the count is 3", 0.0, 1.0)
    assert review([segment], _correction(segment, "the count is 5", "stutter"))["ok"] is True


def _overlap(confidence, name="Alice") -> tuple[list[dict], dict]:
    segment = _segment("a.wav:0001", "0900:A+0900:B", "Hello Alice.", 0.0, 1.0)
    edited = {
        "rows": [
            {
                **_row(segment, speaker=name),
                "reason": "overlap_attribution",
                "confidence": confidence,
            }
        ],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "a.wav": {
                "0900:A+0900:B": {
                    "name": name,
                    "status": "mapped",
                    "origin": "editor",
                    "source_id": segment["segment_id"],
                }
            }
        },
    }
    return [segment], edited


@pytest.mark.parametrize("confidence", [None, "", "   ", True, False, [], {}, 1.5, float("nan")])
def test_overlap_confidence_is_not_checked(confidence):
    segments, edited = _overlap(confidence)
    assert review(segments, edited)["ok"] is True


@pytest.mark.parametrize("confidence", ["low", "medium", "high", 0, 1, 0.4])
def test_overlap_confidence_accepts_text_or_unit_interval(confidence):
    segments, edited = _overlap(confidence)
    assert review(segments, edited)["ok"] is True


@pytest.mark.parametrize("evidence", [None, "", "   ", 123, True, False, [], {}])
def test_editor_evidence_is_not_checked(evidence):
    segment = _segment("a.wav:0001", "0900:A", "Hello Alice.", 0.0, 1.0)
    edited = {
        "rows": [_row(segment, speaker="Alice")],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "a.wav": {
                "0900:A": {
                    "name": "Alice",
                    "status": "mapped",
                    "origin": "editor",
                    "source_id": "missing",
                    "evidence": evidence,
                }
            }
        },
    }
    assert review([segment], edited)["ok"] is True


def test_editor_evidence_string_without_source_id_is_accepted():
    segment = _segment("a.wav:0001", "0900:A", "Hello Alice.", 0.0, 1.0)
    edited = {
        "rows": [_row(segment, speaker="Alice")],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "a.wav": {
                "0900:A": {
                    "name": "Alice",
                    "status": "mapped",
                    "origin": "editor",
                    "evidence": "Hello Alice",
                }
            }
        },
    }
    assert review([segment], edited)["ok"] is True


@pytest.mark.parametrize("name", [True, False, 1, {"Alice": True}, ["Alice"], None])
def test_unused_mapping_metadata_is_not_checked(name):
    segment = _segment("a.wav:0001", "0900:A", "Hello Alice.", 0.0, 1.0)
    edited = {
        "rows": [_row(segment)],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "a.wav": {
                "0900:A": {"name": name, "status": "mapped", "origin": "caller"}
            }
        },
    }
    assert review([segment], edited)["ok"] is True


def test_exclusion_reason_string_is_accepted():
    segment = _segment("a.wav:0001", "0900:A", "Hello.", 0.0, 1.0)
    edited = {
        "rows": [],
        "uncertain": [],
        "excluded": [{"source_ids": [segment["segment_id"]], "reason": "filler"}],
        "corrections": [],
        "name_map": _map([segment]),
    }
    assert review([segment], edited)["ok"] is True


def test_empty_exclusion_reason_is_allowed():
    segments = [
        _segment("a.wav:0001", "0900:A", "one", 0.0, 1.0),
        _segment("a.wav:0002", "0900:A", "two", 1.0, 2.0),
    ]
    edited = {
        "rows": [_row(segments[0])],
        "uncertain": [],
        "excluded": [{"source_ids": ["a.wav:0002"], "reason": ""}],
        "corrections": [],
        "name_map": _map(segments),
    }
    assert review(segments, edited)["ok"] is True


def test_correction_after_is_not_checked():
    segment = _segment("a.wav:0001", "0900:A", "the count is 3", 0.0, 1.0)
    hidden = {
        "rows": [_row(segment, content="the count is 13")],
        "uncertain": [],
        "excluded": [],
        "corrections": [{"source_ids": [segment["segment_id"]], "before": "3", "after": "3", "reason": "stutter"}],
        "name_map": _map([segment]),
    }
    hidden_result = review([segment], hidden)
    assert hidden_result["ok"] is True
    assert hidden_result["unannotated_losses"] == []
    note = _segment("a.wav:0001", "0900:A", "this is not optional", 0.0, 1.0)
    buried = {
        "rows": [_row(note, content="this is note optional")],
        "uncertain": [],
        "excluded": [],
        "corrections": [{"source_ids": [note["segment_id"]], "before": "not", "after": "not", "reason": "filler"}],
        "name_map": _map([note]),
    }
    buried_result = review([note], buried)
    assert buried_result["ok"] is True
    assert buried_result["unannotated_losses"] == []
    kept = {
        "rows": [_row(segment, content="the count is 5")],
        "uncertain": [],
        "excluded": [],
        "corrections": [{"source_ids": [segment["segment_id"]], "before": "3", "after": "5", "reason": "stutter"}],
        "name_map": _map([segment]),
    }
    assert review([segment], kept)["ok"] is True


def test_editor_can_infer_a_name_without_literal_spelling_in_the_file():
    segment = _segment("a.wav:0001", "0900:A", "Hello", 0.0, 1.0)
    edited = {
        "rows": [_row(segment, speaker="Charlie")],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {
            "a.wav": {
                "0900:A": {
                    "name": "Charlie",
                    "status": "mapped",
                    "origin": "editor",
                    "source_id": segment["segment_id"],
                }
            }
        },
    }
    assert review([segment], edited)["ok"] is True


def test_missing_overlap_maps_and_cjk_character_difference_do_not_block_export():
    segments = [
        _segment("a.wav:0001", "0900:A", "不会同意，但这是特别好的渠道。", 0.0, 1.0),
        _segment("a.wav:0002", "0900:A+0900:B", "嗯。", 1.0, 2.0),
    ]
    edited = {
        "rows": [_row(segments[0], content="不会同意，但这是很好的渠道。"), _row(segments[1])],
        "uncertain": [],
        "excluded": [],
        "corrections": [],
        "name_map": {},
    }
    rows, result, extras = apply_edit(segments, edited, "timed")
    assert result["ok"] is True
    assert rows[0]["content"] == "不会同意，但这是很好的渠道。"
    assert rows[1]["speaker"] == "0900:A+0900:B"
    assert result["unannotated_losses"] == []
    assert extras["name_map"]["a.wav"]["0900:A+0900:B"] == {
        "status": "unknown", "name": "", "origin": "editor"
    }
    assert edited["name_map"] == {}


def test_omitted_caller_map_is_restored_but_can_be_replaced():
    segment = _segment("a.wav:0001", "0900:A", "Hello.", 0.0, 1.0)
    caller = {"name": "Alice", "status": "mapped", "origin": "caller"}
    confirmed = {"a.wav": {"0900:A": caller}}
    edited = {"rows": [_row(segment, speaker="Alice")], "excluded": [], "uncertain": []}
    rows, result, extras = apply_edit([segment], edited, "timed", confirmed)
    assert result["ok"] is True
    assert rows[0]["speaker"] == "Alice"
    assert extras["name_map"]["a.wav"]["0900:A"] == caller
    edited["name_map"] = {"a.wav": {"0900:A": {**caller, "name": "Bob"}}}
    assert review([segment], edited, confirmed)["ok"] is False  # Alice no longer has a source mapping.
    edited["rows"][0]["speaker"] = "Bob"
    assert review([segment], edited, confirmed)["ok"] is True


def test_unused_malformed_mapping_does_not_block_acoustic_label():
    segment = _segment("a.wav:0001", "0900:A", "Hello.", 0.0, 1.0)
    edited = {"rows": [_row(segment)], "name_map": {"a.wav": {"0900:A": None}}}
    assert review([segment], edited)["ok"] is True


def test_owned_modified_csv_is_archived_not_lost(tmp_path, monkeypatch):
    from asr_skill.compat import _mark_owned, align_date_dir

    day = tmp_path / "day"
    (day / "raw").mkdir(parents=True)
    (day / "raw" / "clip.wav").write_bytes(b"x")
    csv_path = day / "out.csv"
    csv_path.write_text("speaker,content\n0900:A,user edited\n", encoding="utf-8")
    _mark_owned(csv_path)
    csv_path.write_text("speaker,content\n0900:A,human change\n", encoding="utf-8")
    rich = day / "out.rich.jsonl"
    diar = tmp_path / "diar.json"
    diar.write_text(
        '{"audio_dir":"raw","files":[{"file":"clip.wav","segments":[],"speech_regions":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "asr_skill.compat.align_paths",
        lambda *args, **kwargs: (0, [{"speaker": "0900:A", "content": "new", "start": 0, "end": 1}]),
    )
    code = align_date_dir(str(day), str(diar), str(csv_path), str(rich), work_dir=str(tmp_path / "work"))
    assert code == 0
    archived = list((day / "history").rglob("out.csv"))
    assert archived
    assert "human change" in archived[0].read_text(encoding="utf-8")


def test_long_file_is_rejected_before_load(tmp_path, monkeypatch):
    from asr_skill.runners.diarize import main as diar_main

    src = tmp_path / "long.wav"
    src.write_bytes(b"x")
    spec = tmp_path / "jobs.json"
    spec.write_text(
        '{"model": "nvidia/Nemotron-3-Diarization", "jobs": [{"input": "%s", "output": "%s"}]}'
        % (src, tmp_path / "out.json"),
        encoding="utf-8",
    )
    monkeypatch.setattr("asr_skill.preflight.probe_duration", lambda _path: 9000.0)
    calls = {"n": 0}

    def fake_load(_model):
        calls["n"] += 1
        return object(), object()

    monkeypatch.setattr("asr_skill.runners.diarize.load_model", fake_load)
    assert diar_main(["--jobs", str(spec)]) != 0
    assert calls["n"] == 0


def test_prepare_edit_exposes_the_protocol(tmp_path: Path):
    rich = tmp_path / "rich.jsonl"
    segment = _segment("meeting_0900.wav:0001", "0900:A", "Hello.", 0.0, 1.0)
    rich.write_text(json.dumps(segment) + "\n", encoding="utf-8")
    confirmed = tmp_path / "confirmed.json"
    confirmed.write_text(
        json.dumps({"meeting_0900.wav": {"0900:A": {"name": "Alice", "status": "mapped", "origin": "caller"}}}),
        encoding="utf-8",
    )
    task = tmp_path / "task"
    code = main(
        [
            "prepare-edit",
            "--rich",
            str(rich),
            "--task-dir",
            str(task),
            "--confirmed-name-map",
            str(confirmed),
        ]
    )
    assert code == EXIT_OK
    assert (task / "instructions.md").is_file()
    assert (task / "segments.jsonl").is_file()
    assert (task / "confirmed_name_map.json").is_file()
