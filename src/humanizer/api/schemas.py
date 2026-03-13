from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)
    profile: str
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class BatchAnalyzeRequest(BaseModel):
    items: list[AnalyzeRequest] = Field(min_length=1)


class AnalyzeResult(BaseModel):
    profile: str
    label: str
    score: float
    confidence: Literal["low", "medium", "high"]
    signals: list[str]
    provider: str
    model: str
    request_id: str
    latency_ms: int


class AnalyzeResponse(BaseModel):
    status: Literal["success"]
    result: AnalyzeResult


class BatchAnalyzeItemResponse(BaseModel):
    status: Literal["success", "error"]
    result: AnalyzeResult | None = None
    error: str | None = None


class BatchAnalyzeResponse(BaseModel):
    status: Literal["success"]
    results: list[BatchAnalyzeItemResponse]


class ProviderInfo(BaseModel):
    name: str
    enabled: bool
    default_model: str


class ProvidersResponse(BaseModel):
    status: Literal["success"]
    providers: list[ProviderInfo]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class VersionResponse(BaseModel):
    status: Literal["success"]
    service: str
    version: str
