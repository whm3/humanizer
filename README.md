MAKE YOUR OUTPUT MORE REPLICANT LESS CLANKER

## Overview

HUMANIZER is a local-first, API-first service for analyzing text and rewriting prose to reduce AI-detection signals while keeping the source meaning intact.

The project is built around a provider-agnostic contract:

- apps and agents can use the HTTP API
- local operators can use the CLI
- major functions are intended to have both API and CLI coverage

Current live provider-backed detection supports:

- `openai`
- `gemini`
- `perplexity`

The service can:

- analyze text with one provider or all detected providers
- return per-provider results plus `consensus` and `worst_case`
- summarize detection trends and AI evidence
- produce humanization guidance
- iteratively rewrite prose and re-run detection until a threshold or iteration limit is reached

## Current Status

This repository is in active MVP development.

Implemented now:

- FastAPI API and matching CLI
- multi-provider detection
- provider autodetection from environment variables
- raw text, Markdown, PDF, DOCX, local file, and URL input handling
- source-code analysis support
- fenced code block preservation inside mixed prose documents
- provider-backed rewrite path for prose humanization
- rewrite review guardrails to reduce hallucinated additions

Still being tuned:

- rewrite effectiveness on highly polished rhetorical prose
- runtime cost and latency of multi-provider rewrite review
- handling of temporary provider unavailability under heavy live usage

## Repository Layout

- `src/humanizer/` application code
- `tests/` automated test suite
- `docs/` architecture, plans, UAT, dependency/license tracking, smoke-test notes, and breadcrumb log
- `testdocs/` local smoke-test fixtures

## Requirements

- Python `3.12+`
- project-local virtual environment
- provider API keys in `~/.env` or `.env`

Current environment variables used by the app include:

- `OPENAI_API_KEY`
- `PERPLEXITY_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `HUMANIZER_GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `DEEPSEEK_API_KEY`
- `GROK_API_KEY`
- `XAI_API_KEY`

Secrets are referenced from the environment only and should not be copied into repository files, logs, or docs.

## Setup

Create and activate the local virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project and dev dependencies:

```bash
./.venv/bin/pip install -e '.[dev]'
```

## Running

Run the API locally:

```bash
./.venv/bin/uvicorn humanizer.api.app:app --reload
```

Run the CLI:

```bash
./.venv/bin/python -m humanizer.cli --help
```

List detected providers:

```bash
./.venv/bin/python -m humanizer.cli providers list
```

Analyze inline text:

```bash
./.venv/bin/python -m humanizer.cli analyze \
  --text "This is a sample paragraph." \
  --profile ai_detection
```

Humanize a local document:

```bash
./.venv/bin/python -m humanizer.cli humanize \
  --input-file testdocs/draft.md \
  --threshold 0.40 \
  --max-iterations 2
```

## API

Current routes:

- `GET /v1/health`
- `GET /v1/version`
- `GET /v1/providers`
- `POST /v1/analyze`
- `POST /v1/analyze/batch`
- `POST /v1/humanize`

Example analyze request:

```json
{
  "text": "Sample text to analyze.",
  "profile": "ai_detection"
}
```

Example humanize request:

```json
{
  "input_path": "testdocs/draft.md",
  "profile": "ai_detection",
  "threshold": 0.4,
  "max_iterations": 2,
  "humanizer_provider": "openai",
  "humanizer_model": "gpt-5-mini"
}
```

## Input Types

Supported text inputs currently include:

- raw text
- Markdown
- PDF
- DOCX
- source code files
- fetched URLs

Content typing behavior:

- pure source code can be analyzed but is not humanized
- prose documents with fenced code blocks keep those blocks unchanged during rewrite

## Testing

Run the automated suite:

```bash
./.venv/bin/pytest
```

The current local suite covers:

- settings and provider autodetection
- API routes
- CLI behavior
- analysis service behavior
- input loading
- rewrite guardrails

For runtime smoke procedures, see:

- `docs/smoke-test-automation.md`

## Provider Notes

Detection:

- `openai`, `gemini`, and `perplexity` are live-backed today when keys are configured
- offline tests use deterministic stub adapters

Rewrite:

- provider-backed rewrite is enabled
- rewritten prose is reviewed before acceptance
- additions are only accepted if all active review providers support them as grounded in the source/context

Operational note:

- free-tier Gemini quotas were too restrictive for the current multi-pass rewrite/review flow
- paid Gemini quota materially improved runtime stability during live smoke testing

## Documentation

Important project docs:

- `docs/textguard-rewrite-architecture.md`
- `docs/project-plan.md`
- `docs/development-standards.md`
- `docs/uat-plan.md`
- `docs/dependency-license-tracker.md`
- `docs/smoke-test-automation.md`

## Limitations

- rewrite quality is still being tuned for difficult rhetorical content
- strict review guardrails can reject aggressive rewrites and slow convergence
- multimodal image/video/music workflows are future work, not active MVP scope
- some development fixtures in `testdocs/` are intended for local validation and may not ship as release artifacts
