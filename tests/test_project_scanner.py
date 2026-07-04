"""Tests for ProjectScanner (the "望" dimension).

Creates synthetic project structures in tmp_path to verify classification,
constraint detection, StraTA completeness, language detection, test ratio.
"""

from __future__ import annotations

from pathlib import Path

from observer.project_scanner import scan_project


def _make_project(tmp_path: Path, name: str = "test-proj") -> Path:
    """Create a project root directory."""
    p = tmp_path / name
    p.mkdir()
    return p


class TestProjectType:
    def test_doc_vault(self, tmp_path: Path) -> None:
        """>70% markdown, shallow → doc-vault."""
        p = _make_project(tmp_path)
        for i in range(10):
            (p / f"note{i}.md").write_text(f"# Note {i}")
        (p / "config.json").write_text("{}")
        profile = scan_project(p)
        assert profile.project_type == "doc-vault"

    def test_complex_app(self, tmp_path: Path) -> None:
        """Deep tree, many files → complex-app."""
        p = _make_project(tmp_path)
        for module in ("auth", "api", "db", "utils", "models"):
            mod_dir = p / "src" / module
            mod_dir.mkdir(parents=True)
            for i in range(25):
                (mod_dir / f"file{i}.py").write_text("# code")
        profile = scan_project(p)
        assert profile.project_type == "complex-app"

    def test_scaffold(self, tmp_path: Path) -> None:
        """Few files, shallow → scaffold."""
        p = _make_project(tmp_path)
        (p / "main.py").write_text("print('hello')")
        (p / "README.md").write_text("# scaffold")
        (p / "requirements.txt").write_text("flask")
        profile = scan_project(p)
        assert profile.project_type in ("scaffold", "library")

    def test_library(self, tmp_path: Path) -> None:
        """Has manifest + src/ → library."""
        p = _make_project(tmp_path)
        (p / "pyproject.toml").write_text("[project]\nname='lib'")
        src = p / "src" / "lib"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "core.py").write_text("# code")
        tests = p / "tests"
        tests.mkdir()
        (tests / "test_core.py").write_text("# test")
        profile = scan_project(p)
        assert profile.project_type == "library"

    def test_empty_dir(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path, "empty")
        profile = scan_project(p)
        assert profile.project_type == "unknown"
        assert profile.total_files == 0


class TestConstraintDetection:
    def test_claude_md_detected(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        (p / "CLAUDE.md").write_text("# Agent instructions")
        profile = scan_project(p)
        assert profile.has_ai_constraint
        assert "CLAUDE.md" in profile.constraint_files

    def test_agents_md_detected(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        (p / "AGENTS.md").write_text("# Agent instructions")
        profile = scan_project(p)
        assert profile.has_ai_constraint

    def test_no_constraint(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        profile = scan_project(p)
        assert not profile.has_ai_constraint
        assert profile.constraint_files == []


class TestStrataCompleteness:
    def test_full_strata(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        docs = p / "docs"
        docs.mkdir()
        for doc in ("STRATEGY.md", "TASKS.md", "HANDOFF.md", "LESSONS.md", "HARNESS_SPEC.md"):
            (docs / doc).write_text(f"# {doc}")
        profile = scan_project(p)
        assert profile.strata_completeness == 1.0

    def test_partial_strata(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        docs = p / "docs"
        docs.mkdir()
        (docs / "STRATEGY.md").write_text("# strategy")
        (docs / "TASKS.md").write_text("# tasks")
        profile = scan_project(p)
        assert 0.3 <= profile.strata_completeness <= 0.5  # 2/5

    def test_no_strata(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        profile = scan_project(p)
        assert profile.strata_completeness == 0.0


class TestLanguageAndTestRatio:
    def test_primary_language_python(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        for i in range(10):
            (p / f"mod{i}.py").write_text("# code")
        (p / "readme.md").write_text("# readme")
        profile = scan_project(p)
        assert profile.primary_language == "python"

    def test_primary_language_typescript(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        for i in range(10):
            (p / f"mod{i}.ts").write_text("// code")
        profile = scan_project(p)
        assert profile.primary_language == "typescript"

    def test_test_ratio(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        for i in range(8):
            (p / f"mod{i}.py").write_text("# code")
        for i in range(2):
            (p / f"test_mod{i}.py").write_text("# test")
        profile = scan_project(p)
        assert profile.test_file_ratio == 0.2

    def test_no_tests(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        for i in range(5):
            (p / f"mod{i}.py").write_text("# code")
        profile = scan_project(p)
        assert profile.test_file_ratio == 0.0


class TestFileTreeMetrics:
    def test_depth_and_breadth(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "file1.py").write_text("")
        (p / "file2.py").write_text("")
        deep = p / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("")
        profile = scan_project(p)
        assert profile.file_tree_depth >= 4
        assert profile.file_tree_breadth >= 3  # file1, file2, a/ (non-hidden)

    def test_skip_dirs_excluded(self, tmp_path: Path) -> None:
        p = _make_project(tmp_path)
        (p / "main.py").write_text("# code")
        # Create noise dirs with files — should be excluded.
        (p / ".git").mkdir()
        (p / ".git" / "config").write_text("git config")
        (p / "node_modules").mkdir()
        (p / "node_modules" / "lib.js").write_text("// lib")
        (p / "__pycache__").mkdir()
        (p / "__pycache__" / "main.cpython-311.pyc").write_text("")
        profile = scan_project(p)
        assert profile.total_files == 1  # only main.py


class TestConstraintMaturity:
    def test_high_maturity(self, tmp_path: Path) -> None:
        """Constraint + StraTA + tests → high maturity."""
        p = _make_project(tmp_path)
        (p / "CLAUDE.md").write_text("# agent")
        docs = p / "docs"
        docs.mkdir()
        for doc in ("STRATEGY.md", "TASKS.md", "HANDOFF.md", "LESSONS.md", "HARNESS_SPEC.md"):
            (docs / doc).write_text("")
        (p / "main.py").write_text("")
        (p / "test_main.py").write_text("")
        profile = scan_project(p)
        assert profile.constraint_maturity > 0.5

    def test_low_maturity(self, tmp_path: Path) -> None:
        """No constraint, no StraTA, no tests → low maturity."""
        p = _make_project(tmp_path)
        (p / "main.py").write_text("")
        profile = scan_project(p)
        assert profile.constraint_maturity < 0.2
