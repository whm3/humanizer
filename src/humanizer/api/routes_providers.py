from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException

from humanizer.api.schemas import (
    ProviderInfo,
    ProviderStatusRequest,
    ProviderStatusInfo,
    ProviderStatusResponse,
    ProvidersResponse,
)
from humanizer.commands import CommandService
from humanizer.core.errors import HumanizerError


def build_provider_router(commands: CommandService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/providers", response_model=ProvidersResponse)
    async def providers() -> ProvidersResponse:
        payload = commands.providers()
        return ProvidersResponse(
            status="success",
            providers=[ProviderInfo(**provider) for provider in payload["providers"]],
        )

    @router.get("/v1/providers/status", response_model=ProviderStatusResponse)
    async def provider_status() -> ProviderStatusResponse:
        payload = commands.provider_status()
        return ProviderStatusResponse(
            status="success",
            providers=[ProviderStatusInfo(**provider) for provider in payload["providers"]],
        )

    @router.post("/v1/providers/status", response_model=ProviderStatusResponse)
    async def provider_status_with_keys(request: ProviderStatusRequest) -> ProviderStatusResponse:
        try:
            payload = commands.provider_status(request)
        except HumanizerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ProviderStatusResponse(
            status="success",
            providers=[ProviderStatusInfo(**provider) for provider in payload["providers"]],
        )

    return router
