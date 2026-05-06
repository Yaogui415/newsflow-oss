# Repository Maintenance Checklist

Use this checklist after the initial open-source launch to keep the repository in a healthy state.

## GitHub repository setup

- fill in the repository About description using `docs/GITHUB_ABOUT.md`
- add the recommended Topics
- upload `image/newsflow-social-preview.svg` as the social preview image
- publish a first Release using `docs/RELEASE_v0.1.0.md`

## Branch and review hygiene

- enable branch protection for `main`
- require pull requests for non-trivial changes
- require status checks from GitHub Actions once CI is green
- keep direct pushes to `main` limited to maintenance or emergency changes

## Documentation upkeep

- keep `README.md` aligned with the real codebase
- update `docs/SELF_HOSTING.md` whenever setup steps change
- update `docs/RELEASE_v0.1.0.md` pattern for future releases
- remove or rewrite stale screenshots when the UI changes significantly

## Security and privacy

- never commit real API keys or live database URLs
- never add teacher-facing or private course submission materials into this public repository
- review deployment manifests before every public push
- keep `SECURITY.md` current if your reporting process changes

## Issue and community management

- label incoming issues quickly
- close incomplete reports politely if they cannot be reproduced
- move security reports out of public issues
- mark beginner-friendly work with `good first issue`

## Release cadence

For each meaningful release, try to update:

- release notes
- README screenshots if needed
- roadmap status
- self-hosting instructions if deployment changed
