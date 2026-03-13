# Smoke Test Automation

## Purpose

Document the smoke-test layer for HUMANIZER so runtime validation is repeatable and does not rely on memory or ad hoc command history.

This document complements:

- automated unit and integration coverage in `tests/`
- the UAT matrix in `docs/uat-plan.md`
- the continuity log in `docs/breadcrumbs.log`

## Current Smoke-Test Coverage

The project currently has two validation layers:

### 1. Automated pytest coverage

Run from the local virtual environment:

```bash
./.venv/bin/pytest
```

This covers:

- settings and environment token detection
- API routes through in-process async testing
- CLI commands
- analysis service behavior
- request/response schemas
- input loading
- source-code handling rules

Latest known full-suite result during active development:

- `52 passed`

Current default extracted-text limit:

- `250000` characters
- configurable through `REQUEST_TEXT_MAX_CHARS`
- this limit applies to extracted text length, not raw file size in bytes

### 2. Runtime smoke-test commands

These are lighter-weight, behavior-oriented checks that exercise the current branch like an operator would.

They are useful because they can catch issues that a green test suite may miss, especially around:

- environment variable naming
- CLI runtime behavior
- file-path flows
- provider autodetection

## Recommended Smoke-Test Sequence

Run these from the project root:

### Provider Detection

```bash
./.venv/bin/python -m humanizer.cli providers list
```

Expected result:

- JSON output
- provider list contains only providers with detected credentials
- after the current local environment update, Gemini should appear if `HUMANIZER_GEMINI_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY` is set

### Analyze Inline Text

```bash
./.venv/bin/python -m humanizer.cli analyze \
  --text "This is a short sample paragraph for smoke testing." \
  --profile ai_detection
```

Expected result:

- JSON output
- `status=success`
- aggregate result includes:
  - `selected_providers`
  - `consensus`
  - `worst_case`
  - `summary`

### Humanize Inline Text

```bash
./.venv/bin/python -m humanizer.cli humanize \
  --text "Furthermore, individuals utilize numerous repetitive phrases in order to communicate." \
  --threshold 0.40 \
  --max-iterations 2
```

Expected result:

- JSON output
- rewrite iteration history present
- `humanizer_provider` and `humanizer_model` present
- final analysis present

### Analyze Source Code

```bash
tmpdir=$(mktemp -d)
printf '%s\n' 'import os' '' 'def main():' '    return os.getcwd()' > "$tmpdir/sample.py"
./.venv/bin/python -m humanizer.cli analyze --input-file "$tmpdir/sample.py" --profile ai_detection
```

Expected result:

- `content_type` is `code`
- analysis succeeds
- humanization summary is disabled for code inputs

### Humanize Mixed Prose and Code

```bash
tmpdir=$(mktemp -d)
printf '%s\n' '# Whitepaper' '' 'This section discusses a method.' '' '```python' 'import os' 'def main():' '    return os.getcwd()' '```' '' 'Furthermore, individuals utilize numerous repetitive phrases in order to communicate.' > "$tmpdir/sample.md"
./.venv/bin/python -m humanizer.cli humanize --input-file "$tmpdir/sample.md" --threshold 0.40 --max-iterations 2
```

Expected result:

- command succeeds
- prose is rewritten
- fenced code block remains present and unmodified

### In-Process API Smoke Test

```bash
tmpfile=$(mktemp /tmp/humanizer-api-probe-XXXX.py)
printf '%s\n' \
  'import asyncio' \
  'from httpx import ASGITransport, AsyncClient' \
  'from humanizer.api.app import create_app' \
  '' \
  'async def main():' \
  '    transport = ASGITransport(app=create_app())' \
  '    async with AsyncClient(transport=transport, base_url="http://testserver") as client:' \
  '        response = await client.post("/v1/analyze", json={"text": "API smoke test paragraph.", "profile": "ai_detection"})' \
  '        print(response.status_code)' \
  '        print(response.json()["status"])' \
  '        print(response.json()["result"]["content_type"])' \
  '' \
  'asyncio.run(main())' > "$tmpfile"
./.venv/bin/python "$tmpfile"
```

Expected result:

- `200`
- `success`
- `text`

## Current Smoke-Test Findings

The most recent smoke-test pass confirmed:

- provider autodetection works for the current environment
- Gemini detection now works with `HUMANIZER_GEMINI_API_KEY`
- live provider-backed scoring works for `gemini`, `openai`, and `perplexity`
- file-based analyze and humanize flows work after validator fixes
- source-code analysis works
- fenced code blocks are preserved during mixed-document humanization
- in-process API analyze requests work

Recent live fixture results:

- `testdocs/Sub-QuantumVernierCalibration.md`: consensus `likely_ai_assisted` at `0.90`
- `testdocs/Hamlet.pdf`: consensus `likely_human` at `0.07`
- `testdocs/GlobalWarming.pdf`: consensus `likely_human` at `0.33`, with `perplexity` as a stricter outlier at `0.85`

## Known Caveats

- The current rewrite logic is still deterministic and placeholder-oriented; only the detector path is live-provider-backed right now.
- Mixed prose/code humanization preserves code blocks, but surrounding Markdown formatting may still be compressed in ways that should be improved before polished end-user documentation is finalized.
- Smoke tests are currently documented as commands rather than packaged in a single shell script. That is acceptable for now, but a dedicated script would improve repeatability later.
- Very large documents can still exceed the extracted-text limit if their parsed text is longer than `REQUEST_TEXT_MAX_CHARS`, even when the file size itself seems reasonable.
- Some providers appear to express score as confidence in their chosen label rather than raw AI-likelihood; the normalization layer now corrects for that, but this behavior should continue to be watched during future smoke tests.

## When To Run Smoke Tests

Run the smoke sequence:

- before opening or updating a major PR
- after changing request/response contracts
- after changing input-loading behavior
- after changing provider autodetection rules
- after changing CLI parsing

## Next Automation Upgrade

If smoke testing becomes routine, add a checked-in helper such as:

- `tools/smoke-test.sh`

That script should wrap the commands above and fail fast when expected JSON fields or status codes are missing.
