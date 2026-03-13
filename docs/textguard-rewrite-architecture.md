# Text Analysis Service Rewrite Architecture

## Recommendation

Rewrite from scratch rather than fork `TextGuardAI`.

The existing project is small, but it already has the kind of debt that is cheaper to replace than to preserve:

- provider coupling is hardcoded to DeepSeek in the core client
- the README, route names, and implementation do not line up cleanly
- "MCP" terminology is misleading and not functionally important to the design
- provider settings are not abstracted cleanly
- this is fundamentally a thin LLM-backed classification service, which is straightforward to rebuild well

If the goal is to preserve the intent and product shape while making OpenAI and Perplexity first-class options, a clean rebuild is the better path.

## Product Intent

Build a service that accepts text, applies a configurable analysis prompt, and returns structured results for things like:

- AI-generated text likelihood
- style/humanization scoring
- spam or abuse screening
- tone/risk categorization
- custom org-specific classification tasks

The service should not be tied to one model vendor. It should treat the model as a pluggable scoring engine behind a stable API.

## Design Goals

- Provider-agnostic from day one
- Stable API contract regardless of backend model
- Strict structured outputs, not freeform prose
- Clear separation between prompt policy and transport code
- Cheap to operate for self-hosted or internal-team use
- Easy to extend with new model vendors later
- Observable and testable without depending on live vendor calls for every test

## Recommended Stack

- Python 3.12+
- FastAPI
- Pydantic v2
- httpx for outbound provider calls
- uvicorn for local serving
- pytest for tests
- optional Redis for rate limiting / caching
- optional Postgres for persistent audit and result storage

## High-Level Architecture

```text
Client
  -> FastAPI API layer
  -> Auth / rate limit / request validation
  -> Analysis service
      -> Prompt policy
      -> Provider adapter
      -> Output normalizer
      -> Confidence / heuristic post-processing
  -> Response formatter
  -> Optional persistence / audit log
```

Core rule: the API layer should never know whether the result came from OpenAI, Perplexity, or anything else.

## Core Components

### 1. API Layer

Provide clean endpoints such as:

- `POST /v1/analyze`
- `POST /v1/analyze/batch`
- `GET /v1/providers`
- `GET /v1/health`
- `GET /v1/version`

The request model should define:

- input text
- analysis profile
- provider override optional
- model override optional
- response mode optional
- metadata optional

Example request:

```json
{
  "text": "Sample text to analyze",
  "profile": "ai_detection",
  "provider": "openai",
  "model": "gpt-5-mini",
  "metadata": {
    "source": "reddit-draft"
  }
}
```

### 2. Analysis Service

This is the orchestration layer.

Responsibilities:

- validate profile selection
- choose provider and model
- build the prompt or structured request
- call the provider adapter
- normalize provider response into a common schema
- attach local heuristics if desired
- emit final result

### 3. Provider Adapter Interface

Create a narrow interface such as:

```python
class ProviderAdapter(Protocol):
    async def analyze(self, request: ProviderRequest) -> ProviderResult:
        ...
```

Implement adapters for:

- `OpenAIAdapter`
- `PerplexityAdapter`
- optional `DeepSeekAdapter`

This keeps vendor-specific details isolated to one directory.

### 4. Prompt Policy Layer

Prompts and schemas should not live inline inside API handlers.

Instead, define profiles:

- `ai_detection`
- `spam_detection`
- `risk_review`
- `humanization_feedback`

Each profile should own:

- system prompt / instruction set
- output schema
- temperature / inference defaults
- provider compatibility rules
- post-processing rules

This allows the product to evolve without changing route code.

### 5. Output Normalization Layer

Different providers return different shapes and quality levels. Normalize them into one schema.

Example normalized response:

```json
{
  "profile": "ai_detection",
  "provider": "openai",
  "model": "gpt-5-mini",
  "label": "likely_ai_assisted",
  "score": 0.71,
  "confidence": "medium",
  "signals": [
    "high structural regularity",
    "low lexical variation",
    "overly even sentence rhythm"
  ],
  "explanation": "Text shows repeated high-regularity phrasing patterns.",
  "request_id": "req_123",
  "latency_ms": 842
}
```

Do not leak raw vendor output unless an explicit debug mode is enabled.

## Provider Support Strategy

### OpenAI

Two viable integration modes:

#### Option A: Chat Completions

Fastest path for parity with the existing DeepSeek-style implementation.

Pros:

- easiest migration path
- similar request shape to DeepSeek
- low implementation risk

Cons:

- not OpenAI's forward-looking default

#### Option B: Responses API

Better long-term choice if this becomes a real product.

Pros:

- current OpenAI direction
- better structure for future tool and schema use

Cons:

- slightly more implementation work
- not as close to the original DeepSeek call pattern

Recommendation: start with one OpenAI adapter that uses the current preferred OpenAI API for structured output, but keep the provider abstraction generic enough that swapping transport style later is not disruptive.

### Perplexity

Perplexity is relatively easy to support if the service keeps an OpenAI-compatible abstraction.

Notes:

- use it as an optional provider, not the default architecture anchor
- verify model output stability for structured JSON before relying on it for strict scoring workflows
- treat citation-specific features as optional extras, not part of the core contract

## Suggested Directory Structure

```text
HUMANIZER/
  docs/
    text-analysis-product-spec.md
    textguard-rewrite-architecture.md
  src/
    app.py
    api/
      routes_analyze.py
      routes_admin.py
      schemas.py
    core/
      settings.py
      logging.py
      errors.py
    analysis/
      service.py
      profiles/
        ai_detection.py
        spam_detection.py
        humanization_feedback.py
      normalization.py
      heuristics.py
    providers/
      base.py
      openai_adapter.py
      perplexity_adapter.py
      deepseek_adapter.py
    auth/
      api_keys.py
      rate_limits.py
    persistence/
      models.py
      repository.py
  tests/
    test_api.py
    test_analysis_service.py
    test_openai_adapter.py
    test_perplexity_adapter.py
    fixtures/
```

## API Contract

### Analyze

`POST /v1/analyze`

Request:

```json
{
  "text": "string",
  "profile": "ai_detection",
  "provider": "openai",
  "model": "gpt-5-mini",
  "metadata": {}
}
```

Response:

```json
{
  "status": "success",
  "result": {
    "profile": "ai_detection",
    "label": "likely_ai_assisted",
    "score": 0.71,
    "confidence": "medium",
    "signals": ["signal 1", "signal 2"],
    "provider": "openai",
    "model": "gpt-5-mini",
    "request_id": "req_123",
    "latency_ms": 842
  }
}
```

### Batch Analyze

`POST /v1/analyze/batch`

This should process items independently and return per-item status rather than fail the whole batch if one provider call fails.

## Configuration Model

Use neutral settings names, not provider-branded env vars.

Examples:

- `DEFAULT_PROVIDER`
- `DEFAULT_MODEL`
- `OPENAI_API_KEY`
- `PERPLEXITY_API_KEY`
- `DEEPSEEK_API_KEY`
- `ENABLE_PROVIDER_OPENAI`
- `ENABLE_PROVIDER_PERPLEXITY`
- `ENABLE_AUDIT_LOG`
- `DATABASE_URL`
- `REDIS_URL`

This avoids rewriting the whole config surface every time a provider changes.

## Security Model

### Minimum

- API key auth for clients
- request size limits
- provider timeout caps
- structured logging without raw secret leakage
- no provider keys exposed in user-visible errors
- per-key rate limits
- input validation on text size and batch size

### Recommended

- audit log of request metadata and decision summary
- encrypted persistence if storing user text
- configurable retention period
- admin-only debug mode
- provider allowlist per customer or tenant

## Testing Strategy

### Unit Tests

- prompt/profile selection
- provider selection logic
- normalization logic
- fallback behavior
- error mapping

### Adapter Tests

Mock provider responses, including:

- malformed JSON
- timeout
- 429 rate limit
- provider 5xx
- partial batch failures

### API Tests

- auth enforcement
- validation behavior
- response schema stability
- batch semantics

### Live Smoke Tests

Have a separate manual or gated test suite for real vendor calls with:

- OpenAI
- Perplexity
- optional DeepSeek

Do not make CI depend on live paid endpoints.

## Migration Strategy From TextGuardAI

If preserving the product intent matters, migrate only these ideas:

- single-text and batch-text endpoints
- tiered API access concept if still useful
- simple usage stats

Do not preserve:

- DeepSeek-specific naming
- MCP branding
- route/doc mismatches
- hardcoded provider assumptions

## Delivery Plan

### Phase 0

- create clean repo
- define schemas
- implement provider-neutral settings
- build one analysis profile

### Phase 1

- implement OpenAI adapter
- implement analyze endpoint
- add normalization layer
- add tests

### Phase 2

- implement Perplexity adapter
- add batch endpoint
- add API key auth and rate limits
- add audit logging

### Phase 3

- add persistence
- add more profiles
- add admin and reporting endpoints

## Bottom Line

A rewrite is the better engineering choice.

This service is small enough that rebuilding it cleanly is cheaper than carrying forward DeepSeek-specific naming, weak abstraction boundaries, and mismatched docs. If the goal is a durable text-analysis service with OpenAI or Perplexity support, start clean and keep provider logic behind a strict adapter boundary.
