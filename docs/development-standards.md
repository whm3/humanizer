# HUMANIZER Development Standards

## Core Delivery Rules

- Build the project API-first.
- Every user-facing function must have a corresponding API operation.
- Provide CLI access for the same capabilities so apps, scripts, and agents can use the system either through HTTP or local command execution.
- Keep all development local to this environment unless a specific external call is required for controlled testing.
- Use the project virtual environment at `.venv/` for isolated Python execution.
- Reference secrets from environment sources only. Never copy secret values into repository files, logs, tests, or docs.
- Record actions, decisions, and lessons learned in `docs/breadcrumbs.log`.

## API-First Rule

The API contract is the primary interface for the system.

This means:

- business capabilities are designed as API operations first
- internal services should map cleanly to request and response models
- CLI commands should call the same application services used by the API
- adding a capability only in the CLI or only in internal code is not sufficient

## CLI Parity Rule

Each significant function should have:

- an API endpoint or API operation
- a CLI command or subcommand with equivalent behavior
- matching request/option semantics where practical
- consistent structured output expectations

The CLI is a first-class local interface, not a separate product surface.

## Local-Only Development Rule

- Develop, run, and test within this local workspace.
- Do not depend on remote deployment infrastructure during normal development.
- Real provider tests may call upstream APIs, but only from the local environment and only through environment-referenced credentials.

## Environment Isolation

Use the local virtual environment for Python commands:

```bash
source .venv/bin/activate
```

If a tool, package, or script is added, it should be installed and run from this environment unless there is a documented exception.

## Dependency and Upstream Code Tracking

As dependencies or upstream code are introduced, document:

- package or upstream project name
- version or commit reference when known
- purpose in this project
- license
- any attribution or redistribution requirement
- any security or operational caveat

Record this in `docs/dependency-license-tracker.md`.

## UAT Rule

Every action and function added to the project should have a corresponding UAT entry covering:

- purpose
- trigger path through API
- trigger path through CLI
- setup and preconditions
- expected result
- failure cases
- operator notes

Record this in `docs/uat-plan.md`.

## Initial Interface Mapping

The following target capabilities should be built with API and CLI parity:

- health check
- version check
- list providers
- analyze single text
- analyze batch text
- debug or admin inspection only if explicitly enabled and access-controlled

## Review Gate

Before a feature is considered complete:

- API behavior exists
- CLI behavior exists or is explicitly deferred with rationale
- automated tests exist at the appropriate level
- a UAT entry exists or is updated
- dependency and license impact is documented if anything new was introduced
