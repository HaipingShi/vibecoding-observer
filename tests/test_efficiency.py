"""Tests for the efficiency classifier (code output vs interaction cost)."""

from __future__ import annotations

from observer.efficiency import EfficiencyProfile, classify_efficiency
from observer.git_analyzer import GitMetrics
from observer.project_scanner import ProjectProfile
from observer.taxonomy import Efficiency


def _git(
    added: int = 0,
    deleted: int = 0,
    interactions: int = 0,
) -> GitMetrics:
    return GitMetrics(
        is_repo=True,
        total_commits=10,
        total_lines_added=added,
        total_lines_deleted=deleted,
        avg_diff_size=float(added + deleted),
        deletion_ratio=0.0,
        active_branches=1,
        long_lived_branches=0,
        test_lines_added=0,
        test_line_ratio=0.0,
        interaction_count=interactions,
    )


def _proj(files: int = 50) -> ProjectProfile:
    return ProjectProfile(
        project_type="library",
        file_tree_depth=3,
        file_tree_breadth=5,
        total_files=files,
        has_ai_constraint=False,
        constraint_files=[],
        strata_completeness=0.0,
        primary_language="python",
        test_file_ratio=0.1,
    )


class TestClassifyEfficiency:
    def test_high_leverage(self) -> None:
        """High code + low interaction → high-leverage."""
        m = _git(added=2000, deleted=100, interactions=500)
        assert classify_efficiency(m) == Efficiency.EFF_HIGH_LEVERAGE

    def test_grindy(self) -> None:
        """High code + high interaction → grindy."""
        m = _git(added=2000, deleted=100, interactions=3000)
        assert classify_efficiency(m) == Efficiency.EFF_GRINDY

    def test_idle(self) -> None:
        """Low code + high interaction → idle."""
        m = _git(added=50, deleted=10, interactions=3000)
        assert classify_efficiency(m) == Efficiency.EFF_IDLE

    def test_scaffold(self) -> None:
        """Low code + low interaction → scaffold."""
        m = _git(added=50, deleted=10, interactions=100)
        assert classify_efficiency(m) == Efficiency.EFF_SCAFFOLD

    def test_maintenance(self) -> None:
        """Large existing project + low new code + high interaction → maintenance."""
        m = _git(added=100, deleted=50, interactions=3000)
        p = _proj(files=200)
        assert classify_efficiency(m, p) == Efficiency.EFF_MAINTENANCE

    def test_maintenance_not_triggered_for_small_project(self) -> None:
        """Small project with same metrics → idle, not maintenance."""
        m = _git(added=100, deleted=50, interactions=3000)
        p = _proj(files=30)  # small project
        assert classify_efficiency(m, p) == Efficiency.EFF_IDLE

    def test_no_project_profile(self) -> None:
        """Works without project profile (skips maintenance check)."""
        m = _git(added=2000, deleted=100, interactions=500)
        assert classify_efficiency(m) == Efficiency.EFF_HIGH_LEVERAGE


class TestEfficiencyProfile:
    def test_description_present(self) -> None:
        for eff in Efficiency:
            profile = EfficiencyProfile(eff)
            assert len(profile.description) > 10

    def test_label(self) -> None:
        profile = EfficiencyProfile(Efficiency.EFF_GRINDY)
        assert profile.label == "eff-grindy"
