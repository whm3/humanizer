# HUMANIZER Project Plan

## Purpose

Build a provider-agnostic text analysis service that accepts text plus an analysis profile and returns normalized structured results. The first goal is a clean, testable rewrite with OpenAI as the first supported provider and Perplexity as the second.

This plan converts the architecture spec into an execution sequence that is practical to implement and validate incrementally.

## Non-Negotiable Constraints

- Keep provider logic behind adapter boundaries.
- Keep prompts and output schemas out of route handlers.
- Return normalized structured responses, not raw provider output.
- Reference secrets from the environment only; never copy secret values into code, logs, docs, or tests.
- Keep live provider calls out of normal CI.
- Keep any internal continuity notes outside the public repository.

## Working Assumptions

- Python 3.12+ is the target runtime.
- FastAPI, Pydantic v2, httpx, uvicorn, and pytest are the starting stack.
- Local smoke testing can use provider credentials loaded from environment variables or a local `.env` file.
- Initial implementation work will live under `src/`.

## Delivery Strategy

Build the service in narrow vertical slices:

1. Establish project scaffolding and core contracts.
2. Deliver one working analysis path with a single provider.
3. Add a second provider without changing the public API shape.
4. Add auth, rate limiting, and audit-oriented logging.
5. Expand profiles and optional persistence only after the core path is stable.

This sequence is designed to validate the architecture early. If the second provider can be added cleanly, the abstraction is probably correct. If not, the design should be corrected before adding more surface area.

## Phase 0: Repository Foundation

### Objectives

- Create the Python project skeleton under `src/`.
- Define request and response schemas.
- Define provider-neutral settings and config loading.
- Create one analysis profile as the reference implementation.
- Establish testing, linting, and local run entrypoints.

### Deliverables

- `src/app.py`
- `src/api/`
- `src/core/`
- `src/analysis/`
- `src/providers/`
- `tests/`
- `.gitignore`
- `pyproject.toml`
- local env example file without secrets

### Definition of Done

- The app starts locally.
- `GET /v1/health` and `GET /v1/version` respond.
- Core Pydantic models exist for analyze requests and normalized results.
- One profile is defined with schema and prompt configuration.
- Tests run locally without live provider calls.

## Phase 1: First End-to-End Analysis Flow

### Objectives

- Implement the provider adapter base interface.
- Implement the OpenAI adapter first.
- Build the analysis orchestration service.
- Expose `POST /v1/analyze`.
- Normalize provider output into the common response schema.

### Deliverables

- `src/providers/base.py`
- `src/providers/openai_adapter.py`
- `src/analysis/service.py`
- `src/analysis/normalization.py`
- `src/api/routes_analyze.py`
- unit and API tests for the single-item analyze flow

### Definition of Done

- A valid analyze request produces a normalized response through OpenAI.
- Provider errors are mapped into stable API errors.
- Raw provider payloads are not returned by default.
- Adapter tests cover malformed JSON, timeout, and rate-limit scenarios.
- API tests cover validation and response schema stability.

## Phase 2: Multi-Provider Validation

### Objectives

- Implement the Perplexity adapter.
- Confirm the API contract remains unchanged when switching providers.
- Add provider listing and provider capability reporting.
- Add `POST /v1/analyze/batch` with per-item status semantics.

### Deliverables

- `src/providers/perplexity_adapter.py`
- `GET /v1/providers`
- `POST /v1/analyze/batch`
- expanded normalization tests across both providers

### Definition of Done

- The same analyze contract works with OpenAI and Perplexity.
- Batch requests return partial successes and failures correctly.
- Provider-specific behavior remains confined to adapter code.
- Smoke tests confirm both providers work with local environment credentials.

## Phase 3: Security and Operational Controls

### Objectives

- Add API key authentication for service clients.
- Add request limits and provider timeout controls.
- Add rate limiting hooks.
- Add structured audit-style logging for request metadata and decision summary.

### Deliverables

- `src/auth/api_keys.py`
- `src/auth/rate_limits.py`
- request size and batch size guards
- structured application logging
- debug controls that do not expose provider secrets

### Definition of Done

- Unauthorized requests are rejected consistently.
- Request and batch limits are enforced.
- Logs contain useful metadata without leaking secrets or raw provider credentials.
- Error responses remain stable and do not expose internal transport details.

## Phase 4: Product Expansion

### Objectives

- Add more analysis profiles.
- Add optional persistence for audit and reporting use cases.
- Add admin/reporting endpoints if justified by actual usage.

### Deliverables

- additional profile modules under `src/analysis/profiles/`
- optional persistence layer under `src/persistence/`
- admin-oriented routes if needed

### Definition of Done

- New profiles can be added without route changes.
- Persistence is optional and isolated from the core analysis path.
- Admin/debug features are access-controlled.

## Cross-Cutting Workstreams

### Testing

- Unit tests for profile selection, provider selection, normalization, fallback logic, and error mapping.
- Adapter tests with mocked provider responses.
- API tests for auth, validation, schema stability, and batch semantics.
- Separate smoke tests for real provider calls using environment-referenced credentials.

### Observability

- request IDs in responses and logs
- latency measurement per provider call
- structured logs for failures and retry-worthy conditions

### Documentation

- keep any internal continuity notes outside the public repository
- update architecture docs only when design decisions materially change
- add setup and run instructions once the app skeleton exists

## Initial Build Order

1. Create `pyproject.toml`, `.gitignore`, and the `src/` package skeleton.
2. Implement settings, schemas, and health/version routes.
3. Implement one profile definition.
4. Implement the provider adapter protocol and OpenAI adapter.
5. Implement the analysis service and single analyze route.
6. Add tests around the first vertical slice.
7. Add the Perplexity adapter and batch route.
8. Add auth, limits, and audit logging.

## Main Risks

- Structured output quality may vary by model and provider.
- Provider APIs may differ enough that normalization needs iteration.
- It is easy to let route handlers absorb business logic unless boundaries are enforced early.
- Live provider tests can become flaky or costly if not kept separate from normal tests.

## Risk Mitigations

- Keep a strict normalized response schema from the start.
- Mock provider transports heavily in automated tests.
- Add live smoke tests only as gated manual checks.
- Validate the architecture by integrating the second provider before adding optional persistence or admin features.

## Immediate Next Step

Start Phase 0 by creating the Python project scaffold, provider-neutral settings, shared schemas, and the health/version endpoints.
