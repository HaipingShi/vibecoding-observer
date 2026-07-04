"""Tests for the DiagnosticEngine (cross-diagnostic rules)."""

from __future__ import annotations

from observer.aggregator import AgentBreakdown, ProjectSummary, Report
from observer.diagnostic_engine import diagnose
from observer.episode import EpisodeSummary
from observer.git_analyzer import GitMetrics
from observer.project_scanner import ProjectProfile


def _profile(
    ptype: str = "library",
    constraint: bool = False,
    strata: float = 0.0,
    files: int = 50,
) -> ProjectProfile:
    return ProjectProfile(
        project_type=ptype,
        file_tree_depth=3,
        file_tree_breadth=5,
        total_files=files,
        has_ai_constraint=constraint,
        constraint_files=["CLAUDE.md"] if constraint else [],
        strata_completeness=strata,
        primary_language="python",
        test_file_ratio=0.1,
    )


def _git(
    added: int = 0,
    deleted: int = 0,
    interactions: int = 0,
    deletion_ratio: float = 0.0,
) -> GitMetrics:
    return GitMetrics(
        is_repo=True,
        total_commits=10,
        total_lines_added=added,
        total_lines_deleted=deleted,
        avg_diff_size=float(added + deleted),
        deletion_ratio=deletion_ratio,
        active_branches=1,
        long_lived_branches=0,
        test_lines_added=0,
        test_line_ratio=0.0,
        interaction_count=interactions,
    )


def _report(
    events: int = 1000,
    degen: int = 50,
    wrong_layer: int = 10,
    lifecycle: int = 0,
    reversal: int = 0,
) -> Report:
    return Report(
        project_summaries=[ProjectSummary(
            project="test", cwd="/p/test", event_count=events,
            label_counts={"degen-wrong-layer": wrong_layer, "degen-ignore-lifecycle": lifecycle, "waste-reversal": reversal},
            degenerate_count=degen, waste_total=reversal, handoff_count=0,
            user_event_count=events // 2, assistant_event_count=events // 2,
        )],
        agent_breakdowns=[AgentBreakdown(agent="claude", event_count=events, label_counts={}, degenerate_count=degen)],
        global_label_counts={"degen-wrong-layer": wrong_layer, "degen-ignore-lifecycle": lifecycle, "waste-reversal": reversal},
        total_events=events, total_projects=1, total_handoffs=0,
        top_waste_projects=[], top_degenerate_projects=[],
        label_by_agent={},
    )


def _episode(
    goal: str = "请分析 API contract 漂移风险",
    events: int = 60,
    implementation: int = 0,
    verification: int = 0,
    closure: int = 0,
) -> EpisodeSummary:
    return EpisodeSummary(
        project="test",
        cwd="/p/test",
        start_ts="2026-06-28T13:00:00Z",
        end_ts="2026-06-28T13:10:00Z",
        start_index=0,
        end_index=events - 1,
        event_count=events,
        goal=goal,
        constraints=(),
        implementation_count=implementation,
        verification_count=verification,
        correction_count=0,
        closure_count=closure,
    )


class TestConstraintGap:
    def test_missing_constraint_with_degen(self) -> None:
        p = _profile(constraint=False, strata=0.0)
        r = _report(events=1000, degen=200)
        findings = diagnose(project=p, git=None, report=r)
        assert any("约束缺失" in f.title for f in findings)

    def test_has_constraint_no_finding(self) -> None:
        p = _profile(constraint=True, strata=0.8)
        r = _report(events=1000, degen=10)
        findings = diagnose(project=p, git=None, report=r)
        assert not any("约束缺失" in f.title for f in findings)


class TestEfficiencyDiagnosis:
    def test_high_leverage(self) -> None:
        g = _git(added=2000, deleted=100, interactions=500)
        r = _report(events=500)
        findings = diagnose(project=_profile(), git=g, report=r)
        assert any("高杠杆" in f.title for f in findings)
        assert all(f.severity == "info" for f in findings if "高杠杆" in f.title)

    def test_idle(self) -> None:
        g = _git(added=50, deleted=10, interactions=3000)
        r = _report(events=3000)
        findings = diagnose(project=_profile(), git=g, report=r)
        assert any("空转" in f.title for f in findings)


class TestLayerConfusion:
    def test_dominant_wrong_layer(self) -> None:
        r = _report(events=1000, degen=100, wrong_layer=50)
        findings = diagnose(project=_profile(ptype="complex-app"), git=None, report=r)
        assert any("层级误判" in f.title for f in findings)

    def test_low_wrong_layer_no_finding(self) -> None:
        r = _report(events=1000, degen=100, wrong_layer=5)
        findings = diagnose(project=_profile(), git=None, report=r)
        assert not any("层级误判" in f.title for f in findings)


class TestDocLifecycle:
    def test_doc_vault_lifecycle(self) -> None:
        p = _profile(ptype="doc-vault", constraint=False)
        r = _report(events=500, lifecycle=50)
        findings = diagnose(project=p, git=None, report=r)
        assert any("生命周期" in f.title for f in findings)


class TestReversalChurn:
    def test_high_deletion_and_reversal(self) -> None:
        g = _git(added=500, deleted=300, interactions=1000, deletion_ratio=0.4)
        r = _report(events=1000, reversal=20)
        findings = diagnose(project=_profile(), git=g, report=r)
        assert any("废弃率" in f.title for f in findings)


class TestEpisodeDiagnostics:
    def test_top_level_goal_without_engineering_loop(self) -> None:
        episodes = [_episode() for _ in range(20)]

        findings = diagnose(project=None, git=None, report=None, episodes=episodes)

        assert any("顶层目标存在但工程闭环缺失" in f.title for f in findings)

    def test_implementation_verification_gap(self) -> None:
        episodes = [
            _episode(events=5, implementation=1, verification=0, closure=0)
            for _ in range(12)
        ]

        findings = diagnose(project=None, git=None, report=None, episodes=episodes)

        assert any("验证/收束不足" in f.title for f in findings)

    def test_weak_goal_quality(self) -> None:
        episodes = [_episode(goal="开做", events=1) for _ in range(25)]

        findings = diagnose(project=None, git=None, report=None, episodes=episodes)

        assert any("任务入口目标质量偏弱" in f.title for f in findings)


class TestSeverity:
    def test_critical_sorted_first(self) -> None:
        p = _profile(constraint=False, strata=0.0)
        r = _report(events=1000, degen=500, wrong_layer=400)
        findings = diagnose(project=p, git=None, report=r)
        if len(findings) > 1:
            severity_order = {"critical": 0, "warning": 1, "info": 2}
            for i in range(len(findings) - 1):
                assert severity_order[findings[i].severity] <= severity_order[findings[i + 1].severity]


class TestEmpty:
    def test_no_signals(self) -> None:
        findings = diagnose(project=None, git=None, report=None)
        assert findings == []
