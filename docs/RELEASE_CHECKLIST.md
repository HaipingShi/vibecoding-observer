# Release Checklist

Use this checklist before publishing `vibecoding-observer`.

## 1. Version And Metadata

- [ ] Decide the next version using semantic versioning.
- [ ] Update `pyproject.toml`.
- [ ] Update `src/observer/__init__.py`.
- [ ] Update README badges and visible version text.
- [ ] Update `CHANGELOG.md` with migration notes and verification commands.
- [ ] Confirm the canonical surfaces are still:
  - distribution: `vibecoding-observer`
  - CLI: `vibecoding-observer`
  - import package: `observer`

## 2. Installation And Naming

- [ ] Confirm README installation instructions match the real release channel.
- [ ] Confirm no docs point to `geesh/agentlens`.
- [ ] Confirm no docs tell users to install PyPI `agentlens`.
- [ ] Confirm no `agentlens` console script is published.
- [ ] Confirm wheel and sdist do not contain `src/agentlens` or `agentlens/`.

## 3. Privacy And Asset Boundary

- [ ] Do not publish local Claude/Codex logs.
- [ ] Do not publish generated `report.html`, `report.md`,
  `.analysis-profile.json`, or `share-card.svg` from real local logs.
- [ ] Do not publish `.agent/`, `.coderail/`, `coderail-output/`,
  `project-template/`, or other governance scaffolding/run state.
- [ ] Do not publish `.venv/`, `.ruff_cache/`, `.pytest_cache/`, build caches,
  or local scratch output.
- [ ] Confirm runtime behavior remains local-first: no telemetry, no upload, no
  runtime LLM calls, no ranking.

## 4. Verification

```bash
uv sync --extra dev
uv run ruff check .
uv run pyright
uv run pytest
uv build --out-dir /tmp/vibecoding_observer_dist
```

If adapters, discovery, CLI, reports, profile output, or privacy behavior
changed, also run:

```bash
bash scripts/run_e2e.sh /tmp/vibecoding_observer_e2e
```

When real local logs are used for e2e, record only summary counts in public
release notes. Do not paste sensitive report fragments.

## 5. Build Artifact Inspection

```bash
python - <<'PY'
import pathlib
import tarfile
import zipfile

dist = pathlib.Path("/tmp/vibecoding_observer_dist")
for wheel in dist.glob("*.whl"):
    names = zipfile.ZipFile(wheel).namelist()
    assert not any(name.startswith("agentlens/") for name in names)
    assert not any(".agent/" in name or ".coderail/" in name for name in names)
    print(wheel.name, "ok")

for sdist in dist.glob("*.tar.gz"):
    names = tarfile.open(sdist).getnames()
    assert not any("/src/agentlens/" in name for name in names)
    assert not any("/.agent/" in name or "/.coderail/" in name for name in names)
    assert not any("/project-template/" in name for name in names)
    print(sdist.name, "ok")
PY
```

## 6. Tag And GitHub Release

- [ ] Create an annotated tag after checks pass.
- [ ] Release notes include highlights, compatibility notes, install command,
  and verification summary.
- [ ] GitHub About, topics, homepage, Issues, and security reporting surfaces
  are intentional.
