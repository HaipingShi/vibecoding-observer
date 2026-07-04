"""Tests for the unified IR (IREvent / ToolCall).

Covers the IR contract: field set, round-trip serialization, required-field
validation, and fixture loading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observer.ir import IREvent, ToolCall

# --------------------------------------------------------------------------- #
# ToolCall
# --------------------------------------------------------------------------- #


class TestToolCall:
    def test_minimal_construction(self) -> None:
        tc = ToolCall(name="Bash")
        assert tc.name == "Bash"
        assert tc.input == {}
        assert tc.result_ok is None

    def test_full_round_trip(self) -> None:
        tc = ToolCall(name="Edit", input={"file_path": "x.py"}, result_ok=True)
        assert ToolCall.from_dict(tc.to_dict()) == tc

    def test_from_dict_tolerates_missing_optionals(self) -> None:
        tc = ToolCall.from_dict({"name": "Read"})
        assert tc.input == {}
        assert tc.result_ok is None


# --------------------------------------------------------------------------- #
# IREvent construction & defaults
# --------------------------------------------------------------------------- #


def _make_event(**overrides: object) -> IREvent:
    base: dict[str, object] = {
        "ts": "2026-06-28T13:00:00Z",
        "source_agent": "claude",
        "cwd": "/Users/example/projects/example",
        "project": "example",
        "role": "user",
    }
    base.update(overrides)
    return IREvent.from_dict(base)  # type: ignore[arg-type]


class TestIREventConstruction:
    def test_required_fields_present(self) -> None:
        ev = _make_event()
        assert ev.ts == "2026-06-28T13:00:00Z"
        assert ev.source_agent == "claude"
        assert ev.role == "user"

    def test_defaults_for_optional_fields(self) -> None:
        ev = _make_event()
        assert ev.text == ""
        assert ev.tool_calls == ()
        assert ev.parent is None
        assert ev.children == ()
        assert ev.is_handoff is False

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValueError, match="missing"):
            IREvent.from_dict({"ts": "x", "source_agent": "claude"})  # no role

    def test_project_derived_from_cwd_when_absent(self) -> None:
        ev = IREvent.from_dict(
            {
                "ts": "2026-06-28T13:00:00Z",
                "source_agent": "codex",
                "cwd": "/Users/example/projects/myproj",
                "role": "user",
            }
        )
        assert ev.project == "myproj"

    def test_frozen_is_immutable(self) -> None:
        ev = _make_event()
        with pytest.raises((AttributeError, TypeError)):
            ev.text = "mutated"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Round-trip serialization
# --------------------------------------------------------------------------- #


class TestRoundTrip:
    def test_event_without_tool_calls(self) -> None:
        ev = _make_event(text="hello")
        assert IREvent.from_dict(ev.to_dict()) == ev

    def test_event_with_tool_calls(self) -> None:
        ev = _make_event(
            role="assistant",
            tool_calls=(
                ToolCall(name="Bash", input={"command": "ls"}, result_ok=True),
                ToolCall(name="Read", input={"file_path": "a.py"}, result_ok=None),
            ),
        )
        restored = IREvent.from_dict(ev.to_dict())
        assert restored == ev
        assert len(restored.tool_calls) == 2
        assert restored.tool_calls[0].result_ok is True

    def test_event_with_tree_links_and_handoff(self) -> None:
        ev = _make_event(
            parent="ev-001",
            children=("ev-003", "ev-004"),
            is_handoff=True,
        )
        restored = IREvent.from_dict(ev.to_dict())
        assert restored.parent == "ev-001"
        assert restored.children == ("ev-003", "ev-004")
        assert restored.is_handoff is True

    def test_to_dict_is_json_serializable(self) -> None:
        ev = _make_event(
            tool_calls=(ToolCall(name="Bash", result_ok=False),),
        )
        # Must not raise.
        s = json.dumps(ev.to_dict())
        assert json.loads(s)["tool_calls"][0]["result_ok"] is False


# --------------------------------------------------------------------------- #
# Fixture loading
# --------------------------------------------------------------------------- #


class TestFixture:
    def test_ir_sample_loads_and_validates(self, fixtures_dir: Path) -> None:
        raw = json.loads((fixtures_dir / "ir_sample.json").read_text())
        events = [IREvent.from_dict(d) for d in raw]
        assert len(events) == 4

        # Multi-source present.
        agents = {ev.source_agent for ev in events}
        assert agents == {"claude", "codex"}

        # The handoff event is flagged.
        handoffs = [ev for ev in events if ev.is_handoff]
        assert len(handoffs) == 1
        assert handoffs[0].source_agent == "codex"

        # A failed tool call is captured (drives degen-stops-at-works).
        failed = [
            ev for ev in events if any(tc.result_ok is False for tc in ev.tool_calls)
        ]
        assert len(failed) == 1

    def test_fixture_round_trips(self, fixtures_dir: Path) -> None:
        raw = json.loads((fixtures_dir / "ir_sample.json").read_text())
        events = [IREvent.from_dict(d) for d in raw]
        # to_dict -> from_dict must be lossless for every fixture event.
        for ev in events:
            assert IREvent.from_dict(ev.to_dict()) == ev
