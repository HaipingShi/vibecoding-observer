"""Smoke tests — verify the package is importable and the basics hold.

These are intentionally minimal: T-001 only validates the skeleton.
Real component tests arrive with their respective tasks (T-002 onward).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import observer

ROOT = Path(__file__).resolve().parents[1]


def test_package_importable() -> None:
    """The package can be imported without side effects."""
    import observer as pkg  # noqa: F401 — explicit re-import for clarity


def test_version_string() -> None:
    """__version__ is a non-empty semver-style string."""
    assert isinstance(observer.__version__, str)
    parts = observer.__version__.split(".")
    assert len(parts) >= 2, f"expected semver, got {observer.__version__}"
    assert all(p.isdigit() or p[0].isalpha() for p in parts), (
        f"version parts should be numeric or pre-release, got {parts}"
    )


def test_all_exports_are_valid() -> None:
    """Every name in __all__ is an attribute of the package."""
    for name in observer.__all__:
        assert hasattr(observer, name), f"__all__ lists {name!r} but it is missing"


def test_distribution_exposes_only_canonical_cli() -> None:
    """The deprecated agentlens name must not be published as this CLI."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["scripts"] == {
        "vibecoding-observer": "observer.cli:main",
    }
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/observer",
    ]
