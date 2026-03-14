from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalyzeRequest(BaseModel):
    text: str | None = None
    input_path: str | None = None
    input_url: str | None = None
    content_type: Literal["auto", "text", "code"] = "auto"
    profile: str
    provider: str | None = None
    model: str | None = None
    fast_mode: bool = False
    language_hint: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_text_or_input_path(self) -> "AnalyzeRequest":
        if not (self.text and self.text.strip()) and not self.input_path and not self.input_url:
            raise ValueError("one of text, input_path, or input_url must be provided")
        return self


class BatchAnalyzeRequest(BaseModel):
    items: list[AnalyzeRequest] = Field(min_length=1)


class HumanizeRequest(BaseModel):
    text: str | None = None
    input_path: str | None = None
    input_url: str | None = None
    content_type: Literal["auto", "text", "code"] = "auto"
    profile: str = "ai_detection"
    provider: str | None = None
    model: str | None = None
    fast_mode: bool = False
    humanizer_provider: str | None = None
    humanizer_model: str | None = None
    language_hint: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)
    threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    max_iterations: int = Field(default=3, ge=1, le=10)

    @field_validator("text")
    @classmethod
    def humanize_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_text_or_input_path(self) -> "HumanizeRequest":
        if not (self.text and self.text.strip()) and not self.input_path and not self.input_url:
            raise ValueError("one of text, input_path, or input_url must be provided")
        return self


class AnalyzeResult(BaseModel):
    provider: str
    model: str
    profile: str
    label: str
    score: float
    confidence: Literal["low", "medium", "high"]
    signals: list[str]
    explanation: str | None = None
    request_id: str
    latency_ms: int


class AggregateSummary(BaseModel):
    label: str
    score: float
    confidence: Literal["low", "medium", "high"]
    signals: list[str]
    providers_considered: list[str]


class AnalysisSummary(BaseModel):
    detections: str
    trends: str
    ai_evidence: str
    humanization: str
    humanization_changes: list[str]


class AnalyzeAggregateResult(BaseModel):
    content_type: Literal["text", "code"]
    profile: str
    request_id: str
    latency_ms: int
    provider_selection: str
    selected_providers: list[str]
    source_results: list[AnalyzeResult]
    consensus: AggregateSummary
    worst_case: AnalyzeResult
    summary: AnalysisSummary


class HumanizeIteration(BaseModel):
    iteration: int
    input_text: str
    output_text: str
    applied_changes: list[str]
    rewrite_status: Literal["accepted", "rejected", "unchanged", "skipped"]
    rewrite_rejection_reason: str | None = None
    candidate_rewrites: list[dict[str, Any]] = Field(default_factory=list)
    analysis: AnalyzeAggregateResult


class HumanizeResult(BaseModel):
    original_text: str
    rewritten_text: str
    threshold: float
    humanizer_provider: str
    humanizer_model: str
    reached_threshold: bool
    iterations: list[HumanizeIteration]
    final_analysis: AnalyzeAggregateResult


class AnalyzeResponse(BaseModel):
    status: Literal["success"]
    result: AnalyzeAggregateResult


class HumanizeResponse(BaseModel):
    status: Literal["success"]
    result: HumanizeResult


class BatchAnalyzeItemResponse(BaseModel):
    status: Literal["success", "error"]
    result: AnalyzeAggregateResult | None = None
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


class ProviderStatusInfo(BaseModel):
    name: str
    available: bool
    default_model: str
    detail: str


class ProviderStatusResponse(BaseModel):
    status: Literal["success"]
    providers: list[ProviderStatusInfo]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class VersionResponse(BaseModel):
    status: Literal["success"]
    service: str
    version: str
