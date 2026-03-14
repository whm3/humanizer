from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from humanizer.providers.base import (
    ProviderRequest,
    ProviderResult,
    RewriteRequest,
    RewriteReviewResult,
)


PROFILE_LABELS = {
    "ai_detection": {"likely_ai_assisted", "likely_human"},
    "humanization_feedback": {"needs_humanization", "naturally_varied"},
}

POSITIVE_LABELS = {
    "ai_detection": "likely_ai_assisted",
    "humanization_feedback": "needs_humanization",
}


class StructuredProviderPayload(BaseModel):
    label: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: str
    signals: list[str]
    explanation: str


class RewriteReviewPayload(BaseModel):
    supported: bool
    confidence: str
    issues: list[str]
    explanation: str


def build_analysis_instructions(request: ProviderRequest) -> str:
    allowed_labels = sorted(PROFILE_LABELS[request.profile_name])
    return (
        f"{request.system_prompt}\n"
        f"You are analyzing {request.content_type} content.\n"
        f"Primary language hint: {request.language_hint}.\n"
        "Return only a single JSON object with these keys:\n"
        '- "label": one of ' + ", ".join(allowed_labels) + "\n"
        '- "score": number from 0.0 to 1.0 where higher means stronger detection for the active profile\n'
        '- "confidence": one of "low", "medium", "high"\n'
        '- "signals": array of 1 to 4 short evidence phrases\n'
        '- "explanation": short plain-English explanation\n'
        "Do not include markdown fences, citations, or extra commentary."
    )


def build_rewrite_instructions(request: RewriteRequest) -> str:
    requested_changes = "\n".join(f"- {change}" for change in request.changes) or "- make the prose sound less machine-generated"
    signal_notes = "\n".join(f"- {signal}" for signal in request.signals[:4]) or "- no detector signals were provided"
    escalation = ""
    if request.iteration > 1 or request.prior_score > (request.target_score + 0.20):
        escalation = (
            "This is not the first rewrite attempt and the text still scores too high.\n"
            "Be more aggressive:\n"
            "- break overly symmetrical structure\n"
            "- remove generic slogans, platitudes, and polished essay transitions\n"
            "- replace abstractions with plain phrasing or source-grounded specifics already present in the text\n"
            "- vary paragraph length and sentence rhythm more noticeably\n"
            "- collapse or simplify headings if they make the text feel templated\n"
            "- avoid neat rhetorical contrasts like 'it's not X, it's Y'\n"
            "- avoid ceremonial, campaign-style, or manifesto-like language\n"
            "- do not preserve the original sentence-by-sentence cadence if that cadence feels synthetic\n"
        )
    return (
        "Rewrite the user's text so it reads more naturally human while preserving the original meaning.\n"
        f"Primary language hint: {request.language_hint}.\n"
        f"Content type: {request.content_type} prose.\n"
        f"Current detector score: {request.prior_score:.2f}. Target score: {request.target_score:.2f}. Rewrite iteration: {request.iteration}.\n"
        "Requirements:\n"
        "- Return only the rewritten text.\n"
        "- Preserve markdown where it remains useful, but you may simplify rigid headings or separators when they make the text feel templated.\n"
        "- Do not add code fences, preambles, explanations, citations, URLs, bibliography sections, or source attributions.\n"
        "- Do not introduce new factual claims, dates, statistics, laws, names, or numbers that were not already present in the source text.\n"
        "- Remove fabricated or implausible technical specificity when it is not necessary to preserve meaning.\n"
        "- Prefer concrete, natural phrasing over polished boilerplate.\n"
        "- Keep the output readable but do not over-smooth it into generic assistant prose.\n"
        "- Prefer a plainspoken, slightly uneven human voice over a polished speech or essay voice.\n"
        "- Avoid repeated motivational framing, abstract slogans, tidy parallel constructions, and balanced thesis sentences.\n"
        "- It is acceptable to merge, split, reorder, or shorten nearby sentences when that makes the passage feel less templated.\n"
        "- It is acceptable to drop obvious throat-clearing, transition padding, or repetitive setup when meaning is preserved.\n"
        "- Use contractions and direct phrasing when natural for the language and tone.\n"
        "- If the source sounds ceremonial, make it sound like a capable person explaining the same point directly.\n"
        "Detector signals to address:\n"
        f"{signal_notes}\n"
        "Requested changes:\n"
        f"{requested_changes}\n"
        f"{escalation}"
    )


def build_rewrite_review_instructions(language_hint: str) -> str:
    return (
        "Review whether a rewritten passage stays faithful to the source passage.\n"
        f"Primary language hint: {language_hint}.\n"
        "Return only a single JSON object with these keys:\n"
        '- "supported": boolean, true only if the rewrite does not introduce unsupported claims and additions make sense in context\n'
        '- "confidence": one of "low", "medium", "high"\n'
        '- "issues": array of short issue phrases; use an empty array if supported is true\n'
        '- "explanation": short plain-English explanation\n'
        "Treat invented citations, URLs, dates, statistics, laws, named entities, or factual claims not grounded in the source as unsupported.\n"
        "Do not include markdown fences or extra commentary."
    )


def parse_provider_json(profile_name: str, payload_text: str) -> ProviderResult:
    candidate = payload_text.strip()
    if candidate.startswith("```"):
        candidate = _strip_code_fence(candidate)
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"provider returned non-JSON content: {payload_text[:200]}") from exc

    try:
        payload = StructuredProviderPayload.model_validate(parsed)
    except PydanticValidationError as exc:
        raise ValueError("provider returned JSON that does not match the normalized schema") from exc

    allowed_labels = PROFILE_LABELS[profile_name]
    if payload.label not in allowed_labels:
        raise ValueError(f"provider returned unsupported label for profile {profile_name}: {payload.label}")
    if payload.confidence not in {"low", "medium", "high"}:
        raise ValueError(f"provider returned unsupported confidence level: {payload.confidence}")

    signals = [signal.strip() for signal in payload.signals if signal.strip()][:4]
    if not signals:
        raise ValueError("provider returned no usable signals")

    score = _normalize_score(profile_name, payload.label, payload.score)

    return ProviderResult(
        label=payload.label,
        score=round(score, 4),
        confidence=payload.confidence,
        signals=signals,
        explanation=payload.explanation.strip(),
    )


def parse_rewrite_review_json(payload_text: str) -> RewriteReviewResult:
    candidate = payload_text.strip()
    if candidate.startswith("```"):
        candidate = _strip_code_fence(candidate)
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"provider returned non-JSON review content: {payload_text[:200]}") from exc

    try:
        payload = RewriteReviewPayload.model_validate(parsed)
    except PydanticValidationError as exc:
        raise ValueError("provider returned review JSON that does not match the normalized schema") from exc

    if payload.confidence not in {"low", "medium", "high"}:
        raise ValueError(f"provider returned unsupported confidence level: {payload.confidence}")

    return RewriteReviewResult(
        supported=payload.supported,
        confidence=payload.confidence,
        issues=[issue.strip() for issue in payload.issues if issue.strip()][:4],
        explanation=payload.explanation.strip(),
    )


def _normalize_score(profile_name: str, label: str, score: float) -> float:
    positive_label = POSITIVE_LABELS[profile_name]
    if label == positive_label and score < 0.5:
        return 1.0 - score
    if label != positive_label and score > 0.5:
        return 1.0 - score
    return score


def gemini_response_schema(profile_name: str) -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "label": {
                "type": "STRING",
                "enum": sorted(PROFILE_LABELS[profile_name]),
            },
            "score": {"type": "NUMBER"},
            "confidence": {
                "type": "STRING",
                "enum": ["low", "medium", "high"],
            },
            "signals": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
            },
            "explanation": {"type": "STRING"},
        },
        "required": ["label", "score", "confidence", "signals", "explanation"],
        "propertyOrdering": ["label", "score", "confidence", "signals", "explanation"],
    }


def openai_json_schema(profile_name: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {
                "type": "string",
                "enum": sorted(PROFILE_LABELS[profile_name]),
            },
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "signals": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
            },
            "explanation": {"type": "string"},
        },
        "required": ["label", "score", "confidence", "signals", "explanation"],
    }


def openai_rewrite_review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "supported": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
            },
            "explanation": {"type": "string"},
        },
        "required": ["supported", "confidence", "issues", "explanation"],
    }


def gemini_rewrite_review_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "supported": {"type": "BOOLEAN"},
            "confidence": {"type": "STRING", "enum": ["low", "medium", "high"]},
            "issues": {"type": "ARRAY", "items": {"type": "STRING"}},
            "explanation": {"type": "STRING"},
        },
        "required": ["supported", "confidence", "issues", "explanation"],
        "propertyOrdering": ["supported", "confidence", "issues", "explanation"],
    }


def _strip_code_fence(candidate: str) -> str:
    lines = candidate.splitlines()
    if not lines:
        return candidate
    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
