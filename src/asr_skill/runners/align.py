"""Apple Silicon ASR runner. Import MLX only when this module is executed."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import subprocess
import sys
from pathlib import Path

from asr_skill.artifacts import read_json, write_json, write_jsonl
from asr_skill.contracts import (
    ASR_MODEL_ID,
    EXIT_MODEL,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_UNSUPPORTED,
    EXIT_USAGE,
    MIN_REGION_SEC,
    MLX_QWEN_VERSION,
    MLX_VERSION,
    NAGISA_VERSION,
    NUMPY_VERSION,
    SOYNLP_VERSION,
)
from asr_skill.timeline import acoustic_labels, assign_speaker, file_prefix, words_to_segments


def _apple() -> bool:
    import platform

    return sys.platform == "darwin" and platform.machine() == "arm64"


def pin_mismatch(name: str, want: str) -> str | None:
    try:
        got = metadata.version(name)
    except metadata.PackageNotFoundError:
        return f"{name} is not installed. Required {want}."
    if got != want:
        return f"{name} {got} != required {want}."
    return None


def check_runtime(model_id: str) -> int:
    if not _apple():
        print("MLX ASR is supported on Apple Silicon only. No other ASR model will be used.", file=sys.stderr)
        return EXIT_UNSUPPORTED
    for name, want in (
        ("mlx", MLX_VERSION),
        ("numpy", NUMPY_VERSION),
        ("nagisa", NAGISA_VERSION),
        ("soynlp", SOYNLP_VERSION),
    ):
        mismatch = pin_mismatch(name, want)
        if mismatch:
            print(f"{mismatch} Refusing to load {model_id}.", file=sys.stderr)
            return EXIT_MODEL
    version = metadata.version("mlx-qwen3-asr")
    if version != MLX_QWEN_VERSION:
        print(
            f"mlx-qwen3-asr {version} != required {MLX_QWEN_VERSION}. Refusing to load {model_id}.",
            file=sys.stderr,
        )
        return EXIT_MODEL
    from mlx_qwen3_asr import transcribe

    if not callable(transcribe):
        print("mlx_qwen3_asr.transcribe is missing", file=sys.stderr)
        return EXIT_MODEL
    print(f"asr-runtime ok mlx-qwen3-asr={version} model={model_id}")
    return EXIT_OK


def _slice(source: Path, start: float, duration: float, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
            "-ar", "16000", "-ac", "1", str(dest),
        ],
        check=True,
    )


def align_file(source: Path, file_info: dict, model_id: str, work_dir: Path) -> list[dict]:
    from mlx_qwen3_asr import transcribe

    segments = [(item["start"], item["end"], int(item["speaker"])) for item in file_info["segments"]]
    labels = acoustic_labels([item[2] for item in segments], file_prefix(source.name))
    words: list[dict] = []
    regions = file_info.get("speech_regions") or []
    usable = [item for item in regions if item["end"] - item["start"] >= MIN_REGION_SEC]
    if not usable:
        return []
    for index, region in enumerate(usable):
        start = float(region["start"])
        duration = float(region["end"]) - start
        wav = work_dir / f"{source.stem}_region_{index:03d}.wav"
        _slice(source, start, duration, wav)
        try:
            result = transcribe(str(wav), model=model_id, verbose=False, return_timestamps=True)
        finally:
            wav.unlink(missing_ok=True)
        for token in result.segments or []:
            text = (token.get("text") or "").strip()
            if not text:
                continue
            word_start = start + float(token["start"])
            word_end = start + float(token["end"])
            midpoint = (word_start + word_end) / 2
            words.append(
                {
                    "text": text,
                    "start": word_start,
                    "end": word_end,
                    "speaker_ids": assign_speaker(midpoint, segments),
                }
            )
    if not words:
        raise RuntimeError(f"speech regions in {source.name} produced no words")
    return words_to_segments(words, labels, source.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asr_skill.runners.align")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--warmup")
    parser.add_argument("--audio")
    parser.add_argument("--diarization")
    parser.add_argument("--output-rich")
    parser.add_argument("--model", default=ASR_MODEL_ID)
    parser.add_argument("--jobs")
    args = parser.parse_args(argv)
    if args.jobs:
        spec = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
        if spec.get("model") != ASR_MODEL_ID:
            print(f"refusing model {spec.get('model')}", file=sys.stderr)
            return EXIT_MODEL
        from asr_skill.preflight import over_limit

        try:
            too_long = over_limit([Path(job["audio"]) for job in spec["jobs"]])
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_RUNTIME
        if too_long:
            print(too_long, file=sys.stderr)
            return EXIT_USAGE
        code = check_runtime(spec["model"])
        if code != EXIT_OK:
            return code
        failed_model = False
        failed_runtime = False
        for job in spec["jobs"]:
            output = Path(job["output"])
            output.parent.mkdir(parents=True, exist_ok=True)
            info = read_json(Path(job["diarization"]))["files"][0]
            regions = info.get("speech_regions") or []
            usable = [item for item in regions if item["end"] - item["start"] >= MIN_REGION_SEC]
            if not usable:
                write_json(
                    output,
                    {
                        "status": "complete",
                        "empty_speech": True,
                        "input_sha256": job.get("input_sha256"),
                        "params_sha256": job.get("params_sha256"),
                        "rows": [],
                    },
                )
                continue
            try:
                rows = align_file(Path(job["audio"]), info, spec["model"], output.parent)
                write_json(
                    output,
                    {
                        "status": "complete",
                        "empty_speech": False,
                        "input_sha256": job.get("input_sha256"),
                        "params_sha256": job.get("params_sha256"),
                        "rows": rows,
                    },
                )
            except subprocess.CalledProcessError as exc:
                failed_runtime = True
                print(exc.stderr or str(exc), file=sys.stderr)
                write_json(output, {"status": "failed", "error": str(exc)})
            except Exception as exc:
                failed_model = True
                print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
                write_json(output, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        if failed_runtime:
            return EXIT_RUNTIME
        return EXIT_MODEL if failed_model else EXIT_OK
    if args.model != ASR_MODEL_ID:
        print(f"refusing model {args.model}", file=sys.stderr)
        return EXIT_MODEL
    if args.check or args.load:
        code = check_runtime(args.model)
        if code != EXIT_OK or not args.load:
            return code
        if not args.warmup:
            print("load requested without --warmup", file=sys.stderr)
            return EXIT_USAGE
        try:
            from mlx_qwen3_asr import transcribe

            result = transcribe(args.warmup, model=args.model, verbose=False, return_timestamps=True)
        except Exception as exc:
            print(f"load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_MODEL
        count = len(result.segments or [])
        print(f"loaded mlx-qwen3-asr warmup_tokens={count}")
        return EXIT_OK
    if not args.audio or not args.diarization or not args.output_rich:
        parser.print_help()
        return EXIT_USAGE
    payload = read_json(Path(args.diarization))
    if payload.get("model") != ASR_MODEL_ID and payload.get("model") != args.model:
        # diarization json stores the diarization model, not the ASR model
        pass
    file_info = payload["files"][0]
    try:
        rows = align_file(Path(args.audio), file_info, args.model, Path(args.output_rich).parent)
    except Exception as exc:
        print(f"align failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_MODEL
    write_jsonl(Path(args.output_rich), rows)
    print(f"aligned {Path(args.audio).name} rows={len(rows)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
