"""CPU diarization runner. Import torch only when this module is executed."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from asr_skill.artifacts import write_json
from asr_skill.contracts import (
    DIAR_TRANSFORMERS_COMMIT,
    DIARIZATION_MODEL_ID,
    EXIT_MODEL,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    FRAME_MS,
    LIBROSA_VERSION,
    NUMPY_VERSION,
    TORCH_VERSION,
)
from asr_skill.timeline import file_prefix, smooth_diarization


def _commit() -> str | None:
    import importlib.metadata as metadata
    import json

    try:
        raw = metadata.distribution("transformers").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not raw:
        return None
    return json.loads(raw).get("vcs_info", {}).get("commit_id")


def check_runtime(model_id: str) -> int:
    import importlib.metadata as metadata
    from transformers import AutoModelForAudioFrameClassification

    expected = {
        "torch": TORCH_VERSION,
        "librosa": LIBROSA_VERSION,
        "numpy": NUMPY_VERSION,
    }
    for name, want in expected.items():
        got = metadata.version(name)
        if got != want:
            print(f"{name} {got} != required {want}. Refusing to load {model_id}.", file=sys.stderr)
            return EXIT_MODEL
    commit = _commit()
    version = metadata.version("transformers")
    if commit != DIAR_TRANSFORMERS_COMMIT:
        print(
            json_error(
                f"transformers commit {commit} != required {DIAR_TRANSFORMERS_COMMIT} "
                f"(reported {version}). Refusing to load {model_id}."
            ),
            file=sys.stderr,
        )
        return EXIT_MODEL
    if not hasattr(AutoModelForAudioFrameClassification, "from_pretrained"):
        print("AutoModelForAudioFrameClassification is missing. Refusing to continue.", file=sys.stderr)
        return EXIT_MODEL
    print(f"diar-runtime ok transformers={version} commit={commit} model={model_id}")
    return EXIT_OK


def json_error(message: str) -> str:
    return message


def load_model(model_id: str):
    from transformers import AutoModelForAudioFrameClassification, AutoProcessor

    commit = _commit()
    if commit != DIAR_TRANSFORMERS_COMMIT:
        raise RuntimeError(
            f"transformers commit {commit} != {DIAR_TRANSFORMERS_COMMIT}; not loading {model_id}"
        )
    if model_id != DIARIZATION_MODEL_ID:
        raise RuntimeError(f"refusing model {model_id}; expected {DIARIZATION_MODEL_ID}")
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForAudioFrameClassification.from_pretrained(model_id)
    model.eval()
    device = str(getattr(model, "device", "cpu"))
    if device != "cpu":
        raise RuntimeError(f"model loaded on {device}, expected cpu; not switching devices")
    name = type(model).__name__
    if "Diarization" not in name and "Nemotron" not in name:
        raise RuntimeError(f"loaded {name}, which is not the diarization model")
    return processor, model


def _load_audio(path: Path, sampling_rate: int, work_dir: Path):
    from transformers.audio_utils import load_audio

    try:
        return load_audio(str(path), sampling_rate=sampling_rate)
    except Exception:
        wav = work_dir / f"{path.stem}.16k.wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ar", "16000", "-ac", "1", str(wav)],
                check=True,
            )
            return load_audio(str(wav), sampling_rate=sampling_rate)
        except subprocess.CalledProcessError as second:
            err = (second.stderr or b"") if isinstance(second.stderr, bytes) else (second.stderr or "")
            raise RuntimeError(f"ffmpeg failed: {err or second}") from second
        finally:
            wav.unlink(missing_ok=True)


def diarize_one(path: Path, processor, model, work_dir: Path) -> dict:
    import torch

    sampling_rate = processor.feature_extractor.sampling_rate
    audio = _load_audio(path, sampling_rate, work_dir)
    duration = len(audio) / sampling_rate
    inputs = processor(audio, sampling_rate=sampling_rate)
    inputs = inputs.to(model.device, dtype=model.dtype)
    with torch.inference_mode():
        logits = model(**inputs).logits
    raw = [
        (float(item["Start"]), float(item["End"]), int(item["Speaker"]))
        for item in processor.extract_speaker_dict(logits, inputs.attention_mask)[0]
    ]
    segments, regions, speakers = smooth_diarization(raw)
    return {
        "file": path.name,
        "duration_s": round(duration, 2),
        "frame_ms": FRAME_MS,
        "speakers": speakers,
        "segments": segments,
        "speech_regions": regions,
        "label_prefix": file_prefix(path.name),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asr_skill.runners.diarize")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--work-dir")
    parser.add_argument("--model", default=DIARIZATION_MODEL_ID)
    parser.add_argument("--jobs")
    args = parser.parse_args(argv)
    if args.jobs:
        spec = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
        if spec.get("model") != DIARIZATION_MODEL_ID:
            print(f"refusing model {spec.get('model')}", file=sys.stderr)
            return EXIT_MODEL
        from asr_skill.preflight import over_limit

        try:
            too_long = over_limit([Path(job["input"]) for job in spec["jobs"]])
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_RUNTIME
        if too_long:
            print(f"duration preflight: {too_long}", file=sys.stderr)
            return EXIT_USAGE
        try:
            processor, model = load_model(spec["model"])
        except Exception as exc:
            print(f"load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_MODEL
        failed_runtime = False
        failed_model = False
        for job in spec["jobs"]:
            output = Path(job["output"])
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                result = diarize_one(Path(job["input"]), processor, model, output.parent)
                payload = {
                    "date_dir": spec.get("date_dir", "."),
                    "audio_dir": spec.get("audio_dir", "."),
                    "model": spec["model"],
                    "files": [result],
                }
                write_json(
                    output,
                    {
                        "status": "complete",
                        "input_sha256": job.get("input_sha256"),
                        "params_sha256": job.get("params_sha256"),
                        "empty_speech": not result["segments"],
                        "payload": payload,
                    },
                )
            except RuntimeError as exc:
                failed_runtime = "ffmpeg" in str(exc)
                failed_model = not failed_runtime
                write_json(output, {"status": "failed", "error": str(exc)})
                print(str(exc), file=sys.stderr)
            except Exception as exc:
                failed_model = True
                write_json(output, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
                print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        if failed_runtime:
            return EXIT_RUNTIME
        if failed_model:
            return EXIT_MODEL
        return EXIT_OK
    if args.model != DIARIZATION_MODEL_ID:
        print(f"refusing model {args.model}", file=sys.stderr)
        return EXIT_MODEL
    if args.check or args.load:
        code = check_runtime(args.model)
        if code != EXIT_OK or not args.load:
            return code
        try:
            processor, model = load_model(args.model)
        except Exception as exc:
            print(f"load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_MODEL
        print(f"loaded {type(model).__name__} processor={type(processor).__name__}")
        return EXIT_OK
    if not args.input or not args.output:
        parser.print_help()
        return EXIT_USAGE
    source = Path(args.input)
    work_dir = Path(args.work_dir) if args.work_dir else Path(args.output).parent
    work_dir.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        processor, model = load_model(args.model)
        result = diarize_one(source, processor, model, work_dir)
    except Exception as exc:
        print(f"diarize failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_MODEL
    payload = {
        "date_dir": str(source.parent),
        "audio_dir": ".",
        "model": args.model,
        "generated_at": started,
        "transformers_commit": _commit(),
        "files": [result],
    }
    write_json(Path(args.output), payload)
    print(f"diarized {source.name} segments={len(result['segments'])}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
