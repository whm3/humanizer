# Multimodal Workflow Plan

Status: Future enhancement. Do not prioritize this work ahead of the active text workflow, provider expansion, token autodetection, and iterative humanization loop.

## Purpose

Extend the HUMANIZER workflow pattern beyond text into:

- images
- video
- music

Each modality should follow the same core delivery rules already established for text:

- API first
- CLI parity
- local development and testability
- multi-source aggregation by default when provider credentials are available
- single-source override through API and CLI
- normalized outputs with consensus and worst-case summaries where appropriate

## Product Direction

The text pipeline is the reference pattern:

1. accept an input payload and profile
2. resolve one or more sources/providers
3. gather per-source results
4. normalize those results
5. produce consensus and worst-case summaries
6. return one stable API/CLI output shape for the modality

The same orchestration pattern should be reused for image, video, and music analysis, with modality-specific request models and provider adapters.

## Modality Targets

### Images

Initial use cases:

- AI-generated image likelihood
- manipulation/edit detection signals
- style classification
- moderation/risk screening
- custom visual classification tasks

Suggested API surface:

- `POST /v1/analyze/image`
- `POST /v1/analyze/image/batch`

Suggested CLI surface:

- `humanizer analyze-image`
- `humanizer analyze-image-batch`

Input modes:

- local file path
- URL reference
- base64 or binary upload later if needed

### Video

Initial use cases:

- AI-generated video likelihood
- clip-level risk/moderation screening
- scene or segment classification
- motion/style consistency analysis

Suggested API surface:

- `POST /v1/analyze/video`
- `POST /v1/analyze/video/batch`

Suggested CLI surface:

- `humanizer analyze-video`
- `humanizer analyze-video-batch`

Input modes:

- local file path
- URL reference
- future support for pre-extracted frame bundles if needed

### Music

Initial use cases:

- AI-generated music likelihood
- style/genre classification
- vocal/instrumentation structure signals
- moderation or policy checks on audio content and metadata

Suggested API surface:

- `POST /v1/analyze/music`
- `POST /v1/analyze/music/batch`

Suggested CLI surface:

- `humanizer analyze-music`
- `humanizer analyze-music-batch`

Input modes:

- local file path
- URL reference
- future support for extracted features or stems if needed

## Shared Request Pattern

Each modality should support:

- input reference
- profile
- optional single-provider override
- optional model override
- optional metadata

Example image request shape:

```json
{
  "input": "/data/sample.png",
  "profile": "image_ai_detection",
  "provider": "openai",
  "metadata": {
    "source": "local-uat"
  }
}
```

## Shared Response Pattern

Each modality should return:

- selected providers
- per-source normalized results
- consensus summary
- worst-case summary
- request ID
- total latency

Example response shape:

```json
{
  "status": "success",
  "result": {
    "modality": "image",
    "profile": "image_ai_detection",
    "provider_selection": "all_available",
    "selected_providers": ["openai", "gemini"],
    "source_results": [],
    "consensus": {},
    "worst_case": {},
    "request_id": "req_123",
    "latency_ms": 910
  }
}
```

## Implementation Strategy

### Phase A: Shared Architecture

- generalize the analysis orchestration layer so modality-specific adapters can plug into the same aggregation flow
- define modality-aware request and response schemas
- keep provider selection and token autodetection shared across modalities

### Phase B: Image Workflow

- add image schemas, profiles, and command/API entrypoints
- implement placeholder/local adapters first if needed
- add automated tests and UAT coverage

### Phase C: Video Workflow

- add video schemas, profiles, and command/API entrypoints
- define whether providers consume full files, URLs, or extracted frames
- add automated tests and UAT coverage

### Phase D: Music Workflow

- add music schemas, profiles, and command/API entrypoints
- define whether providers consume full files, URLs, or extracted audio features
- add automated tests and UAT coverage

## UAT Expectations

Each modality should have UAT coverage for:

- health of the modality-specific API path
- single-source override
- default all-available-source behavior
- consensus output
- worst-case output
- invalid input path or URL
- unsupported profile
- missing provider credentials

## Dependency and License Notes

Do not add modality-specific SDKs, media-processing libraries, or upstream code without updating:

- `docs/dependency-license-tracker.md`
- `docs/uat-plan.md`
- local operator notes, if maintained separately from the public repository

If image, video, or music processing requires external codecs, media libraries, or copied upstream utilities, their licenses and operational constraints must be documented before adoption.

## Immediate Next Step

Do not start modality-specific implementation yet. Finish stabilizing the text workflow and its automated tests first, then revisit this plan as a future expansion track.
