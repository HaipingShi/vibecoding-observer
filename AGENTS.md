# VibeCoding Observer Agent Guide

This repository is `vibecoding-observer`. Do not use the old `agentlens` name
as a package, CLI, import path, repository source, or PyPI fact source.

## Canonical Surface

- Distribution name: `vibecoding-observer`
- CLI: `vibecoding-observer`
- Python package: `observer`
- Repository: `https://github.com/HaipingShi/vibecoding-observer`

## Work Rules

- Read `README.md`, `pyproject.toml`, `SECURITY.md`, `CONTRIBUTING.md`, and
  `docs/RELEASE_CHECKLIST.md` before changing packaging, CLI behavior, report
  outputs, privacy boundaries, or release metadata.
- Keep diffs small. Do not refactor the diagnostic model while changing docs,
  packaging, or release governance.
- Do not add runtime dependencies unless the task explicitly requires it.
- Do not modify `uv.lock`, package metadata, or CI configuration unless the
  task is about dependencies, packaging, CI, or release.
- Do not reintroduce `src/agentlens`, `agentlens` console scripts, or docs that
  tell users to install PyPI `agentlens`.
- Do not commit local reports, private session logs, `.analysis-profile.json`,
  CodeRail scaffolding, `.agent/`, `.coderail/`, or other run state.

## Privacy Boundary

The diagnostic pipeline is local-first. It may read local Claude Code and Codex
session history and may write private fragments into generated reports.

- Never upload or paste private session logs.
- Do not add telemetry, runtime LLM calls, ranking, or network upload behavior.
- Treat `report.html`, `report.md`, and `.analysis-profile.json` as local
  artifacts unless a user explicitly chooses to share them.

## Verification

Use the smallest relevant set, and broaden when touching shared behavior:

```bash
uv run ruff check .
uv run pyright
uv run pytest
uv build --out-dir /tmp/vibecoding_observer_dist
```

When changing adapters, report/profile output, discovery, or CLI behavior, also
run a fixture or local-scope report generation. Do not print sensitive report
fragments from real user logs.

Before release, follow `docs/RELEASE_CHECKLIST.md`.
