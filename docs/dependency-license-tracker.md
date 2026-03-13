# Dependency and License Tracker

## Purpose

Track dependencies and any upstream code introduced into the project, including license obligations and why each item is needed.

Update this file whenever a new dependency, SDK, library, or copied/adapted upstream code path is added.

## Tracking Table

| Item | Type | Version / Ref | Purpose | License | Requirements / Notes |
| --- | --- | --- | --- | --- | --- |
| Python | Runtime | 3.13.2 local runtime detected on 2026-03-13 | Local development runtime for the service | PSF | Project target remains Python 3.12+ per spec; confirm final runtime compatibility during implementation. |
| FastAPI | Dependency | 0.135.1 | API framework | License metadata blank in `pip show` | Verify upstream license before redistribution-sensitive release steps. |
| Pydantic | Dependency | 2.12.5 | Schema validation and settings models | License metadata blank in `pip show` | Verify upstream license before redistribution-sensitive release steps. |
| pydantic-settings | Dependency | 2.13.1 | Settings and environment loading | License metadata blank in `pip show` | Verify upstream license before redistribution-sensitive release steps. |
| httpx | Dependency | 0.28.1 | Outbound HTTP transport | BSD-3-Clause | Used for provider calls and future URL ingestion. |
| uvicorn | Dependency | 0.41.0 | Local ASGI server | License metadata blank in `pip show` | Verify upstream license before redistribution-sensitive release steps. |
| pytest | Dev dependency | 8.4.2 | Test runner | MIT | Local automated test execution. |
| pytest-asyncio | Dev dependency | 0.26.0 | Async pytest support | License metadata blank in `pip show` | Added to support async API test fixtures. |
| pypdf | Dependency | 5.9.0 | PDF text extraction for supported document inputs | License metadata blank in `pip show` | Verify upstream license before redistribution-sensitive release steps. |
| python-docx | Dependency | 1.2.0 | DOCX text extraction for supported document inputs | MIT | Pulls in `lxml`. |
| lxml | Transitive dependency | 6.0.2 | XML processing required by `python-docx` | BSD-3-Clause | Transitive dependency from DOCX support. |

## Upstream Code Notes

No upstream code has been copied into this repository yet.

The current architecture is informed by the rewrite specification in `docs/textguard-rewrite-architecture.md`, but no third-party source code has been imported from the predecessor system.

## Process Notes

- Do not copy source from upstream projects without recording origin and license.
- If SDKs are used, record their published license when they are added.
- If vendored code is ever introduced, document file paths and attribution requirements here.
