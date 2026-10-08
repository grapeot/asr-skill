"""Identifiers for the scaffold. These names do not run models."""

PHASE = "scaffold"
IMPLEMENTED = False

DIARIZATION_MODEL_ID = "nvidia/Nemotron-3-Diarization"
ASR_MODEL_ID = "Qwen/Qwen3-ASR-1.7B"

FRAME_MS = 10.0
MIN_SEGMENT_SEC = 0.15
SAME_SPEAKER_MERGE_GAP_SEC = 0.3
SPEECH_REGION_MERGE_GAP_SEC = 1.0
NEAR_SEGMENT_SEC = 1.5
UTTERANCE_GAP_SEC = 3.0
SHORT_LINE_CHARS = 3
SHORT_MERGE_GAP_SEC = 15.0
LONG_LINE_CHARS = 400

RAW_CSV_FIELDS = ("speaker", "content")
RICH_SEGMENT_FIELDS = (
    "segment_id",
    "file",
    "start",
    "end",
    "speaker",
    "content",
)
NAME_MAP_STATUSES = ("mapped", "unknown")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_IMPLEMENTED = 3

SCAFFOLD_COMMANDS = ("version", "doctor")
PLANNED_COMMANDS = ("init", "diarize", "align", "clean", "run", "smoke")
