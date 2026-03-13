from __future__ import annotations

from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import AnalyzeRequest, BatchAnalyzeRequest, HumanizeRequest


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

    def analyze(self, payload: AnalyzeRequest) -> dict[str, object]:
        return {
            "status": "success",
            "result": self.analysis_service.analyze(payload).model_dump(),
        }

    def analyze_batch(self, payload: BatchAnalyzeRequest) -> dict[str, object]:
        return {
            "status": "success",
            "results": [
                item.model_dump() for item in self.analysis_service.analyze_batch(payload.items)
            ],
        }

    def humanize(self, payload: HumanizeRequest) -> dict[str, object]:
        return {
            "status": "success",
            "result": self.analysis_service.humanize_until_threshold(payload).model_dump(),
        }
