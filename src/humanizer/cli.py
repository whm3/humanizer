from __future__ import annotations

import argparse
import json
from typing import Sequence

from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import (
    AnalyzeRequest,
    BatchAnalyzeRequest,
    HumanizeRequest,
    ProviderStatusRequest,
)
from humanizer.commands import CommandService
from humanizer.core.logging_utils import configure_logging
from humanizer.core.settings import get_settings
from humanizer.providers.registry import build_provider_registry


def add_api_key_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ignore-env-keys", action="store_true")
    parser.add_argument("--anthropic-api-key")
    parser.add_argument("--deepseek-api-key")
    parser.add_argument("--gemini-api-key")
    parser.add_argument("--grok-api-key")
    parser.add_argument("--openai-api-key")
    parser.add_argument("--perplexity-api-key")


def build_api_key_overrides(args: argparse.Namespace) -> dict[str, str] | None:
    overrides = {
        "anthropic": args.anthropic_api_key,
        "deepseek": args.deepseek_api_key,
        "gemini": args.gemini_api_key,
        "grok": args.grok_api_key,
        "openai": args.openai_api_key,
        "perplexity": args.perplexity_api_key,
    }
    filtered = {provider: api_key for provider, api_key in overrides.items() if api_key}
    return filtered or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="humanizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("version")

    providers_parser = subparsers.add_parser("providers")
    add_api_key_arguments(providers_parser)
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
    add_api_key_arguments(analyze_parser)

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
    humanize_parser.add_argument("--debug-output-file")
    humanize_parser.add_argument("--language", default="en")
    humanize_parser.add_argument("--threshold", type=float, default=0.35)
    humanize_parser.add_argument("--max-iterations", type=int, default=3)
    humanize_parser.add_argument("--max-rewrite-sections", type=int)
    add_api_key_arguments(humanize_parser)

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
            print(
                json.dumps(
                    commands.provider_status(
                        ProviderStatusRequest(
                            ignore_env_keys=args.ignore_env_keys,
                            api_keys=build_api_key_overrides(args),
                        )
                    )
                )
            )
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
                        ignore_env_keys=args.ignore_env_keys,
                        api_keys=build_api_key_overrides(args),
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
                        debug_output_path=args.debug_output_file,
                        language_hint=args.language,
                        ignore_env_keys=args.ignore_env_keys,
                        api_keys=build_api_key_overrides(args),
                        threshold=args.threshold,
                        max_iterations=args.max_iterations,
                        max_rewrite_sections=args.max_rewrite_sections,
                    )
                )
            )
        )
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
