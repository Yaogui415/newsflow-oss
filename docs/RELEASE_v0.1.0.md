# NewsFlow OSS v0.1.0 — Initial public release

NewsFlow is now available as an open-source project.

This first public release introduces NewsFlow as a full-stack newsroom workflow prototype for event tracking, evidence organization, approval chains, correction handling, and post-publication monitoring.

## Why this project matters

Many AI tools for journalism focus on the final text: drafting, rewriting, summarizing, or adapting a story for different channels. NewsFlow starts from a different question:

How can AI support the parts of journalism that happen before and after the article itself?

NewsFlow is built around the idea that responsible editorial work depends on more than writing speed. It depends on structured evidence, reviewable judgment, role-based handoff, explicit approval, risk awareness, and a visible correction loop. The goal is not to replace editorial decision-making, but to make the surrounding workflow easier to organize, inspect, and improve.

## What is included

This release includes:

- a FastAPI backend with workflow-oriented API modules
- a React + TypeScript frontend for dashboard, event, Story Packet, review, and sign-off flows
- core objects such as `EventCase`, `StoryPacket`, `ClaimCard`, `EvidencePack`, `ApprovalTask`, `DecisionLog`, and `CorrectionTicket`
- agent-oriented modules across intake, cognition, governance, production, orchestration, and post-publication monitoring
- environment variable examples for self-hosting
- open-source documentation for contribution, security, setup, maintenance, and release management
- GitHub issue templates, pull request template, CI workflow, Dependabot configuration, and CODEOWNERS

## What NewsFlow is designed to explore

NewsFlow is not only an AI writing interface. It explores AI-assisted workflow design for high-responsibility editorial environments.

The project focuses on:

- event-centered newsroom coordination
- evidence and claim organization before drafting
- human-in-the-loop approval checkpoints
- traceable decision logs and override reasons
- risk review before publication
- correction tickets and post-publication follow-up
- practical boundaries between AI assistance and human accountability

## Current status

This release should be understood as a high-fidelity prototype.

It is suitable for:

- self-hosted exploration
- classroom or research demonstrations
- product thinking around newsroom workflow systems
- secondary development by teams interested in editorial tooling
- experiments around responsible human-AI collaboration

It is not yet positioned as a production-ready newsroom platform.

## Self-hosting

Start with:

```text
docs/SELF_HOSTING.md
```

Recommended local versions:

- Python `3.12` or `3.13`
- Node.js `20.19+`
- Docker / Docker Compose for local infrastructure

## Known limitations

The current release still has important boundaries:

- permissions and organization-level governance can be more granular
- evidence anchors and citation mapping need deeper implementation
- long-term memory and source-protection governance need stronger controls
- deployment and operations guidance can be expanded
- some advanced agent behavior may require configured LLM credentials and local services

## Security and privacy note

Do not use public demo deployments for real newsroom source-protection data, unpublished reporting notes, real personal contact information, or internal approval history.

If you discover a security issue, please follow `SECURITY.md` instead of opening a public issue.

## Repository setup after release

Recommended next steps for maintainers:

- fill in the repository About section using `docs/GITHUB_PAGE_SETUP.md`
- upload `image/newsflow-social-preview.svg` as the GitHub social preview image
- enable branch protection for `main`
- enable Dependabot security alerts
- keep release notes and setup docs aligned with future changes

## Closing note

NewsFlow is an attempt to treat AI in journalism less as a shortcut for producing text and more as an infrastructure layer for organizing judgment, evidence, accountability, and collaboration.

That is the direction this first public release opens up.
