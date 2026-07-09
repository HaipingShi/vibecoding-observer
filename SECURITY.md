# Security Policy

VibeCoding Observer is a local-first diagnostic tool. Its security model is
based on reading local AI coding session history, producing local reports, and
not uploading diagnostic data by default.

## Supported Versions

The project is currently pre-alpha. Security fixes target the latest `main`
branch and the latest released `0.x` version when a release exists.

| Version | Supported |
|---|---|
| `0.x` | Best effort |

## Data Access Model

By default, the CLI may read:

- Claude Code sessions under `~/.claude/projects/`
- Codex sessions under `~/.codex/sessions/`
- Codex archived sessions under `~/.codex/archived_sessions/`
- Git metadata for the representative project when available

You can override session locations with:

```bash
vibecoding-observer --current-project --claude-dir /custom/claude --codex-dir /custom/codex --output ./my-report
```

Use `--all-history` only when you intentionally want to analyze every
discovered Claude Code / Codex session on the machine.

The tool writes:

- `report.html`
- `report.md`
- `.analysis-profile.json`
- `share-card.svg` when explicitly requested with `--export-share-card` or
  `--share-card-svg`

These outputs may include private interaction fragments. Treat them as local
artifacts unless you intentionally share them.

## Network Model

The diagnostic pipeline does not require network access and does not upload
session logs by default. The project does not call an LLM inside the pipeline.

Network access may appear only in user-driven development operations outside
the runtime diagnostic path, such as installing packages, cloning the
repository, checking links, or publishing releases.

## In Scope

Please report:

- Accidental network transmission of local session content.
- Leaks of unredacted private paths, secrets, tokens, emails, or phone numbers
  in generated public-facing artifacts.
- Unsafe parsing behavior that can execute untrusted session content.
- Vulnerabilities in the CLI that overwrite unexpected files outside the
  requested output directory.
- Packaging mistakes that include private generated reports.

## Out of Scope

The following are usually out of scope:

- False positives or false negatives in diagnostic labels unless they leak
  sensitive information.
- Private reports that a user explicitly shares or commits.
- Security issues in Claude Code, Codex, Git, Python, uv, or GitHub Actions.
- Network calls made by development tools outside the runtime diagnostic path.

## Reporting a Vulnerability

Use GitHub Issues:

https://github.com/HaipingShi/vibecoding-observer/issues

If the report contains sensitive details, open a minimal issue requesting a
private maintainer contact path. Do not paste secrets, private logs, or full
session files into a public issue.

Please include:

- A short impact summary.
- A minimal reproduction if possible.
- Affected version or commit.
- Whether private data can leave the local machine.
- Whether generated artifacts are affected.

Maintainers will acknowledge the report as soon as practical and coordinate a
fix or mitigation before public disclosure when needed.
