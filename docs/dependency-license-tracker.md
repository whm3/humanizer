# Dependency and License Tracker

## Purpose

Track dependencies and any upstream code introduced into the project, including license obligations and why each item is needed.

Update this file whenever a new dependency, SDK, library, or copied/adapted upstream code path is added.

## Tracking Table

| Item | Type | Version / Ref | Purpose | License | Requirements / Notes |
| --- | --- | --- | --- | --- | --- |
| Python | Runtime | 3.13.2 local runtime detected on 2026-03-13 | Local development runtime for the service | PSF | Project target remains Python 3.12+ per spec; confirm final runtime compatibility during implementation. |
| FastAPI | Planned dependency | TBD | API framework | TBD | Add exact version and license when installed. |
| Pydantic | Planned dependency | TBD | Schema validation and settings models | TBD | Add exact version and license when installed. |
| httpx | Planned dependency | TBD | Outbound provider HTTP transport | TBD | Add exact version and license when installed. |
| uvicorn | Planned dependency | TBD | Local ASGI server | TBD | Add exact version and license when installed. |
| pytest | Planned dependency | TBD | Test runner | TBD | Add exact version and license when installed. |

## Upstream Code Notes

No upstream code has been copied into this repository yet.

The current architecture is informed by the rewrite specification in `docs/textguard-rewrite-architecture.md`, but no third-party source code has been imported from the predecessor system.

## Process Notes

- Do not copy source from upstream projects without recording origin and license.
- If SDKs are used, record their published license when they are added.
- If vendored code is ever introduced, document file paths and attribution requirements here.
