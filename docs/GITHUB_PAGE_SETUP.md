# GitHub Page Setup Copy

Use this file when filling in the public GitHub repository page for NewsFlow.

## Repository About

### Description

```text
An AI-assisted newsroom workflow system for event tracking, evidence organization, approval chains, correction handling, and post-publication monitoring.
```

### Website

If you have a public demo deployment, add it here. If not, leave this field empty for now.

```text

```

### Topics

```text
ai-agents
newsroom
journalism
workflow
human-in-the-loop
fastapi
react
typescript
editorial-workflow
approval-workflow
fact-checking
```

### Include in the repository About panel

Enable these if available:

- Releases
- Packages, only if you later publish Docker images or packages

## Social Preview

Upload this file in GitHub repository settings:

```text
image/newsflow-social-preview.svg
```

Path in GitHub:

```text
Settings -> General -> Social preview -> Edit -> Upload an image
```

## First Release

### Tag

```text
v0.1.0
```

### Release title

```text
NewsFlow OSS v0.1.0 — Initial public release
```

### Release body

Use the content from:

```text
docs/RELEASE_v0.1.0.md
```

## Suggested pinned repository note

```text
NewsFlow explores how AI can support responsible newsroom workflows beyond text generation: lead intake, evidence organization, claim review, approval traceability, correction handling, and post-publication monitoring.
```

## Branch protection settings

Recommended settings for `main`:

- require a pull request before merging
- require status checks to pass before merging
- select the `CI` workflow once it has run successfully
- require conversation resolution before merging
- do not allow force pushes
- do not allow deletions

Path in GitHub:

```text
Settings -> Branches -> Branch protection rules -> Add rule
```

Branch name pattern:

```text
main
```

## Security settings

Recommended settings:

- enable private vulnerability reporting if available
- keep Dependabot alerts enabled
- keep Dependabot security updates enabled

Path in GitHub:

```text
Settings -> Code security and analysis
```

## Final public launch checklist

- About description added
- Topics added
- Social preview uploaded
- `v0.1.0` tag exists
- first Release published
- CI badge visible in README
- README screenshots display correctly
- no private academic submission materials are present
- no real API keys, database URLs, or production secrets are present
