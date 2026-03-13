from __future__ import annotations

from fastapi import APIRouter

from humanizer.api.schemas import ProviderInfo, ProvidersResponse
from humanizer.commands import CommandService


def build_provider_router(commands: CommandService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/providers", response_model=ProvidersResponse)
    async def providers() -> ProvidersResponse:
        payload = commands.providers()
        return ProvidersResponse(
            status="success",
            providers=[ProviderInfo(**provider) for provider in payload["providers"]],
        )

    return router
