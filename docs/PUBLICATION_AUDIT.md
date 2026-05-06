# Public Release Audit

This document records the final public-release checks performed before publishing NewsFlow OSS.

## Repository scope

The public repository is a clean repository without the private development history from the original project.

Excluded from the public release:

- private academic submission materials
- personal workspace files
- local environment files
- generated build outputs
- historical commits from the original private working repository

## Sensitive information scan

A text scan was performed across the public repository while excluding generated and dependency directories such as `.git`, `node_modules`, `dist`, `build`, virtual environments, and cache folders.

The scan checked for:

- private academic material directory names and related terms
- known production deployment domains from the private deployment
- OpenAI-style API key patterns
- GitHub token patterns
- database URLs containing inline passwords

Result:

```text
No sensitive/private release blockers found in scan scope.
```

## Sanitized configuration

The following public-release changes were applied:

- frontend API base URL is configured through environment variables
- login fallback and backend health check URLs are configured through environment variables
- Vercel and Netlify frontend configs no longer point to a private production backend
- backend Render config uses synced/generated environment variables instead of hardcoded credentials
- backend CORS defaults no longer include the private frontend deployment URL

## Validation

Validation performed during repository preparation:

- frontend production build passed with `npm run build`
- backend health test passed in an isolated Python `3.13` environment
- Python `3.14` was identified as not recommended because `orjson` may fail to build in some environments

## Remaining GitHub UI tasks

These require manual GitHub web UI setup unless GitHub CLI or API credentials are available:

- fill in the repository About description
- add Topics
- upload the social preview image
- publish the first GitHub Release
- enable branch protection for `main`
