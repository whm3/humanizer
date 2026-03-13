from __future__ import annotations

from fastapi import APIRouter, HTTPException

from humanizer.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    HumanizeRequest,
    HumanizeResponse,
)
from humanizer.commands import CommandService
from humanizer.core.errors import HumanizerError


def build_analyze_router(commands: CommandService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/analyze", response_model=AnalyzeResponse)
    async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
        try:
            return AnalyzeResponse(**commands.analyze(request))
        except HumanizerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/v1/analyze/batch", response_model=BatchAnalyzeResponse)
    async def analyze_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
        try:
            return BatchAnalyzeResponse(**commands.analyze_batch(request))
        except HumanizerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/v1/humanize", response_model=HumanizeResponse)
    async def humanize(request: HumanizeRequest) -> HumanizeResponse:
        try:
            return HumanizeResponse(**commands.humanize(request))
        except HumanizerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
