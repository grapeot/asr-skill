from asr_skill.timeline import (
    acoustic_labels,
    assign_speaker,
    file_prefix,
    smooth_diarization,
    words_to_segments,
)


def test_labels_are_first_seen_and_file_scoped():
    assert file_prefix("meeting_0900.wav") == "0900"
    assert file_prefix("meeting_1000.wav") == "1000"
    first = acoustic_labels([2, 0, 2], "0900")
    second = acoustic_labels([2], "1000")
    assert first[2] == "0900:A"
    assert first[0] == "0900:B"
    assert second[2] == "1000:A"
    assert first[2] != second[2]


def test_overlap_and_near_and_empty():
    segments = [(0.0, 1.0, 0), (0.8, 1.4, 1)]
    assert assign_speaker(0.9, segments) == [0, 1]
    assert assign_speaker(1.5, segments) == [1]
    assert assign_speaker(4.0, segments) == []
    assert words_to_segments([], {0: "0900:A"}, "meeting_0900.wav") == []


def test_word_midpoint_groups_without_crossing_speakers():
    labels = {0: "0900:A", 1: "0900:B"}
    words = [
        {"text": "Hello", "start": 0.1, "end": 0.4, "speaker_ids": [0]},
        {"text": "Bob.", "start": 0.5, "end": 0.8, "speaker_ids": [0]},
        {"text": "No.", "start": 1.2, "end": 1.5, "speaker_ids": [1]},
    ]
    rows = words_to_segments(words, labels, "meeting_0900.wav")
    assert [row["speaker"] for row in rows] == ["0900:A", "0900:B"]
    assert rows[0]["content"] == "Hello Bob."
    assert rows[0]["segment_id"] == "meeting_0900.wav:0001"


def test_short_fragments_are_dropped_before_regions():
    segments, regions, speakers = smooth_diarization([(0.0, 0.05, 0), (1.0, 1.4, 1)])
    assert speakers == [1]
    assert segments[0]["speaker"] == 1
    assert regions
