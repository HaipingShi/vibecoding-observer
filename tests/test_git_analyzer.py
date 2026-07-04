"""Tests for GitAnalyzer (the "切" dimension).

Uses real git repos in tmp_path for end-to-end validation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from observer.git_analyzer import analyze_git


def _git_init(repo: Path) -> None:
    """Initialize a git repo with safe defaults."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)


def _git_commit(repo: Path, files: dict[str, str]) -> None:
    """Stage files and commit."""
    for path, content in files.items():
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "test commit"], cwd=repo, check=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "test-repo"
    repo.mkdir()
    _git_init(repo)
    return repo


class TestBasicMetrics:
    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        p = tmp_path / "not-a-repo"
        p.mkdir()
        (p / "file.txt").write_text("hello")
        metrics = analyze_git(p)
        assert not metrics.is_repo
        assert metrics.total_commits == 0

    def test_single_commit(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"main.py": "print('hello')\n"})
        metrics = analyze_git(git_repo)
        assert metrics.is_repo
        assert metrics.total_commits == 1
        assert metrics.total_lines_added > 0

    def test_multiple_commits(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"a.py": "a = 1\n"})
        _git_commit(git_repo, {"b.py": "b = 2\n"})
        _git_commit(git_repo, {"c.py": "c = 3\n"})
        metrics = analyze_git(git_repo)
        assert metrics.total_commits == 3
        assert metrics.total_lines_added >= 3

    def test_deletion_tracking(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"file.py": "line1\nline2\nline3\n"})
        _git_commit(git_repo, {"file.py": "line1\n"})  # delete 2 lines
        metrics = analyze_git(git_repo)
        assert metrics.total_lines_deleted > 0
        assert metrics.deletion_ratio > 0


class TestEfficiencyMetrics:
    def test_commit_per_interaction(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"main.py": "print('hello')\n"})
        _git_commit(git_repo, {"util.py": "x = 1\n"})
        metrics = analyze_git(git_repo, interaction_count=100)
        assert metrics.commit_per_interaction == 0.02  # 2/100

    def test_zero_interactions(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"main.py": "x\n"})
        metrics = analyze_git(git_repo)
        assert metrics.commit_per_interaction == 0.0

    def test_avg_diff_size(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"a.py": "line1\nline2\nline3\n"})  # 3 added
        metrics = analyze_git(git_repo)
        assert metrics.avg_diff_size >= 3.0

    def test_net_lines(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"a.py": "line1\nline2\n"})
        metrics = analyze_git(git_repo)
        assert metrics.net_lines >= 2


class TestTestRatio:
    def test_test_lines_detected(self, git_repo: Path) -> None:
        _git_commit(git_repo, {
            "main.py": "def add(a, b):\n    return a + b\n",
            "test_main.py": "def test_add():\n    assert add(1,2) == 3\n",
        })
        metrics = analyze_git(git_repo)
        assert metrics.test_lines_added > 0
        assert metrics.test_line_ratio > 0

    def test_no_tests(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"main.py": "x = 1\n"})
        metrics = analyze_git(git_repo)
        assert metrics.test_lines_added == 0
        assert metrics.test_line_ratio == 0.0


class TestBranchAnalysis:
    def test_branches_counted(self, git_repo: Path) -> None:
        _git_commit(git_repo, {"main.py": "x\n"})
        subprocess.run(["git", "branch", "feature-a"], cwd=git_repo, check=True)
        subprocess.run(["git", "branch", "feature-b"], cwd=git_repo, check=True)
        metrics = analyze_git(git_repo)
        assert metrics.active_branches >= 3  # main + 2 features (or master)


class TestEmptyMetrics:
    def test_empty_repo(self, git_repo: Path) -> None:
        """No commits yet."""
        metrics = analyze_git(git_repo)
        assert metrics.is_repo
        assert metrics.total_commits == 0
        assert metrics.total_lines_added == 0
