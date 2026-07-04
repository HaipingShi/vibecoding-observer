"""ProjectScanner — the "望" (observe) dimension of the diagnostic framework.

Scans a project's directory structure to produce a :class:`ProjectProfile`:
project type, file tree shape, AI coding constraint maturity, StraTA document
completeness, primary language, and test file ratio.

This is the structural context that conversation-only analysis misses.
Knowing whether a project has CLAUDE.md, whether it's a doc vault vs a complex
app, and whether StraTA discipline exists — these transform the interaction
diagnosis from "you have N degen-wrong-layer events" to "you lack constraint
files, which is the root cause of repeated cold-start layer confusion."

Zero external dependencies. Pure stdlib (os/pathlib/collections).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ProjectProfile", "ProjectScanner", "scan_project"]


# --------------------------------------------------------------------------- #
# Output type
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    """Structural profile of a project (the "望" dimension)."""

    project_type: str
    """Classified type: doc-vault / scaffold / complex-app / library / data-pipeline / unknown."""

    file_tree_depth: int
    """Maximum directory nesting depth."""

    file_tree_breadth: int
    """Number of direct children in the root directory."""

    total_files: int
    """Total files scanned (excluding .git, node_modules, __pycache__, .venv)."""

    has_ai_constraint: bool
    """Whether any AI coding constraint file exists."""

    constraint_files: list[str]
    """Which constraint files were found."""

    strata_completeness: float
    """0.0–1.0, fraction of StraTA docs present (STRATEGY/TASKS/HANDOFF/LESSONS/HARNESS)."""

    primary_language: str
    """Detected primary language by file extension frequency."""

    test_file_ratio: float
    """Fraction of files that appear to be tests."""

    @property
    def constraint_maturity(self) -> float:
        """Overall constraint maturity score (0.0–1.0)."""
        score = 0.3 * (1.0 if self.has_ai_constraint else 0.0)
        score += 0.4 * self.strata_completeness
        score += 0.3 * (min(1.0, self.test_file_ratio * 10) if self.test_file_ratio > 0 else 0.0)
        return round(score, 2)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", ".pyright", "dist", "build", ".eggs",
    ".idea", ".vscode", ".DS_Store", "target", "__pypackages__",
})

_AI_CONSTRAINT_FILES: tuple[str, ...] = (
    "CLAUDE.md", "AGENTS.md", ".agent", ".cursorrules", "cursor.rules",
    ".github/copilot-instructions.md", "copilot-instructions.md",
)

_STRATA_DOCS: tuple[str, ...] = (
    "STRATEGY.md", "TASKS.md", "HANDOFF.md", "LESSONS.md", "HARNESS_SPEC.md",
)

_LANG_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".md": "markdown",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".rb": "ruby",
    ".sh": "shell",
}

_TEST_PATTERNS: tuple[str, ...] = (
    "test_", "_test", ".test.", ".spec.", "tests/", "/test/",
)


# --------------------------------------------------------------------------- #
# Scanner
# --------------------------------------------------------------------------- #


class ProjectScanner:
    """Scan a project directory to produce a ProjectProfile.

    Args:
        max_files: Safety cap to avoid scanning huge repos (default 50000).
    """

    def __init__(self, max_files: int = 50000) -> None:
        self.max_files = max_files

    def scan(self, project_path: str | Path) -> ProjectProfile:
        """Scan a project directory and return its structural profile.

        Args:
            project_path: Path to the project root.

        Returns:
            ProjectProfile with all fields populated.
        """
        root = Path(project_path)
        if not root.is_dir():
            return self._empty_profile()

        files: list[Path] = []
        max_depth = 0
        lang_counter: Counter[str] = Counter()
        test_count = 0

        for path in self._walk(root):
            rel = path.relative_to(root)
            depth = len(rel.parts) - 1
            if depth > max_depth:
                max_depth = depth

            files.append(path)
            ext = path.suffix.lower()
            if ext in _LANG_EXTENSIONS:
                lang_counter[_LANG_EXTENSIONS[ext]] += 1

            rel_str = str(rel).lower()
            if any(p in rel_str for p in _TEST_PATTERNS):
                test_count += 1

        total_files = len(files)
        breadth = len([p for p in root.iterdir() if not p.name.startswith(".")]) if root.is_dir() else 0

        # Constraint detection.
        constraint_found: list[str] = []
        for cf in _AI_CONSTRAINT_FILES:
            if (root / cf).exists():
                constraint_found.append(cf)
        has_constraint = len(constraint_found) > 0

        # StraTA completeness.
        strata_found = sum(1 for doc in _STRATA_DOCS if (root / "docs" / doc).exists() or (root / doc).exists())
        strata_score = strata_found / len(_STRATA_DOCS)

        # Primary language.
        primary = lang_counter.most_common(1)[0][0] if lang_counter else "unknown"

        # Test ratio.
        test_ratio = test_count / total_files if total_files > 0 else 0.0

        return ProjectProfile(
            project_type=self._classify_type(files, lang_counter, max_depth, root),
            file_tree_depth=max_depth,
            file_tree_breadth=breadth,
            total_files=total_files,
            has_ai_constraint=has_constraint,
            constraint_files=constraint_found,
            strata_completeness=round(strata_score, 2),
            primary_language=primary,
            test_file_ratio=round(test_ratio, 4),
        )

    # ----------------------------------------------------------------- #
    # Internal
    # ----------------------------------------------------------------- #
    def _walk(self, root: Path):
        """Yield files recursively, skipping noise directories."""
        count = 0
        for path in root.rglob("*"):
            if count >= self.max_files:
                break
            # Skip noise directories.
            parts = path.relative_to(root).parts
            if any(part in _SKIP_DIRS for part in parts):
                continue
            if path.is_file():
                count += 1
                yield path

    @staticmethod
    def _classify_type(
        files: list[Path],
        lang_counter: Counter[str],
        max_depth: int,
        root: Path | None = None,
    ) -> str:
        """Classify project type from structural signals."""
        total = len(files)
        if total == 0:
            return "unknown"

        md_count = lang_counter.get("markdown", 0)
        md_ratio = md_count / total if total > 0 else 0

        # Doc vault: mostly markdown, shallow tree.
        if md_ratio > 0.7 and max_depth <= 5:
            return "doc-vault"

        # Check for package manifests at root.
        has_manifest = False
        if root:
            for m in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod"):
                if (root / m).exists():
                    has_manifest = True
                    break

        # Complex app: multi-module structure, many files.
        if max_depth >= 2 and total > 100:
            return "complex-app"

        # Library: has manifest + structured depth.
        if has_manifest and max_depth >= 2:
            return "library"

        # Scaffold: few files, shallow.
        if total <= 30 and max_depth <= 3:
            return "scaffold"

        return "unknown"

    @staticmethod
    def _empty_profile() -> ProjectProfile:
        return ProjectProfile(
            project_type="unknown",
            file_tree_depth=0,
            file_tree_breadth=0,
            total_files=0,
            has_ai_constraint=False,
            constraint_files=[],
            strata_completeness=0.0,
            primary_language="unknown",
            test_file_ratio=0.0,
        )


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def scan_project(project_path: str | Path) -> ProjectProfile:
    """One-shot project scan without instantiating."""
    return ProjectScanner().scan(project_path)
