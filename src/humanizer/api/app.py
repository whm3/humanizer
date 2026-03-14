from fastapi import FastAPI

from humanizer.analysis.service import AnalysisService
from humanizer.api.routes_analyze import build_analyze_router
from humanizer.api.routes_providers import build_provider_router
from humanizer.api.routes_system import build_system_router
from humanizer.commands import CommandService
from humanizer.core.logging_utils import configure_logging
from humanizer.core.settings import get_settings
from humanizer.providers.registry import build_provider_registry


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    service = AnalysisService(settings, build_provider_registry(settings))
    commands = CommandService(service)
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(build_system_router(commands))
    app.include_router(build_provider_router(commands))
    app.include_router(build_analyze_router(commands))
    return app


app = create_app()
