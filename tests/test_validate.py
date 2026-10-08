import pytest

from asr_skill.clean import apply_edit
from asr_skill.validate import review


def _segment(segment_id: str, speaker: str, content: str, start: float = 0.0, end: float = 1.0) -> dict:
    return {
        "segment_id": segment_id,
        "file": segment_id.split(":")[0],
        "start": start,
        "end": end,
        "speaker": speaker,
        "content": content,
    }


def _names(*segments: dict) -> dict:
    mapped: dict[str, dict] = {}
    for segment in segments:
        mapped.setdefault(segment["file"], {})[segment["speaker"]] = {
            "name": None,
            "status": "unknown",
            "origin": "editor",
        }
    return mapped


def test_source_map_coverage_is_not_a_gate():
    segments = [_segment("meeting_0900.wav:0001", "0900:A", "Hello.")]
    edited = {"rows": [], "excluded": [], "uncertain": [], "corrections": [], "name_map": _names(*segments)}
    result = review(segments, edited)
    assert result["ok"] is True
    assert result["missing_source_ids"] == []
    assert result["equivalence_proven"] is False


def test_number_or_negation_difference_is_not_checked():
    segments = [_segment("meeting_0900.wav:0001", "0900:A", "The count is not 3.")]
    edited = {
        "rows": [
            {
                "source_ids": ["meeting_0900.wav:0001"],
                "content": "The count is 3.",
                "start": 0.0,
                "end": 1.0,
                "speaker": "0900:A",
            }
        ],
        "excluded": [],
        "uncertain": [],
        "corrections": [],
        "name_map": _names(*segments),
    }
    result = review(segments, edited)
    assert result["ok"] is True
    assert result["unannotated_losses"] == []
    assert result["warnings"] == []
    assert result["equivalence_proven"] is False


def test_annotated_stutter_fix_is_allowed():
    segments = [_segment("meeting_0900.wav:0001", "0900:A", "The count is 55.")]
    edited = {
        "rows": [
            {
                "source_ids": ["meeting_0900.wav:0001"],
                "content": "The count is 5.",
                "start": 0.0,
                "end": 1.0,
                "speaker": "0900:A",
            }
        ],
        "excluded": [],
        "uncertain": [],
        "corrections": [
            {
                "source_ids": ["meeting_0900.wav:0001"],
                "before": "55",
                "after": "5",
                "reason": "repeated digit",
            }
        ],
        "name_map": _names(*segments),
    }
    assert review(segments, edited)["ok"] is True


def test_cross_speaker_merge_does_not_need_an_overlap_reason():
    segments = [
        _segment("meeting_0900.wav:0001", "0900:A", "Hello.", 0.0, 1.0),
        _segment("meeting_0900.wav:0002", "0900:B", "No.", 1.0, 2.0),
    ]
    merged = {
        "rows": [
            {
                "source_ids": ["meeting_0900.wav:0001", "meeting_0900.wav:0002"],
                "content": "Hello. No.",
                "start": 0.0,
                "end": 2.0,
                "speaker": "unknown",
            }
        ],
        "excluded": [],
        "uncertain": [],
        "corrections": [],
        "name_map": _names(*segments),
    }
    assert review(segments, merged)["ok"] is True


@pytest.mark.parametrize(
    ("kind", "changes", "problem"),
    [
        ("rows", {"speaker": "invented"}, "speaker not allowed"),
        ("uncertain", {"speaker": "0900:A"}, "uncertain speaker must be unknown"),
        ("rows", {"start": -1}, "time envelope"),
        ("rows", {"end": 2}, "time envelope"),
        ("rows", {"start": 0.8, "end": 0.2}, "time envelope"),
        ("rows", {"start": float("nan")}, "time envelope"),
        ("rows", {"end": float("inf")}, "time envelope"),
    ],
)
def test_retained_rules_still_block_publication(kind, changes, problem):
    source = _segment("meeting.wav:0001", "0900:A", "Hello")
    row = {"source_ids": [source["segment_id"]], "start": 0, "end": 1,
           "speaker": "0900:A", "content": "Hello", **changes}
    rows, result, extras = apply_edit([source], {kind: [row]}, "timed")
    assert result["ok"] is False
    assert any(item.startswith(problem) for item in result["problems"])
    assert rows == []
    assert extras == {}


def test_reversed_sources_in_a_merge_still_fail_order_check():
    sources = [_segment("a.wav:1", "A", "One", 0, 1), _segment("a.wav:2", "B", "Two", 1, 2)]
    edited = {"rows": [{"source_ids": ["a.wav:2", "a.wav:1"], "speaker": "unknown",
                        "content": "Two one", "start": 0, "end": 2}]}
    assert "rows are out of source time order" in review(sources, edited)["problems"]


def test_split_source_rows_cannot_reverse_time():
    source = _segment("a.wav:1", "A", "One two", 0, 2)
    edited = {"rows": [
        {"source_ids": ["a.wav:1"], "speaker": "A", "content": "Two", "start": 1, "end": 2},
        {"source_ids": ["a.wav:1"], "speaker": "A", "content": "One", "start": 0, "end": 1},
    ]}
    assert "rows are out of source time order" in review([source], edited)["problems"]


def test_split_source_rows_are_exported_without_uniqueness_gate():
    source = _segment("a.wav:1", "A", "One two", 0, 2)
    edited = {"rows": [
        {"source_ids": ["a.wav:1"], "speaker": "A", "content": "One", "start": 0, "end": 1},
        {"source_ids": ["a.wav:1"], "speaker": "A", "content": "Two", "start": 1, "end": 2},
    ]}
    rows, result, extras = apply_edit([source], edited, "timed")
    assert result["ok"] is True
    assert [row["content"] for row in rows] == ["One", "Two"]
    assert [row["source_ids"] for row in extras["source_map"]["rows"]] == [["a.wav:1"], ["a.wav:1"]]


def test_source_file_timestamps_may_reset_at_a_file_boundary():
    sources = [_segment("a.wav:1", "A", "First file", 10, 11),
               _segment("b.wav:1", "B", "Next file", 0, 1)]
    edited = {"rows": [{"source_ids": [source["segment_id"]], "speaker": source["speaker"],
                        "content": source["content"], "start": source["start"], "end": source["end"]}
                       for source in sources]}
    rows, result, _extras = apply_edit(sources, edited, "timed")
    assert result["ok"] is True
    assert [row["content"] for row in rows] == ["First file", "Next file"]
