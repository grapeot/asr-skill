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


def test_source_map_must_cover_every_segment():
    segments = [_segment("meeting_0900.wav:0001", "0900:A", "Hello.")]
    edited = {"rows": [], "excluded": [], "uncertain": [], "corrections": [], "name_map": _names(*segments)}
    result = review(segments, edited)
    assert result["ok"] is False
    assert "meeting_0900.wav:0001" in result["missing_source_ids"]
    assert result["equivalence_proven"] is False


def test_unannotated_number_or_negation_loss_is_rejected():
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
    assert result["ok"] is False
    assert any(item["token"] == "not" for item in result["unannotated_losses"])


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


def test_cross_speaker_merge_needs_an_overlap_reason():
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
    assert review(segments, merged)["ok"] is False
