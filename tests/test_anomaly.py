"""Tests for the Anomaly Detector.

Validates that statistical thresholds select anomalous slices for deep read,
targeting a 5-15% selection rate.
"""

from __future__ import annotations

from observer.anomaly import AnomalyKind, detect
from observer.extractor import LabeledEvent
from observer.ir import IREvent
from observer.taxonomy import Activation, ResponsePattern

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _labeled(
    role: str,
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
        text="x",
        is_handoff=is_handoff,
    )
    return LabeledEvent(event=ev, labels=labels)


def _degen() -> frozenset:
    return frozenset({ResponsePattern.DEGEN_INTUITION})


def _eng() -> frozenset:
    return frozenset({ResponsePattern.ENG_DECOMPOSE})


# --------------------------------------------------------------------------- #
# Project degenerate outliers
# --------------------------------------------------------------------------- #


class TestProjectDegenerate:
    def test_outlier_project_flagged(self) -> None:
        # alpha: 90% degen, beta/gamma: 0% → alpha is the statistical outlier.
        alpha = [_labeled("assistant", "claude", _degen()) for _ in range(9)]
        alpha += [_labeled("assistant", "claude") for _ in range(1)]
        beta = [_labeled("assistant", "claude") for _ in range(10)]
        gamma = [_labeled("assistant", "claude") for _ in range(10)]
        anomalies = detect([("alpha", alpha), ("beta", beta), ("gamma", gamma)])
        kinds = {a.kind for a in anomalies}
        assert AnomalyKind.PROJECT_DEGENERATE in kinds
        degen_anom = [a for a in anomalies if a.kind == AnomalyKind.PROJECT_DEGENERATE]
        assert degen_anom[0].project == "alpha"

    def test_low_event_count_project_skipped(self) -> None:
        # Too few events → no σ-based detection.
        small = [_labeled("assistant", "claude", _degen()) for _ in range(2)]
        anomalies = detect([("small", small)])
        assert not any(a.kind == AnomalyKind.PROJECT_DEGENERATE for a in anomalies)


# --------------------------------------------------------------------------- #
# Activation ineffectiveness
# --------------------------------------------------------------------------- #


class TestActivationIneffective:
    def test_ineffective_activation_flagged(self) -> None:
        # act-first-principle used 5 times but NEVER followed by eng-*.
        events = [_labeled("user", "claude", frozenset({Activation.ACT_FIRST_PRINCIPLE})) for _ in range(5)]
        events += [_labeled("assistant", "claude") for _ in range(5)]
        anomalies = detect([("alpha", events)])
        ineff = [a for a in anomalies if a.kind == AnomalyKind.ACTIVATION_INEFFECTIVE]
        assert len(ineff) >= 1
        assert "act-first-principle" in ineff[0].description

    def test_effective_activation_not_flagged(self) -> None:
        # act followed by eng-* in the next event → effective.
        events = [
            _labeled("user", "claude", frozenset({Activation.ACT_CONSTRAINT_REASON})),
            _labeled("assistant", "claude", _eng()),
            _labeled("user", "claude", frozenset({Activation.ACT_CONSTRAINT_REASON})),
            _labeled("assistant", "claude", _eng()),
            _labeled("user", "claude", frozenset({Activation.ACT_CONSTRAINT_REASON})),
            _labeled("assistant", "claude", _eng()),
        ]
        anomalies = detect([("alpha", events)])
        ineff = [a for a in anomalies if a.kind == AnomalyKind.ACTIVATION_INEFFECTIVE]
        # efficacy is high → not flagged
        constraint_ineff = [a for a in ineff if "act-constraint-reason" in a.description]
        assert constraint_ineff == []


# --------------------------------------------------------------------------- #
# Long-tail sessions
# --------------------------------------------------------------------------- #


class TestLongTail:
    def test_longest_project_flagged(self) -> None:
        big = [_labeled("user", "claude") for _ in range(100)]
        small = [_labeled("user", "claude") for _ in range(10)]
        tiny = [_labeled("user", "claude") for _ in range(5)]
        anomalies = detect([("big", big), ("small", small), ("tiny", tiny)])
        longtail = [a for a in anomalies if a.kind == AnomalyKind.LONG_TAIL_SESSION]
        assert len(longtail) >= 1
        assert longtail[0].project == "big"


# --------------------------------------------------------------------------- #
# Handoff density
# --------------------------------------------------------------------------- #


class TestHandoffDense:
    def test_dense_handoffs_flagged(self) -> None:
        events = [_labeled("user", "claude", is_handoff=True) for _ in range(4)]
        events += [_labeled("user", "claude") for _ in range(6)]
        anomalies = detect([("alpha", events)])
        dense = [a for a in anomalies if a.kind == AnomalyKind.HANDOFF_DENSE]
        assert len(dense) == 1
        assert dense[0].project == "alpha"

    def test_few_handoffs_not_flagged(self) -> None:
        events = [_labeled("user", "claude", is_handoff=True) for _ in range(1)]
        events += [_labeled("user", "claude") for _ in range(10)]
        anomalies = detect([("alpha", events)])
        dense = [a for a in anomalies if a.kind == AnomalyKind.HANDOFF_DENSE]
        assert dense == []


# --------------------------------------------------------------------------- #
# Structural
# --------------------------------------------------------------------------- #


class TestStructural:
    def test_empty_input(self) -> None:
        assert detect([]) == []

    def test_events_attached_for_llm_read(self) -> None:
        events = [_labeled("user", "claude", is_handoff=True) for _ in range(3)]
        events += [_labeled("user", "claude") for _ in range(3)]
        anomalies = detect([("alpha", events)])
        dense = [a for a in anomalies if a.kind == AnomalyKind.HANDOFF_DENSE]
        assert len(dense[0].events) == 3  # the 3 handoff events
