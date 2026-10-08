"""Command-line entry. Acoustic models stay local. An editor command is caller-supplied."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from asr_skill import __version__
from asr_skill.contracts import (
    ASR_MODEL_ID,
    DIARIZATION_MODEL_ID,
    EXIT_OK,
    EXIT_USAGE,
)

DESCRIPTION = (
    "Local speaker-attributed transcription. "
    "Diarization and speech recognition run on this machine. "
    "A text editor you configure may send text to that editor's own service."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="asr-skill", description=DESCRIPTION)
    parser.add_argument("--version", action="store_true", help="Print the version")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version", help="Print the version")
    doctor = sub.add_parser("doctor", help="Load the verified models, or report the missing piece")
    doctor.add_argument("--no-load", action="store_true", help="Check imports and pins without loading weights")

    init = sub.add_parser("init", help="Create the two verified environments and load the models once")
    init.add_argument("--no-download", action="store_true", help="Do not download weights")

    diar = sub.add_parser("diarize", help="Diarize original-file timelines with Nemotron on CPU")
    diar.add_argument("--input", required=True, help="Audio file or directory")
    diar.add_argument("--work-dir", required=True, help="Checkpoint directory")
    diar.add_argument("--model", default=DIARIZATION_MODEL_ID)

    align = sub.add_parser("align", help="Align Qwen word times onto the diarization timeline")
    align.add_argument("--input", required=True)
    align.add_argument("--work-dir", required=True)
    align.add_argument("--model", default=ASR_MODEL_ID)

    clean = sub.add_parser("clean", help="Ask an external editor to revise text, then validate the map")
    clean.add_argument("--rich", required=True)
    clean.add_argument("--output-csv", required=True)
    clean.add_argument("--source-map", required=True)
    clean.add_argument("--name-map", required=True)
    clean.add_argument("--editor-cmd", required=True, help="Executable that receives the task directory")
    clean.add_argument("--csv-format", choices=("legacy", "timed"), default="timed")
    clean.add_argument("--task-dir")

    run = sub.add_parser("run", help="Diarize, align, and optionally clean")
    run.add_argument("--input", required=True)
    run.add_argument("--work-dir", required=True)
    run.add_argument("--editor-cmd")
    run.add_argument("--csv-format", choices=("legacy", "timed"), default="timed")

    smoke = sub.add_parser("smoke", help="Run the verified models on a synthetic Alice/Bob recording")
    smoke.add_argument("--work-dir", required=True)
    smoke.add_argument("--editor-cmd")

    prepare = sub.add_parser("prepare-edit", help="Write the editor task so the current agent can edit it")
    prepare.add_argument("--rich", required=True)
    prepare.add_argument("--task-dir", required=True)
    prepare.add_argument("--confirmed-name-map")

    finalize = sub.add_parser("finalize-edit", help="Validate edited.json and write the readable outputs")
    finalize.add_argument("--rich", required=True)
    finalize.add_argument("--task-dir", required=True)
    finalize.add_argument("--output-csv", required=True)
    finalize.add_argument("--source-map", required=True)
    finalize.add_argument("--name-map", required=True)
    finalize.add_argument("--csv-format", choices=("legacy", "timed"), default="timed")

    legacy_diar = sub.add_parser("legacy-diarize", help="Date-directory diarization for a later thin wrapper")
    legacy_diar.add_argument("--date-dir", required=True)
    legacy_diar.add_argument("--output")
    legacy_diar.add_argument("--model", default=DIARIZATION_MODEL_ID)
    legacy_diar.add_argument("--work-dir")

    legacy_align = sub.add_parser("legacy-align", help="Date-directory alignment; CSV stays speaker,content")
    legacy_align.add_argument("--date-dir", required=True)
    legacy_align.add_argument("--diarization", required=True)
    legacy_align.add_argument("--output", required=True)
    legacy_align.add_argument("--rich-output")
    legacy_align.add_argument("--model", default=ASR_MODEL_ID)
    legacy_align.add_argument("--work-dir")
    return parser


def _version() -> int:
    print(f"asr-skill {__version__}")
    return EXIT_OK


def _load_env() -> None:
    from asr_skill.runtime import project_root

    for path in (Path.cwd() / ".env", project_root() / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version or args.command == "version":
        return _version()
    if args.command == "doctor":
        from asr_skill.doctor import print_doctor

        return print_doctor(load=not args.no_load)
    if args.command == "init":
        from asr_skill.setup_runtime import init_runtimes

        return init_runtimes(download=not args.no_download)
    if args.command == "diarize":
        from asr_skill.pipeline import diarize_paths, discover_audio

        paths = discover_audio(Path(args.input))
        if not paths:
            print(f"no audio in {args.input}", file=sys.stderr)
            return EXIT_USAGE
        code, _payload = diarize_paths(paths, Path(args.work_dir), args.model)
        if code == EXIT_OK:
            print(json.dumps({"command": "diarize", "ok": True, "files": len(paths), "model": args.model}))
        return code
    if args.command == "align":
        from asr_skill.pipeline import align_paths, discover_audio

        paths = discover_audio(Path(args.input))
        if not paths:
            print(f"no audio in {args.input}", file=sys.stderr)
            return EXIT_USAGE
        code, rows = align_paths(paths, Path(args.work_dir), args.model)
        if code == EXIT_OK:
            print(json.dumps({"command": "align", "ok": True, "rows": len(rows), "model": args.model}))
        return code
    if args.command == "clean":
        from asr_skill.clean import clean_files

        task = Path(args.task_dir) if args.task_dir else Path(args.output_csv).parent / "editor_task"
        return clean_files(
            Path(args.rich),
            Path(args.output_csv),
            Path(args.source_map),
            Path(args.name_map),
            args.editor_cmd,
            args.csv_format,
            task,
        )
    if args.command == "run":
        from asr_skill.pipeline import align_paths, diarize_paths, discover_audio

        paths = discover_audio(Path(args.input))
        if not paths:
            print(f"no audio in {args.input}", file=sys.stderr)
            return EXIT_USAGE
        work = Path(args.work_dir)
        code, _payload = diarize_paths(paths, work)
        if code != EXIT_OK:
            return code
        code, rows = align_paths(paths, work)
        if code != EXIT_OK:
            return code
        if not args.editor_cmd:
            print(json.dumps({"command": "run", "ok": True, "clean": "not_run", "rows": len(rows)}))
            return EXIT_OK
        from asr_skill.clean import clean_files

        return clean_files(
            work / "transcript.rich.jsonl",
            work / "transcript.readable.csv",
            work / "source_map.json",
            work / "name_map.json",
            args.editor_cmd,
            args.csv_format,
            work / "editor_task",
        )
    if args.command == "smoke":
        from asr_skill.pipeline import align_paths, diarize_paths
        from asr_skill.smoke import acoustic_notes, make_fixture

        work = Path(args.work_dir)
        try:
            paths = make_fixture(work / "audio")
        except Exception as exc:
            print(f"synthetic audio failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        code, _payload = diarize_paths(paths, work)
        if code != EXIT_OK:
            return code
        code, rows = align_paths(paths, work)
        if code != EXIT_OK:
            return code
        notes = acoustic_notes(rows)
        if not rows:
            print(json.dumps({"command": "smoke", "ok": False, "acoustic": notes}))
            return EXIT_USAGE
        if args.editor_cmd:
            from asr_skill.clean import clean_files

            code = clean_files(
                work / "transcript.rich.jsonl",
                work / "transcript.readable.csv",
                work / "source_map.json",
                work / "name_map.json",
                args.editor_cmd,
                "timed",
                work / "editor_task",
            )
            if code != EXIT_OK:
                return code
        print(json.dumps({"command": "smoke", "ok": True, "acoustic": notes, "identity_verified": False}))
        return EXIT_OK
    if args.command == "prepare-edit":
        from asr_skill.artifacts import read_json, read_jsonl
        from asr_skill.clean import prepare_task

        confirmed = read_json(Path(args.confirmed_name_map)) if args.confirmed_name_map else None
        prepare_task(Path(args.task_dir), read_jsonl(Path(args.rich)), confirmed)
        print(json.dumps({"command": "prepare-edit", "ok": True, "task_dir": args.task_dir}))
        return EXIT_OK
    if args.command == "finalize-edit":
        from asr_skill.clean import finalize_edit

        return finalize_edit(
            Path(args.rich),
            Path(args.task_dir) / "edited.json",
            Path(args.output_csv),
            Path(args.source_map),
            Path(args.name_map),
            args.csv_format,
            Path(args.task_dir),
        )
    if args.command == "legacy-diarize":
        from asr_skill.compat import diarize_date_dir

        return diarize_date_dir(args.date_dir, args.output, args.model, args.work_dir)
    if args.command == "legacy-align":
        from asr_skill.compat import align_date_dir

        return align_date_dir(
            args.date_dir,
            args.diarization,
            args.output,
            args.rich_output,
            args.model,
            args.work_dir,
        )
    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
