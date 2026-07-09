# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-09

### Changed

- README installation instructions now use the official PyPI package
  `vibecoding-observer` as the primary install path.
- Release documentation keeps the explicit warning that the PyPI package named
  `agentlens` is not this project.

## [0.2.0] - 2026-07-09

### Added

- Developer-language adaptive reports with `--report-language auto|zh|en`.
- Screenshot-friendly positive share cards in HTML reports.
- Standalone self-contained SVG share-card export via `--export-share-card` and
  `--share-card-svg`.
- Preset playful title pools plus an `llm_title_prompt` field for downstream
  user-owned agents to rewrite share-card titles without Observer calling an LLM.
- Project profile support for custom governance dialects through
  `observer.yaml` fixtures.
- GitHub Pages demo workflow with a Pages-enabled preflight check.
- Single-file bilingual README structure for public repository presentation.
- Repository governance files: `CODE_OF_CONDUCT.md`, `SECURITY.md`, and this changelog.
- Explicit scan scope flags: `--current-project`, `--project /path/to/project`,
  and `--all-history`.
- Project-level `AGENTS.md` and `docs/RELEASE_CHECKLIST.md` to document agent
  work rules, privacy boundaries, release checks, and scaffold exclusions.

### Changed

- Codex engineering-loop recognition now treats patches, shell verification,
  commits, handoff updates, and docs/design artifacts as distinct closure
  evidence instead of collapsing them into `goal_only`.
- Episode loop quality now separates `goal_only`, `design_closed`,
  `implementation_closed`, `verification_only`, and `blocked_or_handoff`.
- Activation efficacy counts design/documentation closures, reducing false
  negatives for architecture, ADR, and governance-heavy tasks.
- Reports now include diagnostic confidence and unrecognized-governance risk
  language to avoid overstating missing closure when the active workflow dialect
  is unknown.
- README now includes visual badges, architecture imagery, demo report guidance,
  and share-card export examples.
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
[0.2.1]: https://github.com/HaipingShi/vibecoding-observer/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/HaipingShi/vibecoding-observer/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HaipingShi/vibecoding-observer
