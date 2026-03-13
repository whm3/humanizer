from __future__ import annotations

import argparse
import json
from typing import Sequence

from humanizer import __version__
from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest
from humanizer.core.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="humanizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("version")

    providers_parser = subparsers.add_parser("providers")
    providers_subparsers = providers_parser.add_subparsers(dest="providers_command", required=True)
    providers_subparsers.add_parser("list")

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--text", required=True)
    analyze_parser.add_argument("--profile", required=True)
    analyze_parser.add_argument("--provider")
    analyze_parser.add_argument("--model")

    batch_parser = subparsers.add_parser("analyze-batch")
    batch_parser.add_argument("--file", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    service = AnalysisService(settings)

    if args.command == "health":
        print(json.dumps({"status": "ok", "service": settings.app_name, "version": settings.app_version}))
        return 0
    if args.command == "version":
        print(json.dumps({"status": "success", "service": settings.app_name, "version": __version__}))
        return 0
    if args.command == "providers":
        print(json.dumps({"status": "success", "providers": service.list_providers()}))
        return 0
    if args.command == "analyze":
        result = service.analyze(
            AnalyzeRequest(
                text=args.text,
                profile=args.profile,
                provider=args.provider,
                model=args.model,
            )
        )
        print(json.dumps({"status": "success", "result": result.model_dump()}))
        return 0
    if args.command == "analyze-batch":
        with open(args.file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        items = [AnalyzeRequest(**item) for item in payload["items"]]
        results = service.analyze_batch(items)
        print(json.dumps({"status": "success", "results": [item.model_dump() for item in results]}))
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
