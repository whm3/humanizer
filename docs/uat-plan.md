# HUMANIZER UAT Plan

## Purpose

Define user acceptance testing for each project action and function. Every shipped capability should be testable through both API and CLI unless a documented exception is approved.

This document starts with the planned core functions and should be updated as implementation grows.

## UAT Conventions

- API-first: the API contract is the primary acceptance target.
- CLI parity: the CLI must expose equivalent core behavior for local operators, scripts, and agents.
- Local execution: UAT should run from this environment.
- Secrets: use environment-referenced credentials only.
- Evidence: record pass/fail notes and relevant request IDs during execution when available.

## UAT Matrix

### Function: Health Check

- Goal: Confirm the service is running and responsive.
- API path: `GET /v1/health`
- CLI path: `humanizer health`
- Preconditions: service process started locally
- Test steps:
  1. Call the API health endpoint.
  2. Run the CLI health command.
- Expected result:
  1. API returns success status and health metadata.
  2. CLI reports the same health state in structured output.
- Failure cases:
  1. service unavailable
  2. inconsistent CLI and API status output

### Function: Version Check

- Goal: Confirm the running version/build identity.
- API path: `GET /v1/version`
- CLI path: `humanizer version`
- Preconditions: service process started locally
- Test steps:
  1. Call the API version endpoint.
  2. Run the CLI version command.
- Expected result:
  1. both interfaces report the same version metadata
- Failure cases:
  1. version missing
  2. API and CLI version mismatch

### Function: List Providers

- Goal: Confirm which providers are enabled and available.
- API path: `GET /v1/providers`
- CLI path: `humanizer providers list`
- Preconditions: configuration loaded locally
- Test steps:
  1. Call the providers API.
  2. Run the providers CLI command.
- Expected result:
  1. both interfaces return the same enabled provider set and capability notes
- Failure cases:
  1. disabled provider shown as enabled
  2. provider metadata mismatch across interfaces

### Function: Analyze Single Text

- Goal: Submit one text payload and receive a normalized structured analysis result.
- API path: `POST /v1/analyze`
- CLI path: `humanizer analyze`
- Preconditions:
  1. service process started locally
  2. at least one provider configured through environment references
  3. selected profile available
- Test steps:
  1. submit a valid analyze request through the API
  2. submit an equivalent request through the CLI
  3. compare normalized outputs
- Expected result:
  1. both interfaces return the same normalized result shape
  2. provider, model, profile, label, score, confidence, and request ID fields are present as defined
  3. raw provider payload is not exposed by default
- Failure cases:
  1. invalid profile
  2. provider timeout
  3. malformed provider response
  4. API and CLI normalization mismatch

### Function: Analyze Batch Text

- Goal: Submit multiple texts and receive per-item results without failing the entire batch when one item errors.
- API path: `POST /v1/analyze/batch`
- CLI path: `humanizer analyze-batch`
- Preconditions:
  1. service process started locally
  2. provider configured
  3. batch size within allowed limits
- Test steps:
  1. submit a mixed-validity batch through the API
  2. submit the same batch through the CLI
- Expected result:
  1. results are returned per item
  2. one failure does not erase successful items
  3. both interfaces preserve the same item ordering and statuses
- Failure cases:
  1. oversized batch
  2. partial provider failure
  3. whole-batch failure caused by one invalid item

### Function: Client Authentication

- Goal: Ensure only authorized clients can call protected functions.
- API path: protected routes such as `POST /v1/analyze`
- CLI path: `humanizer analyze` with configured client credential reference
- Preconditions:
  1. auth configured locally
- Test steps:
  1. call protected API without valid auth
  2. call protected API with valid auth
  3. run equivalent CLI actions with missing and valid auth context
- Expected result:
  1. unauthorized attempts fail cleanly
  2. authorized attempts succeed
- Failure cases:
  1. secret leakage in error output
  2. inconsistent auth behavior across interfaces

### Function: Rate Limit and Request Guardrails

- Goal: Enforce request size, batch size, and rate-limit rules.
- API path: protected and bounded routes
- CLI path: equivalent CLI commands
- Preconditions:
  1. limits configured locally
- Test steps:
  1. send oversized payload
  2. send oversized batch
  3. exceed rate threshold where supported
- Expected result:
  1. requests fail with stable validation or limit errors
  2. CLI surfaces the same policy outcome in structured form
- Failure cases:
  1. unbounded request accepted
  2. internal traceback exposed to the caller

## Execution Record Template

Use this template when running UAT for a specific function:

```text
Function:
Date:
Tester:
Interface: API | CLI
Environment:
Input Summary:
Expected Result:
Actual Result:
Request ID(s):
Outcome: PASS | FAIL
Notes:
```

## Expansion Rule

Whenever a new function or action is added:

- add the API path
- add the CLI path
- define success and failure UAT expectations
- update this document before the feature is considered complete
