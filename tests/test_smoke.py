"""Smoke tests — verify the package is importable and the basics hold.

These are intentionally minimal: T-001 only validates the skeleton.
Real component tests arrive with their respective tasks (T-002 onward).
"""

from __future__ import annotations

import observer


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


def test_agentlens_compat_alias() -> None:
    """The old import package remains available as a compatibility alias."""
    import agentlens
    import agentlens.orchestrator
    import observer.orchestrator

    assert agentlens.__version__ == observer.__version__
    assert agentlens.IREvent is observer.IREvent
    assert agentlens.orchestrator is observer.orchestrator
