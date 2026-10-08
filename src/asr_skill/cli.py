"""Command-line entry for the scaffold.

This module does not load speech models and does not read recordings.
"""

from __future__ import annotations

import argparse
import json
import sys

from asr_skill import __version__
from asr_skill.contracts import (
    EXIT_NOT_IMPLEMENTED,
    EXIT_OK,
    EXIT_USAGE,
    IMPLEMENTED,
    PHASE,
    PLANNED_COMMANDS,
)


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _version_line() -> str:
    flag = "true" if IMPLEMENTED else "false"
    return f"asr-skill {__version__} phase={PHASE} implemented={flag}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asr-skill",
        description=(
            "Local speaker-attributed transcription. "
            "This build is a scaffold and does not transcribe audio."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the package version and scaffold phase",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", help="Print the package version and scaffold phase")
    sub.add_parser(
        "doctor",
        help="Report scaffold status. Does not contact a model or the network",
    )
    for name in PLANNED_COMMANDS:
        planned = sub.add_parser(name, help="Not implemented in this scaffold")
        planned.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return parser


def _not_implemented(command: str) -> int:
    _print_json(
        {
            "command": command,
            "phase": PHASE,
            "implemented": False,
            "error": "not_implemented",
        }
    )
    return EXIT_NOT_IMPLEMENTED


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(item in ("-h", "--help") for item in args):
        build_parser().parse_args(args)
    if "--version" in args or (args and args[0] == "version"):
        print(_version_line())
        return EXIT_OK
    if args and args[0] == "doctor":
        _print_json(
            {
                "command": "doctor",
                "phase": PHASE,
                "implemented": IMPLEMENTED,
                "models_ready": False,
                "network": False,
            }
        )
        return EXIT_OK
    if args and args[0] in PLANNED_COMMANDS:
        return _not_implemented(args[0])
    build_parser().print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
