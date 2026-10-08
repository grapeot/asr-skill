import csv
import json
from pathlib import Path

from asr_skill.contracts import NAME_MAP_STATUSES, RAW_CSV_FIELDS, RICH_SEGMENT_FIELDS, TIMED_CSV_FIELDS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "synthetic"


def _rich_rows():
    rows = []
    for line in (FIXTURES / "alice_bob_rich.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_rich_fixture_fields():
    rows = _rich_rows()
    assert [row["segment_id"] for row in rows] == ["seg-001", "seg-002", "seg-003"]
    for row in rows:
        assert tuple(row) == RICH_SEGMENT_FIELDS
    assert rows[0]["speaker"] == "0900:A"
    assert rows[1]["content"].count("not") == 1
    assert "3" in rows[0]["content"] and "3" in rows[1]["content"]


def test_csv_contract_and_traceability():
    with (FIXTURES / "alice_bob_raw.csv").open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    with (FIXTURES / "alice_bob_readable.csv").open(encoding="utf-8", newline="") as handle:
        readable = list(csv.DictReader(handle))
    assert list(raw[0]) == list(RAW_CSV_FIELDS)
    assert list(readable[0]) == list(TIMED_CSV_FIELDS)
    assert [row["speaker"] for row in readable] == ["Alice", "Bob"]
    assert "3" in readable[0]["content"] and "not" in readable[1]["content"]
    source_map = json.loads((FIXTURES / "alice_bob_source_map.json").read_text(encoding="utf-8"))
    kept = [sid for row in source_map["rows"] for sid in row["source_ids"]]
    excluded = [sid for row in source_map["excluded"] for sid in row["source_ids"]]
    assert kept + excluded == ["seg-001", "seg-002", "seg-003"]
    assert source_map["excluded"][0]["reason"] == "filler"


def test_public_examples_pass_review():
    from asr_skill.validate import review

    segments = _rich_rows()
    source_map = json.loads((FIXTURES / "alice_bob_source_map.json").read_text(encoding="utf-8"))
    name_map = json.loads((FIXTURES / "alice_bob_name_map.json").read_text(encoding="utf-8"))
    by_id = {row["segment_id"]: row for row in segments}
    edited = {
        "rows": [
            {
                "source_ids": item["source_ids"],
                "start": by_id[item["source_ids"][0]]["start"],
                "end": by_id[item["source_ids"][0]]["end"],
                "speaker": name_map[by_id[item["source_ids"][0]]["file"]][
                    by_id[item["source_ids"][0]]["speaker"]
                ]["name"],
                "content": by_id[item["source_ids"][0]]["content"],
            }
            for item in source_map["rows"]
        ],
        "uncertain": source_map["uncertain"],
        "excluded": source_map["excluded"],
        "corrections": source_map["corrections"],
        "name_map": name_map,
    }
    result = review(segments, edited)
    assert result["ok"] is True, result
    assert "excluded" in source_map and "uncertain" in source_map


def test_name_map_keeps_unknown():
    name_map = json.loads((FIXTURES / "alice_bob_name_map.json").read_text(encoding="utf-8"))
    labels = name_map["synthetic_0900.wav"]
    assert labels["0900:A"]["name"] == "Alice"
    assert labels["0900:B"]["name"] == "Bob"
    assert labels["0900:C"]["name"] is None
    assert labels["0900:C"]["status"] == "unknown"
    assert {item["status"] for item in labels.values()} <= set(NAME_MAP_STATUSES)
