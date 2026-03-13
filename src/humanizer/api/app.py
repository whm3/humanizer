from fastapi import FastAPI, HTTPException

from humanizer import __version__
from humanizer.analysis.service import AnalysisService
from humanizer.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    HealthResponse,
    ProviderInfo,
    ProvidersResponse,
    VersionResponse,
)
from humanizer.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    service = AnalysisService(settings)
    app = FastAPI(title=settings.app_name, version=__version__)

    @app.get("/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)

    @app.get("/v1/version", response_model=VersionResponse)
    def version() -> VersionResponse:
        return VersionResponse(status="success", service=settings.app_name, version=settings.app_version)

    @app.get("/v1/providers", response_model=ProvidersResponse)
    def providers() -> ProvidersResponse:
        return ProvidersResponse(
            status="success",
            providers=[ProviderInfo(**provider) for provider in service.list_providers()],
        )

    @app.post("/v1/analyze", response_model=AnalyzeResponse)
    def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
        try:
            result = service.analyze(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return AnalyzeResponse(status="success", result=result)

    @app.post("/v1/analyze/batch", response_model=BatchAnalyzeResponse)
    def analyze_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
        try:
            results = service.analyze_batch(request.items)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return BatchAnalyzeResponse(status="success", results=results)

    return app


app = create_app()
