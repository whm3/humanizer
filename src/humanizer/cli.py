from __future__ import annotations

import argparse
import json
from typing import Sequence

from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest, BatchAnalyzeRequest, HumanizeRequest
from humanizer.commands import CommandService
from humanizer.core.logging_utils import configure_logging
from humanizer.core.settings import get_settings
from humanizer.providers.registry import build_provider_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="humanizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("version")

    providers_parser = subparsers.add_parser("providers")
    providers_subparsers = providers_parser.add_subparsers(dest="providers_command", required=True)
    providers_subparsers.add_parser("list")
    providers_subparsers.add_parser("check")

    analyze_parser = subparsers.add_parser("analyze")
    analyze_input_group = analyze_parser.add_mutually_exclusive_group(required=True)
    analyze_input_group.add_argument("--text")
    analyze_input_group.add_argument("--input-file")
    analyze_input_group.add_argument("--input-url")
    analyze_parser.add_argument("--profile", required=True)
    analyze_parser.add_argument("--content-type", default="auto", choices=["auto", "text", "code"])
    analyze_parser.add_argument("--provider")
    analyze_parser.add_argument("--model")
    analyze_parser.add_argument("--fast-mode", action="store_true")
    analyze_parser.add_argument("--language", default="en")

    batch_parser = subparsers.add_parser("analyze-batch")
    batch_parser.add_argument("--file", required=True)

    humanize_parser = subparsers.add_parser("humanize")
    humanize_input_group = humanize_parser.add_mutually_exclusive_group(required=True)
    humanize_input_group.add_argument("--text")
    humanize_input_group.add_argument("--input-file")
    humanize_input_group.add_argument("--input-url")
    humanize_parser.add_argument("--profile", default="ai_detection")
    humanize_parser.add_argument("--content-type", default="auto", choices=["auto", "text", "code"])
    humanize_parser.add_argument("--provider")
    humanize_parser.add_argument("--model")
    humanize_parser.add_argument("--fast-mode", action="store_true")
    humanize_parser.add_argument("--humanizer-provider")
    humanize_parser.add_argument("--humanizer-model")
    humanize_parser.add_argument("--language", default="en")
    humanize_parser.add_argument("--threshold", type=float, default=0.35)
    humanize_parser.add_argument("--max-iterations", type=int, default=3)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    service = AnalysisService(settings, build_provider_registry(settings))
    commands = CommandService(service)

    if args.command == "health":
        print(json.dumps(commands.health()))
        return 0
    if args.command == "version":
        print(json.dumps(commands.version()))
        return 0
    if args.command == "providers":
        if args.providers_command == "list":
            print(json.dumps(commands.providers()))
            return 0
        if args.providers_command == "check":
            print(json.dumps(commands.provider_status()))
            return 0
        return 0
    if args.command == "analyze":
        print(
            json.dumps(
                commands.analyze(
                    AnalyzeRequest(
                        text=args.text,
                        input_path=args.input_file,
                        input_url=args.input_url,
                        content_type=args.content_type,
                        profile=args.profile,
                        provider=args.provider,
                        model=args.model,
                        fast_mode=args.fast_mode,
                        language_hint=args.language,
                    )
                )
            )
        )
        return 0
    if args.command == "analyze-batch":
        with open(args.file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        print(
            json.dumps(
                commands.analyze_batch(
                    BatchAnalyzeRequest(
                        items=[
                            AnalyzeRequest(**item)
                            for item in payload["items"]
                        ]
                    )
                )
            )
        )
        return 0
    if args.command == "humanize":
        print(
            json.dumps(
                commands.humanize(
                    HumanizeRequest(
                        text=args.text,
                        input_path=args.input_file,
                        input_url=args.input_url,
                        content_type=args.content_type,
                        profile=args.profile,
                        provider=args.provider,
                        model=args.model,
                        fast_mode=args.fast_mode,
                        humanizer_provider=args.humanizer_provider,
                        humanizer_model=args.humanizer_model,
                        language_hint=args.language,
                        threshold=args.threshold,
                        max_iterations=args.max_iterations,
                    )
                )
            )
        )
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
