from __future__ import annotations

from fastapi import APIRouter

from humanizer.api.schemas import HealthResponse, VersionResponse
from humanizer.commands import CommandService


def build_system_router(commands: CommandService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(**commands.health())

    @router.get("/v1/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(**commands.version())

    return router
