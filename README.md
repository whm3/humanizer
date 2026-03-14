MAKE YOUR OUTPUT MORE REPLICANT LESS CLANKER

## Overview

HUMANIZER is a local-first service for analyzing documents with multiple commercial LLMs and rewriting prose to reduce AI-detection signals without changing the underlying meaning.

The project is built API-first:

- applications and agents can use the HTTP API
- local operators can use the CLI
- major workflows are intended to exist in both interfaces

This repository does not currently ship a proprietary detector trained on a large labeled corpus of human-written versus AI-written material. Instead, it orchestrates commercial LLM providers, normalizes their judgments, compares their outputs, and applies guarded rewrite loops on top of that provider layer.

The current value is in:

- provider orchestration
- normalized scoring
- consensus and worst-case reporting
- guarded rewrite iteration
- mixed-document handling
- local deployment and testing

Future versions may add purpose-trained hosted or local models for detection, review, or rewriting.

## Current Scope

Implemented now:

- FastAPI API and matching CLI
- multi-provider detection
- provider autodetection from environment variables
- provider preflight/status checks before longer runs
- raw text, Markdown, PDF, DOCX, URL, and local file input handling
- source-code analysis support
- prose-plus-code handling with fenced code block preservation
- iterative prose humanization with re-analysis
- rewrite validation with a secondary provider
- local token-usage logging

Still being tuned:

- rewrite effectiveness on polished synthetic prose
- latency and cost of multi-provider rewrite loops
- detector calibration on ambiguous or highly polished samples

## Providers

Current live providers:

- `anthropic`
- `gemini`
- `grok`
- `openai`
- `perplexity`

Current detection providers:

- `anthropic`
- `gemini`
- `openai`
- `perplexity`

Current rewrite-capable providers:

- `anthropic`
- `gemini`
- `grok`
- `openai`
- `perplexity`

`grok` is live and available, but it is currently rewrite-only. It is not part of the detection consensus set because its detector behavior on the project fixture set is not calibrated enough for release use yet.

`deepseek` scaffolding exists but is not part of the current MVP provider surface.

## Repository Layout

- `src/humanizer/` application code
- `tests/` automated tests
- `docs/` architecture, plans, UAT, smoke-test notes, and dependency/license tracking
- `testdocs/` sample fixtures for calibration and smoke testing

## Requirements

- Python `3.12+`
- a project-local virtual environment
- provider API keys supplied through the environment or `~/.env`

The app can consume keys from variables including:

- `OPENAI_API_KEY`
- `PERPLEXITY_API_KEY`
- `HUMANIZER_GEMINI_PAID_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `HUMANIZER_GEMINI_API_KEY`
- `HUMANIZER_ANTHROPIC_PAID_KEY`
- `ANTHROPIC_API_KEY`
- `HUMANIZER_GROK_PAID_KEY`
- `HUMANIZER_GROK_KEY`
- `GROK_API_KEY`
- `XAI_API_KEY`

Secrets should remain in local environment files or environment variables only. Do not copy them into tracked source, docs, fixtures, or logs.

## Setup

Create and activate the virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
./.venv/bin/pip install -e '.[dev]'
```

## Running

Run the API:

```bash
./.venv/bin/uvicorn humanizer.api.app:app --reload
```

Run the CLI:

```bash
./.venv/bin/python -m humanizer.cli --help
```

Check provider availability before a live run:

```bash
./.venv/bin/python -m humanizer.cli providers check
```

Check provider availability using only request-scoped keys:

```bash
./.venv/bin/python -m humanizer.cli providers \
  --ignore-env-keys \
  --openai-api-key "$OPENAI_API_KEY" \
  check
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

For live rewrite evaluation, prefer one provider at a time and write a local debug artifact:

```bash
./.venv/bin/python -m humanizer.cli humanize \
  --input-file testdocs/Sub-QuantumVernierCalibration.md \
  --humanizer-provider anthropic \
  --threshold 0.40 \
  --max-iterations 1 \
  --fast-mode \
  --debug-output-file .local/subquantum-anthropic-humanize.json
```

Use the faster lower-fanout mode for interactive runs:

```bash
./.venv/bin/python -m humanizer.cli analyze \
  --input-file testdocs/greenwald.txt \
  --fast-mode
```

Analyze with request-scoped credentials and ignore environment keys:

```bash
./.venv/bin/python -m humanizer.cli analyze \
  --text "This is a sample paragraph." \
  --profile ai_detection \
  --provider openai \
  --ignore-env-keys \
  --openai-api-key "$OPENAI_API_KEY"
```

## API

Current routes:

- `GET /v1/health`
- `GET /v1/version`
- `GET /v1/providers`
- `GET /v1/providers/status`
- `POST /v1/providers/status`
- `POST /v1/analyze`
- `POST /v1/analyze/batch`
- `POST /v1/humanize`

Example analyze request:

```json
{
  "text": "Sample text to analyze.",
  "profile": "ai_detection",
  "fast_mode": false,
  "ignore_env_keys": false
}
```

Example analyze request with request-scoped keys:

```json
{
  "text": "Sample text to analyze.",
  "profile": "ai_detection",
  "provider": "openai",
  "ignore_env_keys": true,
  "api_keys": {
    "openai": "sk-live-key-here"
  }
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
  "humanizer_model": "gpt-5-mini",
  "fast_mode": true
}
```

## Input Handling

Supported inputs include:

- raw text
- Markdown
- PDF
- DOCX
- plain text files
- source code files
- fetched URLs

Content rules:

- pure source code can be analyzed but is not humanized
- prose documents that contain fenced code blocks keep those blocks unchanged during rewrite
- long prose documents are rewritten section-by-section using a shared document-level rewrite brief to reduce visible chunking

## Detection And Rewrite Model

Detection is probabilistic. Results can differ across providers, and polished AI-generated material can still score as likely human on some detectors.

To make that uncertainty visible, the service returns:

- per-provider results
- a `consensus` result
- a `worst_case` result
- summary text for detections, trends, and evidence

Rewrite is also guarded:

- one provider generates the rewrite
- at least one different provider validates it
- unsupported additions can cause the rewrite to be rejected
- debug mode can expose accepted, rejected, unchanged, or skipped rewrite states plus candidate rewrites

Operational note:

- for live rewrite benchmarking, run one humanizer provider at a time rather than parallel side-by-side sessions
- write the result to a local debug artifact file when comparing providers
- this gives a cleaner comparison and avoids wasting quota on multiple long guarded rewrite loops running at once

## Logging

Set `HUMANIZER_LOG_LEVEL=DEBUG` or `LOG_LEVEL=DEBUG` to increase runtime visibility.

Debug logging includes:

- provider request attempts
- retries and provider failures
- humanization iteration progress
- provider preflight failures

Debug logging does not include:

- secret values
- full prompt bodies
- full source document contents

## Token Usage Tracking

Live provider calls can write local token usage records to `.local/token-usage.jsonl`.

This file is ignored by Git and is intended for local quota and cost tracking only.

Live humanize runs can also write a local JSON debug artifact with candidate rewrites and review outcomes when `debug_output_path` or `--debug-output-file` is set.

Relevant settings:

```bash
TOKEN_USAGE_LOG_ENABLED=true
TOKEN_USAGE_LOG_PATH=.local/token-usage.jsonl
```

## Credential Sources

By default, the service loads provider keys from the environment and `~/.env`.

For API and CLI workflows, you can also supply request-scoped keys directly:

- CLI flags like `--openai-api-key`, `--gemini-api-key`, and `--anthropic-api-key`
- API request bodies using the `api_keys` object

If the local environment contains keys for another application, set `ignore_env_keys=true` in the API or `--ignore-env-keys` in the CLI to ignore environment-loaded keys for that request.

## Testing

Run the automated suite:

```bash
./.venv/bin/pytest
```

The current automated coverage includes:

- settings and provider autodetection
- API routes
- CLI behavior
- analysis orchestration
- input loading
- rewrite guardrails
- provider preflight/status checks

For runtime smoke procedures, see [`docs/smoke-test-automation.md`](docs/smoke-test-automation.md).

## Documentation

Important project docs:

- [`docs/textguard-rewrite-architecture.md`](docs/textguard-rewrite-architecture.md)
- [`docs/project-plan.md`](docs/project-plan.md)
- [`docs/development-standards.md`](docs/development-standards.md)
- [`docs/uat-plan.md`](docs/uat-plan.md)
- [`docs/dependency-license-tracker.md`](docs/dependency-license-tracker.md)
- [`docs/smoke-test-automation.md`](docs/smoke-test-automation.md)
