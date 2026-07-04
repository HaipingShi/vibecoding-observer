"""Tests for the Federator (multi-source fusion + handoff detection).

Covers the federation acceptance contract:
  - merges multi-source IR into project-level timelines
  - sorts by timestamp
  - detects cross-agent handoff within the gap window
  - does NOT flag handoff when the gap exceeds the window
  - single-source, multi-source, and handoff scenarios
"""

from __future__ import annotations

import json
from pathlib import Path

from observer.federator import Federator, federate
from observer.ir import IREvent

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _load_fixture(fixtures_dir: Path, name: str) -> list[IREvent]:
    raw = json.loads((fixtures_dir / name).read_text())
    return [IREvent.from_dict(d) for d in raw]


def _ev(
    ts: str,
    agent: str,
    project: str = "example",
    role: str = "user",
    text: str = "",
) -> IREvent:
    return IREvent(
        ts=ts,
        source_agent=agent,  # type: ignore[arg-type]
        cwd=f"/Users/example/projects/{project}",
        project=project,
        role=role,  # type: ignore[arg-type]
        text=text,
    )


# --------------------------------------------------------------------------- #
# Sorting & grouping
# --------------------------------------------------------------------------- #


class TestSortingGrouping:
    def test_events_sorted_by_timestamp(self) -> None:
        events = [
            _ev("2026-06-28T14:00:00Z", "claude"),
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-28T13:30:00Z", "claude"),
        ]
        result = federate(events)
        assert len(result) == 1
        ts_order = [ev.ts for ev in result[0].events]
        assert ts_order == sorted(ts_order, key=str)

    def test_out_of_order_input_corrected(self) -> None:
        events = [
            _ev("2026-06-28T13:30:00Z", "claude", text="mid"),
            _ev("2026-06-28T13:00:00Z", "claude", text="first"),
        ]
        result = federate(events)
        assert result[0].events[0].text == "first"
        assert result[0].events[1].text == "mid"

    def test_multiple_projects_separated(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude", project="alpha"),
            _ev("2026-06-28T13:00:00Z", "claude", project="beta"),
        ]
        result = federate(events)
        assert {p.project for p in result} == {"alpha", "beta"}
        assert len(result[0].events) == 1

    def test_projects_sorted_by_name(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude", project="zeta"),
            _ev("2026-06-28T13:00:00Z", "claude", project="alpha"),
        ]
        result = federate(events)
        assert [p.project for p in result] == ["alpha", "zeta"]

    def test_cwd_captured_from_first_event(self) -> None:
        events = [_ev("2026-06-28T13:00:00Z", "claude", project="example")]
        result = federate(events)
        assert result[0].cwd == "/Users/example/projects/example"


# --------------------------------------------------------------------------- #
# Handoff detection
# --------------------------------------------------------------------------- #


class TestHandoff:
    def test_cross_agent_within_gap_flagged(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-28T14:00:00Z", "codex", text="switch"),
        ]
        result = federate(events)
        handoffs = [ev for ev in result[0].events if ev.is_handoff]
        assert len(handoffs) == 1
        assert handoffs[0].source_agent == "codex"
        assert handoffs[0].text == "switch"

    def test_same_agent_no_handoff(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-28T14:00:00Z", "claude"),
        ]
        result = federate(events)
        assert result[0].handoff_count == 0

    def test_gap_too_large_no_handoff(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-29T20:00:00Z", "codex"),  # >4h gap
        ]
        result = federate(events)
        assert result[0].handoff_count == 0

    def test_handoff_flagged_on_new_agent_first_event(self) -> None:
        # The handoff marks the FIRST event of the new agent run, not the
        # last event of the old agent.
        events = [
            _ev("2026-06-28T13:00:00Z", "claude", role="user", text="c1"),
            _ev("2026-06-28T13:05:00Z", "claude", role="assistant", text="c2"),
            _ev("2026-06-28T14:00:00Z", "codex", role="user", text="x1"),
            _ev("2026-06-28T14:10:00Z", "codex", role="assistant", text="x2"),
        ]
        result = federate(events)
        handoffs = [ev for ev in result[0].events if ev.is_handoff]
        assert len(handoffs) == 1
        assert handoffs[0].text == "x1"

    def test_back_and_forth_multiple_handoffs(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-28T13:30:00Z", "codex"),
            _ev("2026-06-28T14:00:00Z", "claude"),
        ]
        result = federate(events)
        assert result[0].handoff_count == 2

    def test_custom_gap_threshold(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-28T13:05:00Z", "codex"),  # 5 min gap
        ]
        # Threshold of 60s: 5 min exceeds it → no handoff.
        result = federate(events, handoff_max_gap_seconds=60)
        assert result[0].handoff_count == 0


# --------------------------------------------------------------------------- #
# Immutability
# --------------------------------------------------------------------------- #


class TestImmutability:
    def test_original_events_not_mutated(self) -> None:
        events = [
            _ev("2026-06-28T13:00:00Z", "claude"),
            _ev("2026-06-28T14:00:00Z", "codex"),
        ]
        # Snapshot originals.
        original_flags = [ev.is_handoff for ev in events]
        federate(events)
        # Inputs unchanged.
        assert [ev.is_handoff for ev in events] == original_flags


# --------------------------------------------------------------------------- #
# Fixture-based integration
# --------------------------------------------------------------------------- #


class TestFixtures:
    def test_multi_fixture(self, fixtures_dir: Path) -> None:
        events = _load_fixture(fixtures_dir, "federator_multi.json")
        result = federate(events)
        assert len(result) == 1
        assert len(result[0].events) == 4
        # Claude run (2 events) then Codex run (2 events).
        agents = [ev.source_agent for ev in result[0].events]
        assert agents == ["claude", "claude", "codex", "codex"]
        # One handoff at the codex boundary.
        assert result[0].handoff_count == 1

    def test_handoff_fixture_no_false_positive(self, fixtures_dir: Path) -> None:
        events = _load_fixture(fixtures_dir, "federator_handoff.json")
        result = federate(events)
        assert result[0].handoff_count == 0


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


class TestEdgeCases:
    def test_empty_input(self) -> None:
        assert federate([]) == []

    def test_single_event(self) -> None:
        result = federate([_ev("2026-06-28T13:00:00Z", "claude")])
        assert len(result) == 1
        assert result[0].handoff_count == 0

    def test_unparseable_timestamp_kept_in_place(self) -> None:
        # Stable sort: an unparseable ts keeps insertion order, doesn't crash.
        events = [
            IREvent(
                ts="not-a-date",
                source_agent="claude",
                cwd="/p/x",
                project="x",
                role="user",
            ),
            _ev("2026-06-28T13:00:00Z", "claude", project="x"),
        ]
        result = federate(events)
        assert len(result[0].events) == 2

    def test_federator_class_configurable(self) -> None:
        fed = Federator(handoff_max_gap_seconds=1)
        assert fed.handoff_max_gap_seconds == 1
