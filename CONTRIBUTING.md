# Contributing to VibeCoding Observer

Thanks for improving VibeCoding Observer. This project is a local-first Python
diagnostic tool for AI coding session history. Contributions are welcome when
they improve correctness, privacy, portability, documentation, or diagnostic
clarity.

## Scope

Good contribution areas:

- Improve Claude Code / Codex log parsing without loading large files into memory.
- Reduce false positives in the closed diagnostic label taxonomy.
- Add tests for edge cases in adapters, extraction rules, reports, or redaction.
- Improve user-facing report readability without exposing private data.
- Improve docs, examples, or installation instructions.

Not accepted in this project:

- Uploading user session logs to a remote service by default.
- Adding runtime LLM calls inside the diagnostic pipeline.
- Ranking developers, teams, or organizations.
- Heavy runtime dependencies for embeddings, vector search, or ML clustering.
- Telemetry or analytics that send local diagnostic data out of the machine.

## Development Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/HaipingShi/vibecoding-observer.git
cd vibecoding-observer
uv sync --extra dev
```

Run the standard checks:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

The package has no runtime dependencies. Dev dependencies are limited to
testing, linting, and type checking.

## Project Layout

```text
src/observer/       # canonical implementation package
src/agentlens/      # compatibility alias for older imports
tests/              # pytest suite
docs/               # public profile contract and consulting output examples
scripts/            # e2e helper
```

New code should import `observer`. Keep `agentlens` compatibility working until
a future release explicitly removes it.

## Contribution Rules

Before opening a pull request:

1. Keep the diff focused. Do not combine taxonomy, report UI, docs, and package
   metadata in one PR unless they are inseparable.
2. Add or update tests for behavior changes.
3. Run `uv run ruff check .`, `uv run pyright`, and `uv run pytest`.
4. Do not commit generated local diagnostic outputs such as `report.html`,
   `report.md`, `.analysis-profile.json`, or `reports/*.html`.
5. If you tune keyword rules, include at least one negative test for likely
   false positives.
6. If you change `.analysis-profile.json`, update
   `docs/PROFILE_CONTRACT.md` and related tests.

## Adding an Agent Adapter

1. Add the implementation under `src/observer/adapters/<agent>.py`.
2. Subclass `Adapter` from `src/observer/adapters/base.py`.
3. Implement lazy parsing: `parse(jsonl_path) -> Iterator[IREvent]`.
4. Add fixture coverage under `tests/fixtures/`.
5. Add tests under `tests/adapters/test_<agent>.py`.
6. Register discovery and selection in `src/observer/orchestrator.py`.

Adapters must emit unified `IREvent` records. Upper layers should not read raw
source-specific log structures.

## Extending Diagnostic Labels

The extractor uses closed diagnostic labels. A label is useful only if it is
auditable and stable across sessions.

When adding or changing a label:

1. Update `src/observer/taxonomy.py`.
2. Add extraction rules in `src/observer/extractor.py`.
3. Add positive and negative tests.
4. Update report/profile rendering if the label should be user-visible.
5. Check that README/docs still describe the dimensions accurately.

Avoid broad regexes that match line numbers, timestamps, file paths, or tool
output. False positives are worse than lower recall for this project.

## Running E2E

The e2e script reads local Claude Code / Codex history from the current
machine. Run it only when that is acceptable for your environment:

```bash
bash scripts/run_e2e.sh /tmp/vibecoding_observer_e2e
```

The output directory may contain private session fragments. Do not commit it.

## Reporting Issues

Use GitHub Issues:
https://github.com/HaipingShi/vibecoding-observer/issues

Helpful issue reports include:

- OS and Python version.
- Agent source: Claude Code, Codex, or both.
- Command used.
- Error output or a redacted excerpt.
- Whether the issue is parsing, labels, report rendering, or installation.

Do not paste private session logs unless you have redacted them.

## License

By contributing, you agree that your contribution is licensed under the MIT
License.
