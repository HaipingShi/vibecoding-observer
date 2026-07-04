"""Tests for the Aggregator.

Validates label distributions, project cross-tabs, agent breakdowns, and
ranking. Uses synthetic LabeledEvents.
"""

from __future__ import annotations

from observer.aggregator import aggregate
from observer.extractor import LabeledEvent
from observer.ir import IREvent
from observer.taxonomy import Activation, ResponsePattern, Waste

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _labeled(
    role: str,
    text: str,
    agent: str,
    labels: frozenset = frozenset(),
    is_handoff: bool = False,
    project: str = "alpha",
) -> LabeledEvent:
    ev = IREvent(
        ts="2026-06-28T13:00:00Z",
        source_agent=agent,  # type: ignore[arg-type]
        cwd=f"/p/{project}",
        project=project,
        role=role,  # type: ignore[arg-type]
        text=text,
        tool_calls=(),
        is_handoff=is_handoff,
    )
    return LabeledEvent(event=ev, labels=labels)


# --------------------------------------------------------------------------- #
# Core aggregation
# --------------------------------------------------------------------------- #


class TestAggregate:
    def test_empty_input(self) -> None:
        report = aggregate([])
        assert report.total_events == 0
        assert report.total_projects == 0

    def test_single_project_counts(self) -> None:
        events = [
            _labeled("user", "a", "claude", frozenset({Activation.ACT_PASSIVE})),
            _labeled("assistant", "b", "claude", frozenset({ResponsePattern.DEGEN_INTUITION})),
            _labeled("user", "c", "codex", frozenset({Waste.WASTE_HANDOFF}), is_handoff=True),
        ]
        report = aggregate([("alpha", events)])
        assert report.total_events == 3
        assert report.total_projects == 1
        assert report.total_handoffs == 1
        ps = report.project_summaries[0]
        assert ps.project == "alpha"
        assert ps.user_event_count == 2
        assert ps.assistant_event_count == 1
        assert ps.handoff_count == 1

    def test_global_label_counts(self) -> None:
        events = [
            _labeled("user", "a", "claude", frozenset({Activation.ACT_PASSIVE})),
            _labeled("user", "b", "claude", frozenset({Activation.ACT_PASSIVE})),
            _labeled("assistant", "c", "claude", frozenset({ResponsePattern.DEGEN_TOOL_FAIL})),
        ]
        report = aggregate([("alpha", events)])
        assert report.label_count("act-passive") == 2
        assert report.label_count("degen-tool-fail") == 1


# --------------------------------------------------------------------------- #
# Project rankings
# --------------------------------------------------------------------------- #


class TestRankings:
    def test_top_waste_projects(self) -> None:
        proj_a = [
            _labeled("user", "x", "claude", frozenset({Waste.WASTE_RESTATE}), project="a"),
            _labeled("user", "y", "claude", frozenset({Waste.WASTE_HANDOFF}), project="a"),
        ]
        proj_b = [
            _labeled("user", "z", "claude", frozenset({Waste.WASTE_RESTATE}), project="b"),
        ]
        report = aggregate([("a", proj_a), ("b", proj_b)])
        assert report.top_waste_projects[0] == ("a", 2)
        assert report.top_waste_projects[1] == ("b", 1)

    def test_top_degenerate_projects(self) -> None:
        proj_a = [
            _labeled("assistant", "x", "claude", frozenset({ResponsePattern.DEGEN_INTUITION}), project="a"),
        ]
        proj_b = [
            _labeled("assistant", "y", "claude", frozenset({ResponsePattern.DEGEN_TOOL_FAIL}), project="b"),
            _labeled("assistant", "z", "claude", frozenset({ResponsePattern.DEGEN_WRONG_LAYER}), project="b"),
        ]
        report = aggregate([("a", proj_a), ("b", proj_b)])
        assert report.top_degenerate_projects[0] == ("b", 2)
        assert report.top_degenerate_projects[1] == ("a", 1)


# --------------------------------------------------------------------------- #
# Agent breakdowns
# --------------------------------------------------------------------------- #


class TestAgentBreakdown:
    def test_per_agent_label_counts(self) -> None:
        events = [
            _labeled("user", "a", "claude", frozenset({Activation.ACT_PASSIVE})),
            _labeled("user", "b", "codex", frozenset({Activation.ACT_FIRST_PRINCIPLE})),
        ]
        report = aggregate([("alpha", events)])
        assert len(report.agent_breakdowns) == 2
        agents = {ab.agent for ab in report.agent_breakdowns}
        assert agents == {"claude", "codex"}

    def test_label_by_agent_lookup(self) -> None:
        events = [
            _labeled("user", "a", "claude", frozenset({Activation.ACT_PASSIVE})),
            _labeled("user", "b", "codex", frozenset({Activation.ACT_FIRST_PRINCIPLE})),
        ]
        report = aggregate([("alpha", events)])
        assert report.label_by_agent["claude"].get("act-passive") == 1
        assert report.label_by_agent["codex"].get("act-first-principle") == 1

    def test_degenerate_count_per_agent(self) -> None:
        events = [
            _labeled("assistant", "a", "claude", frozenset({ResponsePattern.DEGEN_INTUITION})),
            _labeled("assistant", "b", "codex", frozenset({Activation.ACT_PASSIVE})),
        ]
        report = aggregate([("alpha", events)])
        claude_ab = next(ab for ab in report.agent_breakdowns if ab.agent == "claude")
        codex_ab = next(ab for ab in report.agent_breakdowns if ab.agent == "codex")
        assert claude_ab.degenerate_count == 1
        assert codex_ab.degenerate_count == 0


# --------------------------------------------------------------------------- #
# Project summary fields
# --------------------------------------------------------------------------- #


class TestProjectSummary:
    def test_waste_total(self) -> None:
        events = [
            _labeled("user", "a", "claude", frozenset({Waste.WASTE_RESTATE, Waste.WASTE_BLIND_EDIT})),
        ]
        report = aggregate([("alpha", events)])
        assert report.project_summaries[0].waste_total == 2

    def test_degenerate_rate_capped(self) -> None:
        # One event with 3 degen labels → rate capped at 1.0.
        events = [
            _labeled(
                "assistant",
                "a",
                "claude",
                frozenset(
                    {
                        ResponsePattern.DEGEN_INTUITION,
                        ResponsePattern.DEGEN_TOOL_FAIL,
                        ResponsePattern.DEGEN_WRONG_LAYER,
                    }
                ),
            ),
        ]
        report = aggregate([("alpha", events)])
        assert report.project_summaries[0].degenerate_rate == 1.0

    def test_cwd_captured(self) -> None:
        events = [_labeled("user", "a", "claude", project="myproj")]
        report = aggregate([("myproj", events)])
        assert report.project_summaries[0].cwd == "/p/myproj"


# --------------------------------------------------------------------------- #
# Developer type (ICSE 2026 Type A/B)
# --------------------------------------------------------------------------- #


class TestDeveloperType:
    def test_type_a_high_deep_activation(self) -> None:
        """>30% deep activations → Type A (strategic delegator)."""
        events = [
            _labeled("user", str(i), "claude", frozenset({Activation.ACT_FIRST_PRINCIPLE}))
            for i in range(4)
        ] + [_labeled("user", "p", "claude", frozenset({Activation.ACT_PASSIVE}))]
        report = aggregate([("alpha", events)])
        assert "A" in report.developer_type

    def test_type_b_low_deep_activation(self) -> None:
        """<30% deep activations → Type B (hands-on operator)."""
        events = [
            _labeled("user", str(i), "claude", frozenset({Activation.ACT_PASSIVE}))
            for i in range(8)
        ] + [_labeled("user", "d", "claude", frozenset({Activation.ACT_CONSTRAINT_REASON}))]
        report = aggregate([("alpha", events)])
        assert "B" in report.developer_type

    def test_unknown_no_activations(self) -> None:
        events = [_labeled("user", "x", "claude") for _ in range(5)]
        report = aggregate([("alpha", events)])
        assert report.developer_type == "unknown"
