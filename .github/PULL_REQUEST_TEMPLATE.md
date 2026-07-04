# Pull Request

## Summary

<!-- What changed, and why? Keep this short and concrete. -->

## Scope

<!-- Which area is affected? adapter / taxonomy / report / profile contract / docs / packaging / tests -->

## Validation

<!-- List the commands you ran and their results. -->

- [ ] `uv run ruff check .`
- [ ] `uv run pyright`
- [ ] `uv run pytest`
- [ ] `uv build` if package metadata or README changed
- [ ] `bash scripts/run_e2e.sh /tmp/vibecoding_observer_e2e` if adapters, reports, profile output, or CLI behavior changed

## Privacy and Safety

- [ ] I did not commit `report.html`, `report.md`, `.analysis-profile.json`, or generated local reports.
- [ ] I did not paste private session logs, secrets, full local paths, or private project code.
- [ ] I did not add telemetry, uploads, runtime LLM calls, ranking, or heavy runtime dependencies.

## Contract Checks

- [ ] If `.analysis-profile.json` changed, I updated `docs/PROFILE_CONTRACT.md` and related tests.
- [ ] If diagnostic labels changed, I added positive and negative tests.
- [ ] If user-facing report text changed, I checked that internal signal codes remain traceable but not exposed as primary user copy.
