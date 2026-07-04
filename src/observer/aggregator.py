"""Aggregator — fold labeled events into structured summary metrics.

Consumes ``LabeledEvent`` lists (one per project, from the Extractor) and
produces a :class:`Report` of aggregate metrics: label distributions,
project cross-tabs, per-agent breakdowns, and time trends. This is the
"statistics layer" that runs entirely locally (Strategic Principle: report
is driven by locally-computable structured metrics; LLM only explains).

Output shape is designed for the Reporter to render the report with zero
further computation — every number the report needs is pre-computed here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from observer.extractor import LabeledEvent
from observer.taxonomy import ResponsePattern

__all__ = [
    "AgentBreakdown",
    "ProjectSummary",
    "Report",
    "aggregate",
]


# --------------------------------------------------------------------------- #
# Summary dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """Aggregate metrics for a single project."""

    project: str
    cwd: str
    event_count: int
    label_counts: Mapping[str, int]
    """Label value -> occurrence count across all events in this project."""

    degenerate_count: int
    """Total degen-* labels (the five defects + tool-fail)."""

    waste_total: int
    """Total waste-* labels."""

    handoff_count: int
    user_event_count: int
    assistant_event_count: int

    @property
    def degenerate_rate(self) -> float:
        """Fraction of events carrying any degen-* label."""
        if self.event_count == 0:
            return 0.0
        # degen_count counts label occurrences, not events; approximate rate
        # by events-with-degen. Recompute precisely from label_counts where
        # each event can carry multiple degen labels — but for a rate we want
        # events. We approximate: degen occurrences / events (capped at 1.0).
        return min(1.0, self.degenerate_count / self.event_count)


@dataclass(frozen=True, slots=True)
class AgentBreakdown:
    """Per-agent label counts across all projects."""

    agent: str
    event_count: int
    label_counts: Mapping[str, int]
    degenerate_count: int


@dataclass(frozen=True, slots=True)
class Report:
    """Top-level aggregate report for all analyzed projects."""

    project_summaries: list[ProjectSummary]
    agent_breakdowns: list[AgentBreakdown]

    global_label_counts: Mapping[str, int]
    """Label value -> total count across all projects."""

    total_events: int
    total_projects: int
    total_handoffs: int

    top_waste_projects: list[tuple[str, int]]
    """Projects ranked by waste_total, descending (name, count)."""

    top_degenerate_projects: list[tuple[str, int]]
    """Projects ranked by degenerate_count, descending."""

    label_by_agent: Mapping[str, Mapping[str, int]]
    """agent -> {label_value -> count}. For agent-vs-agent comparison."""

    def label_count(self, label_value: str) -> int:
        """Convenience: total count for a single label value."""
        return self.global_label_counts.get(label_value, 0)

    @property
    def developer_type(self) -> str:
        """Classify the user's collaboration style (ICSE 2026 Type A/B).

        Type A — Strategic Delegator: delegates high-cognitive-load tasks to
        the LLM but actively steers with deep activations (first-principle,
        constraint-reason). High act-* / low act-passive ratio.

        Type B — Hands-on Operator: does high-load tasks themselves, delegates
        only low-load tasks (templates, formatting). Low deep-activation,
        higher passive or shallow interaction.

        Detection: ratio of deep activations (first-principle + constraint-reason
        + ab-falsify) to total user interactions. Above 0.3 → Type A.
        """
        deep = (
            self.label_count("act-first-principle")
            + self.label_count("act-constraint-reason")
            + self.label_count("act-ab-falsify")
        )
        passive = self.label_count("act-passive")
        total_user_acts = deep + passive + self.label_count("act-scale-stress")
        if total_user_acts == 0:
            return "unknown"
        return "A (strategic delegator)" if deep / total_user_acts > 0.3 else "B (hands-on operator)"


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


# The degenerate labels (5 defects + tool-fail) used for rate calculations.
_DEGENERATE_VALUES: frozenset[str] = frozenset(
    {
        ResponsePattern.DEGEN_INTUITION.value,
        ResponsePattern.DEGEN_STOPS_AT_WORKS.value,
        ResponsePattern.DEGEN_KNOWLEDGE_AS_ABILITY.value,
        ResponsePattern.DEGEN_WRONG_LAYER.value,
        ResponsePattern.DEGEN_IGNORE_LIFECYCLE.value,
        ResponsePattern.DEGEN_TOOL_FAIL.value,
    }
)


def aggregate(
    labeled_by_project: Iterable[tuple[str, list[LabeledEvent]]],
) -> Report:
    """Aggregate labeled events across projects into a Report.

    Args:
        labeled_by_project: An iterable of (project_name, labeled_events)
            pairs. Typically the output of running the Extractor per project.

    Returns:
        A Report with all metrics the Reporter needs.
    """
    project_summaries: list[ProjectSummary] = []
    agent_label_counts: dict[str, Counter[str]] = {}
    agent_event_counts: dict[str, int] = {}
    global_counts: Counter[str] = Counter()
    total_events = 0
    total_handoffs = 0

    for project, labeled in labeled_by_project:
        ps = _summarize_project(project, labeled)
        project_summaries.append(ps)
        total_events += ps.event_count
        total_handoffs += ps.handoff_count

        for lbl_val, cnt in ps.label_counts.items():
            global_counts[lbl_val] += cnt

        # Accumulate per-agent stats from this project's events.
        for le in labeled:
            agent = le.event.source_agent
            agent_event_counts[agent] = agent_event_counts.get(agent, 0) + 1
            alc = agent_label_counts.setdefault(agent, Counter())
            for lv in le.label_values:
                alc[lv] += 1

    # Build agent breakdowns.
    agent_breakdowns: list[AgentBreakdown] = []
    label_by_agent: dict[str, Mapping[str, int]] = {}
    for agent in sorted(agent_label_counts):
        alc = agent_label_counts[agent]
        degen = sum(c for v, c in alc.items() if v in _DEGENERATE_VALUES)
        agent_breakdowns.append(
            AgentBreakdown(
                agent=agent,
                event_count=agent_event_counts.get(agent, 0),
                label_counts=dict(alc),
                degenerate_count=degen,
            )
        )
        label_by_agent[agent] = dict(alc)

    # Rank projects by waste and degenerate counts.
    top_waste = sorted(
        ((ps.project, ps.waste_total) for ps in project_summaries),
        key=lambda x: x[1],
        reverse=True,
    )
    top_degen = sorted(
        ((ps.project, ps.degenerate_count) for ps in project_summaries),
        key=lambda x: x[1],
        reverse=True,
    )

    return Report(
        project_summaries=project_summaries,
        agent_breakdowns=agent_breakdowns,
        global_label_counts=dict(global_counts),
        total_events=total_events,
        total_projects=len(project_summaries),
        total_handoffs=total_handoffs,
        top_waste_projects=top_waste,
        top_degenerate_projects=top_degen,
        label_by_agent=label_by_agent,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_WASTE_PREFIX = "waste-"


def _summarize_project(project: str, labeled: list[LabeledEvent]) -> ProjectSummary:
    """Compute per-project summary metrics."""
    label_counts: Counter[str] = Counter()
    user_count = 0
    assistant_count = 0
    handoffs = 0
    cwd = ""

    for le in labeled:
        if not cwd:
            cwd = le.event.cwd
        if le.event.role == "user":
            user_count += 1
        elif le.event.role == "assistant":
            assistant_count += 1
        if le.event.is_handoff:
            handoffs += 1
        for lv in le.label_values:
            label_counts[lv] += 1

    degen_total = sum(c for v, c in label_counts.items() if v in _DEGENERATE_VALUES)
    waste_total = sum(c for v, c in label_counts.items() if v.startswith(_WASTE_PREFIX))

    return ProjectSummary(
        project=project,
        cwd=cwd,
        event_count=len(labeled),
        label_counts=dict(label_counts),
        degenerate_count=degen_total,
        waste_total=waste_total,
        handoff_count=handoffs,
        user_event_count=user_count,
        assistant_event_count=assistant_count,
    )
