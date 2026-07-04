"""Anomaly Detector — select the 5-15% of events worth an LLM deep-read.

The Extractor tags *every* event cheaply; the Aggregator folds them into
summary metrics. But raw labeled events are too numerous to send to an LLM
or display in full. The Anomaly Detector applies statistical thresholds to
pick the slices that carry the most signal:

  1. Project-level degenerate share outliers (project degen-rate > mean + 1σ)
  2. Activation efficacy outliers (an activation label that rarely/never
     precedes an engineering response → it's failing for this user)
  3. Long-tail sessions (event count > P90 within a project)
  4. Handoff-dense projects (handoffs above an absolute threshold)

Output is a list of :class:`Anomaly` records, each pointing at the events
the LLM Analyzer should read. Pure statistics, no LLM, no ML — Strategy
Invariant: keep the OSS dependency surface to "one working LLM".
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field

from observer.extractor import LabeledEvent
from observer.taxonomy import ResponsePattern

__all__ = [
    "Anomaly",
    "AnomalyDetector",
    "AnomalyKind",
    "detect",
]


# --------------------------------------------------------------------------- #
# Output types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Anomaly:
    """A single anomaly pointing at events for LLM deep-read."""

    kind: str
    """One of AnomalyKind.* — categorizes the anomaly for reporting."""

    project: str
    description: str
    """Human-readable explanation of why this slice is anomalous."""

    events: tuple[LabeledEvent, ...] = field(default_factory=tuple)
    """The specific events the LLM should read to explain this anomaly."""

    metric_value: float = 0.0
    """The numeric value that crossed the threshold (for audit)."""


class AnomalyKind:
    """Closed set of anomaly categories."""

    PROJECT_DEGENERATE = "project-degenerate-outlier"
    ACTIVATION_INEFFECTIVE = "activation-ineffective"
    LONG_TAIL_SESSION = "long-tail-session"
    HANDOFF_DENSE = "handoff-dense-project"


# --------------------------------------------------------------------------- #
# Detector
# --------------------------------------------------------------------------- #

# The engineering (good) response labels — used to measure activation efficacy.
_ENG_VALUES: frozenset[str] = frozenset(
    {ResponsePattern.ENG_DECOMPOSE.value, ResponsePattern.ENG_VERIFY.value}
)

# Degenerate labels (8 defects + tool-fail).
_DEGEN_VALUES: frozenset[str] = frozenset(
    {
        ResponsePattern.DEGEN_INTUITION.value,
        ResponsePattern.DEGEN_STOPS_AT_WORKS.value,
        ResponsePattern.DEGEN_KNOWLEDGE_AS_ABILITY.value,
        ResponsePattern.DEGEN_WRONG_LAYER.value,
        ResponsePattern.DEGEN_IGNORE_LIFECYCLE.value,
        ResponsePattern.DEGEN_TOOL_FAIL.value,
        ResponsePattern.DEGEN_INSTANT_GRATIFICATION.value,
        ResponsePattern.DEGEN_SUGGESTER_PREFERENCE.value,
        ResponsePattern.DEGEN_FIXATION.value,
    }
)


class AnomalyDetector:
    """Detect anomalous slices in labeled events per project.

    Args:
        long_tail_percentile: Session length percentile for long-tail (default 90).
        handoff_threshold: Min handoffs in a project to flag it dense (default 3).
        min_events_for_stats: Min events before σ-based outlier detection
            applies (avoid noise on tiny projects; default 5).
    """

    def __init__(
        self,
        long_tail_percentile: float = 90.0,
        handoff_threshold: int = 3,
        min_events_for_stats: int = 5,
    ) -> None:
        self.long_tail_percentile = long_tail_percentile
        self.handoff_threshold = handoff_threshold
        self.min_events_for_stats = min_events_for_stats

    def detect(
        self,
        labeled_by_project: Iterable[tuple[str, list[LabeledEvent]]],
    ) -> list[Anomaly]:
        """Return anomalies across all projects, ordered by signal strength."""
        projects = list(labeled_by_project)
        anomalies: list[Anomaly] = []

        anomalies.extend(self._detect_degenerate_outliers(projects))
        anomalies.extend(self._detect_activation_ineffective(projects))
        anomalies.extend(self._detect_long_tail(projects))
        anomalies.extend(self._detect_handoff_dense(projects))

        return anomalies

    # ----------------------------------------------------------------- #
    # 1. Project-level degenerate outliers
    # ----------------------------------------------------------------- #
    def _detect_degenerate_outliers(
        self,
        projects: list[tuple[str, list[LabeledEvent]]],
    ) -> list[Anomaly]:
        # Compute per-project degenerate event rate (events-with-degen / total).
        rates: list[tuple[str, float, list[LabeledEvent]]] = []
        for project, labeled in projects:
            if len(labeled) < self.min_events_for_stats:
                continue
            degen_events = sum(
                1
                for le in labeled
                if le.label_values & _DEGEN_VALUES
            )
            rate = degen_events / len(labeled)
            rates.append((project, rate, labeled))

        if len(rates) < 2:
            return []

        values = [r[1] for r in rates]
        mean = statistics.fmean(values)
        try:
            stdev = statistics.stdev(values)
        except statistics.StatisticsError:
            return []

        threshold = mean + stdev
        anomalies: list[Anomaly] = []
        for project, rate, labeled in rates:
            if rate > threshold:
                degen_events = tuple(
                    le for le in labeled if le.label_values & _DEGEN_VALUES
                )
                anomalies.append(
                    Anomaly(
                        kind=AnomalyKind.PROJECT_DEGENERATE,
                        project=project,
                        description=(
                            f"Degenerate-response rate {rate:.0%} exceeds "
                            f"mean+1σ ({threshold:.0%})"
                        ),
                        events=degen_events,
                        metric_value=rate,
                    )
                )
        return anomalies

    # ----------------------------------------------------------------- #
    # 2. Activation ineffectiveness
    # ----------------------------------------------------------------- #
    def _detect_activation_ineffective(
        self,
        projects: list[tuple[str, list[LabeledEvent]]],
    ) -> list[Anomaly]:
        # For each activation label, measure how often an engineering response
        # follows it. If an activation NEVER triggers eng-* across all data,
        # flag the events carrying it as ineffective.
        from observer.taxonomy import Activation

        all_events: list[LabeledEvent] = []
        for _, labeled in projects:
            all_events.extend(labeled)

        anomalies: list[Anomaly] = []
        for act in Activation:
            act_events = [
                le for le in all_events if act.value in le.label_values
            ]
            if len(act_events) < 3:
                continue  # not enough samples
            # Did a subsequent assistant turn (within 2 events) show eng-*?
            eng_followups = 0
            for idx, le in enumerate(all_events):
                if act.value not in le.label_values:
                    continue
                window = all_events[idx + 1 : idx + 3]
                if any(
                    we.label_values & _ENG_VALUES
                    for we in window
                ):
                    eng_followups += 1
            efficacy = eng_followups / len(act_events) if act_events else 0.0
            # Flag if efficacy is very low (below 20%) — the activation
            # isn't pulling the LLM into engineering mode.
            if efficacy < 0.2:
                anomalies.append(
                    Anomaly(
                        kind=AnomalyKind.ACTIVATION_INEFFECTIVE,
                        project="*",
                        description=(
                            f"Activation '{act.value}' rarely triggers an "
                            f"engineering response (efficacy {efficacy:.0%})"
                        ),
                        events=tuple(act_events[:10]),  # cap samples
                        metric_value=efficacy,
                    )
                )
        return anomalies

    # ----------------------------------------------------------------- #
    # 3. Long-tail sessions (per-project event length)
    # ----------------------------------------------------------------- #
    def _detect_long_tail(
        self,
        projects: list[tuple[str, list[LabeledEvent]]],
    ) -> list[Anomaly]:
        # Flag projects whose event count is at/above the configured percentile
        # across all projects — the longest interaction lines carry the most
        # entanglement signal for an LLM to unpack.
        lengths = [len(labeled) for _, labeled in projects if labeled]
        if len(lengths) < 3:
            return []
        p_threshold = _percentile(lengths, self.long_tail_percentile)
        anomalies: list[Anomaly] = []
        for project, labeled in projects:
            if len(labeled) >= p_threshold and len(labeled) > 0:
                anomalies.append(
                    Anomaly(
                        kind=AnomalyKind.LONG_TAIL_SESSION,
                        project=project,
                        description=(
                            f"Long interaction line ({len(labeled)} events, "
                            f"P{self.long_tail_percentile:.0f}={p_threshold:.0f})"
                        ),
                        events=tuple(labeled[:10]),  # cap samples
                        metric_value=float(len(labeled)),
                    )
                )
        return anomalies

    # ----------------------------------------------------------------- #
    # 4. Handoff-dense projects
    # ----------------------------------------------------------------- #
    def _detect_handoff_dense(
        self,
        projects: list[tuple[str, list[LabeledEvent]]],
    ) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        for project, labeled in projects:
            handoffs = [le for le in labeled if le.event.is_handoff]
            if len(handoffs) >= self.handoff_threshold:
                anomalies.append(
                    Anomaly(
                        kind=AnomalyKind.HANDOFF_DENSE,
                        project=project,
                        description=(
                            f"High handoff density ({len(handoffs)} cross-agent "
                            f"switches) — likely repeated stalls"
                        ),
                        events=tuple(handoffs),
                        metric_value=float(len(handoffs)),
                    )
                )
        return anomalies


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def detect(
    labeled_by_project: Iterable[tuple[str, list[LabeledEvent]]],
) -> list[Anomaly]:
    """One-shot anomaly detection without instantiating."""
    return AnomalyDetector().detect(labeled_by_project)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _percentile(data: list[int], pct: float) -> float:
    """Simple percentile (linear interpolation)."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac
