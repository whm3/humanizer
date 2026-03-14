from __future__ import annotations

import json
from pathlib import Path

from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import (
    AnalyzeRequest,
    ApiKeyOverrides,
    BatchAnalyzeRequest,
    HumanizeRequest,
    ProviderStatusRequest,
)
from humanizer.core.errors import HumanizerError, ValidationError
from humanizer.core.settings import with_api_key_overrides
from humanizer.providers.registry import build_provider_registry


class CommandService:
    def __init__(self, analysis_service: AnalysisService):
        self.analysis_service = analysis_service

    def health(self) -> dict[str, str]:
        settings = self.analysis_service.settings
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    def version(self) -> dict[str, str]:
        settings = self.analysis_service.settings
        return {
            "status": "success",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    def providers(self) -> dict[str, object]:
        return {
            "status": "success",
            "providers": self.analysis_service.list_providers(),
        }

    def provider_status(self, payload: ProviderStatusRequest | None = None) -> dict[str, object]:
        service = self._service_for_request(payload.api_keys, payload.ignore_env_keys) if payload else self.analysis_service
        return {
            "status": "success",
            "providers": service.provider_status(),
        }

    def analyze(self, payload: AnalyzeRequest) -> dict[str, object]:
        service = self._service_for_request(payload.api_keys, payload.ignore_env_keys)
        return {
            "status": "success",
            "result": service.analyze(payload).model_dump(),
        }

    def analyze_batch(self, payload: BatchAnalyzeRequest) -> dict[str, object]:
        if len(payload.items) > self.analysis_service.settings.batch_max_items:
            raise ValidationError("batch exceeds configured limit")
        return {
            "status": "success",
            "results": self._analyze_batch_results(payload),
        }

    def humanize(self, payload: HumanizeRequest) -> dict[str, object]:
        service = self._service_for_request(payload.api_keys, payload.ignore_env_keys)
        response = {
            "status": "success",
            "result": service.humanize_until_threshold(payload).model_dump(),
        }
        self._write_debug_output(payload.debug_output_path, response)
        return response

    def _service_for_request(
        self,
        api_keys: ApiKeyOverrides | None,
        ignore_env_keys: bool,
    ) -> AnalysisService:
        if not ignore_env_keys and api_keys is None:
            return self.analysis_service
        override_settings = with_api_key_overrides(
            self.analysis_service.settings,
            ignore_env_keys=ignore_env_keys,
            overrides=api_keys.model_dump(exclude_none=True) if api_keys else None,
        )
        return AnalysisService(override_settings, build_provider_registry(override_settings))

    def _analyze_batch_results(self, payload: BatchAnalyzeRequest) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for item in payload.items:
            try:
                results.append(
                    {
                        "status": "success",
                        "result": self._service_for_request(
                            item.api_keys,
                            item.ignore_env_keys,
                        ).analyze(item).model_dump(),
                        "error": None,
                    }
                )
            except HumanizerError as exc:
                results.append({"status": "error", "result": None, "error": str(exc)})
        return results

    def _write_debug_output(self, debug_output_path: str | None, payload: dict[str, object]) -> None:
        if not debug_output_path:
            return
        output_path = Path(debug_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
