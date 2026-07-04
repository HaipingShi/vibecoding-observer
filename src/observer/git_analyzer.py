"""GitAnalyzer — the "切" (pulse) dimension of the diagnostic framework.

Extracts git metrics from a project to produce :class:`GitMetrics`:
commit count, lines added/deleted, commit-per-interaction ratio, average
diff size, deletion ratio, branch health, and test line ratio.

Combined with interaction count (from conversation analysis), this reveals
efficiency patterns:
  - High code + low interaction = strong long-range control (eff-high-leverage)
  - Low code + high interaction = idle spinning (eff-idle)

Uses ``git log --numstat`` for a single-pass extraction. Falls back
gracefully if the directory is not a git repo.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["GitAnalyzer", "GitMetrics", "analyze_git"]


@dataclass(frozen=True, slots=True)
class GitMetrics:
    """Git-derived metrics for a project (the "切" dimension)."""

    is_repo: bool
    total_commits: int
    total_lines_added: int
    total_lines_deleted: int
    avg_diff_size: float
    """Average lines changed (added+deleted) per commit."""

    deletion_ratio: float
    """deleted / (added+deleted) — high values indicate churn/reversal."""

    active_branches: int
    long_lived_branches: int
    """Branches not merged to HEAD with commits older than 7 days."""

    test_lines_added: int
    test_line_ratio: float
    """Fraction of added lines that are in test files."""

    interaction_count: int = 0
    """Set externally from conversation analysis; 0 if not provided."""

    @property
    def commit_per_interaction(self) -> float:
        """Commits per interaction event. Higher = more efficient output."""
        if self.interaction_count == 0:
            return 0.0
        return self.total_commits / self.interaction_count

    @property
    def net_lines(self) -> int:
        return self.total_lines_added - self.total_lines_deleted


class GitAnalyzer:
    """Analyze a git repository to produce GitMetrics.

    Args:
        long_lived_days: Threshold for "long-lived" branches (default 7).
    """

    def __init__(self, long_lived_days: int = 7) -> None:
        self.long_lived_days = long_lived_days

    def analyze(self, project_path: str | Path, interaction_count: int = 0) -> GitMetrics:
        """Analyze git history and return metrics.

        Args:
            project_path: Path to the project root (must be a git repo).
            interaction_count: Number of conversation events (from aggregator).

        Returns:
            GitMetrics. If not a git repo, returns empty metrics with is_repo=False.
        """
        root = Path(project_path)

        if not self._is_git_repo(root):
            return self._empty_metrics(interaction_count)

        log_output = self._git(
            root,
            [
                "log", "--numstat", "--format=@@%H|%ct",
                "--no-merges", "-n", "500",
            ],
        )

        commits = self._parse_log(log_output)

        total_commits = len(commits)
        total_added = sum(c["added"] for c in commits)
        total_deleted = sum(c["deleted"] for c in commits)
        test_added = sum(c["test_added"] for c in commits)

        avg_diff = (
            (total_added + total_deleted) / total_commits
            if total_commits > 0
            else 0.0
        )
        deletion_ratio = (
            total_deleted / (total_added + total_deleted)
            if (total_added + total_deleted) > 0
            else 0.0
        )
        test_ratio = (
            test_added / total_added if total_added > 0 else 0.0
        )

        # Branch analysis.
        branch_info = self._analyze_branches(root)

        return GitMetrics(
            is_repo=True,
            total_commits=total_commits,
            total_lines_added=total_added,
            total_lines_deleted=total_deleted,
            avg_diff_size=round(avg_diff, 1),
            deletion_ratio=round(deletion_ratio, 4),
            active_branches=branch_info["active"],
            long_lived_branches=branch_info["long_lived"],
            test_lines_added=test_added,
            test_line_ratio=round(test_ratio, 4),
            interaction_count=interaction_count,
        )

    # ----------------------------------------------------------------- #
    # Internal
    # ----------------------------------------------------------------- #
    @staticmethod
    def _is_git_repo(root: Path) -> bool:
        return (root / ".git").exists() or _run_git(root, ["rev-parse", "--is-inside-work-tree"]) is not None

    @staticmethod
    def _git(root: Path, args: list[str]) -> str:
        result = _run_git(root, args)
        return result if result is not None else ""

    @staticmethod
    def _parse_log(raw: str) -> list[dict]:
        """Parse git log --numstat --format=@@%H|%ct output.

        Format per commit:
            @@<hash>|<timestamp>
            <added>\t<deleted>\t<filepath>
            <added>\t<deleted>\t<filepath>
            (blank line)
        """
        commits: list[dict] = []
        current: dict | None = None

        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("@@"):
                if current is not None:
                    commits.append(current)
                parts = line[2:].split("|")
                current = {
                    "hash": parts[0] if len(parts) > 0 else "",
                    "timestamp": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                    "added": 0,
                    "deleted": 0,
                    "test_added": 0,
                }
            elif current is not None and "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 3:
                    added = int(parts[0]) if parts[0].isdigit() else 0
                    deleted = int(parts[1]) if parts[1].isdigit() else 0
                    filepath = parts[2]
                    current["added"] += added
                    current["deleted"] += deleted
                    fp_lower = filepath.lower()
                    if any(p in fp_lower for p in ("test_", "_test", ".test.", ".spec.", "/tests/", "/test/")):
                        current["test_added"] += added

        if current is not None:
            commits.append(current)

        return commits

    def _analyze_branches(self, root: Path) -> dict[str, int]:
        """Count active and long-lived branches."""
        output = self._git(root, [
            "for-each-ref", "--format=%(refname:short)|%(committerdate:unix)",
            "refs/heads/",
        ])
        if not output:
            return {"active": 0, "long_lived": 0}

        import time

        now = time.time()
        active = 0
        long_lived = 0
        for line in output.strip().split("\n"):
            parts = line.split("|")
            if len(parts) < 2:
                continue
            active += 1
            ts_str = parts[1].strip()
            if ts_str.isdigit():
                age_days = (now - int(ts_str)) / 86400
                if age_days > self.long_lived_days:
                    long_lived += 1

        return {"active": active, "long_lived": long_lived}

    @staticmethod
    def _empty_metrics(interaction_count: int = 0) -> GitMetrics:
        return GitMetrics(
            is_repo=False,
            total_commits=0,
            total_lines_added=0,
            total_lines_deleted=0,
            avg_diff_size=0.0,
            deletion_ratio=0.0,
            active_branches=0,
            long_lived_branches=0,
            test_lines_added=0,
            test_line_ratio=0.0,
            interaction_count=interaction_count,
        )


# --------------------------------------------------------------------------- #
# Convenience + helpers
# --------------------------------------------------------------------------- #


def analyze_git(project_path: str | Path, interaction_count: int = 0) -> GitMetrics:
    """One-shot git analysis without instantiating."""
    return GitAnalyzer().analyze(project_path, interaction_count)


def _run_git(root: Path, args: list[str]) -> str | None:
    """Run a git command, return stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return None
