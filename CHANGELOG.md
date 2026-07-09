# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Single-file bilingual README structure for public repository presentation.
- Repository governance files: `CODE_OF_CONDUCT.md`, `SECURITY.md`, and this changelog.
- Explicit scan scope flags: `--current-project`, `--project /path/to/project`,
  and `--all-history`.
- Project-level `AGENTS.md` and `docs/RELEASE_CHECKLIST.md` to document agent
  work rules, privacy boundaries, release checks, and scaffold exclusions.

### Changed

- Canonical Python import package is `observer`; the deprecated `agentlens`
  package and CLI alias are no longer published by this project.
- Open-source package metadata now includes author, project-specific keywords,
  and GitHub Issues URL.
- Repository text files are normalized through `.gitattributes`.
- Non-interactive agent runs now default to the current project instead of all
  discovered AI coding history.
- Installation docs now point to the GitHub/source install path until a
  `vibecoding-observer` PyPI release exists, and explicitly warn that the PyPI
  `agentlens` package is not this project.
- `.gitignore` and the PR template now explicitly exclude generated reports,
  local run state, and CodeRail-style scaffold/intermediate artifacts from
  publication.

## [0.1.0] - 2026-07-03

### Added

- Local-first diagnostic pipeline for Claude Code and Codex session history.
- Unified IR, source adapters, federator, closed-label extractor, aggregator,
  anomaly detection, episode analysis, and diagnostic engine.
- User-facing outputs: `report.html`, `report.md`, and `.analysis-profile.json`.
- 28 labels across degradation, activation, waste, and efficiency dimensions.
- Dynamic `consulting_routes` and route-specific `consulting_output` contracts.
- GitHub README hero image and WeChat article GIF asset.
- Public publishing helper script for clean-tree release publishing.

[Unreleased]: https://github.com/HaipingShi/vibecoding-observer
[0.1.0]: https://github.com/HaipingShi/vibecoding-observer
