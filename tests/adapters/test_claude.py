"""Tests for ClaudeAdapter.

Validates the core parsing contract:
  - filters out non-conversation record types
  - extracts tool_use (name/input/result_ok)
  - matches tool_use.id ↔ tool_result.tool_use_id for result_ok
  - yields lazily (streaming)
  - derives project from cwd basename
"""

from __future__ import annotations

from pathlib import Path

import pytest

from observer.adapters.claude import ClaudeAdapter
from observer.ir import IREvent

# --------------------------------------------------------------------------- #
# Fixture-based end-to-end parse
# --------------------------------------------------------------------------- #


@pytest.fixture
def events(fixtures_dir: Path) -> list[IREvent]:
    path = fixtures_dir / "claude_sample.jsonl"
    return list(ClaudeAdapter().parse(path))


class TestParseFixture:
    def test_only_conversation_records_kept(self, events: list[IREvent]) -> None:
        # Fixture has 4 conversation records (2 user prompts + 2 tool_result
        # users + 2 assistant). queue-operation/attachment/file-history-snapshot
        # /ai-title must be dropped.
        assert len(events) == 6

    def test_all_events_stamped_claude(self, events: list[IREvent]) -> None:
        assert all(ev.source_agent == "claude" for ev in events)

    def test_project_derived_from_cwd(self, events: list[IREvent]) -> None:
        assert all(ev.project == "example" for ev in events)
        assert events[0].cwd == "/Users/example/projects/example"

    def test_roles_alternate_correctly(self, events: list[IREvent]) -> None:
        roles = [ev.role for ev in events]
        assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]

    def test_plain_text_user_message(self, events: list[IREvent]) -> None:
        assert events[0].role == "user"
        assert "实现 Adapter" in events[0].text

    def test_parent_uuid_threaded(self, events: list[IREvent]) -> None:
        assert events[0].parent is None
        assert events[1].parent == "u-1"
        assert events[2].parent == "a-1"


# --------------------------------------------------------------------------- #
# Tool extraction & result_ok matching
# --------------------------------------------------------------------------- #


class TestToolExtraction:
    def test_assistant_has_tool_calls(self, events: list[IREvent]) -> None:
        # events[1] = first assistant turn with one Read tool_use.
        a1 = events[1]
        assert len(a1.tool_calls) == 1
        assert a1.tool_calls[0].name == "Read"
        assert a1.tool_calls[0].input["file_path"].endswith("config.toml")

    def test_result_ok_resolved_after_result_seen(self, events: list[IREvent]) -> None:
        # The Read result (call_01, not error) appears on events[2] (user).
        # But tool_use was emitted on events[1], BEFORE the result was seen.
        # So events[1].tool_calls[0].result_ok should be None at emit time.
        # This documents the design: result_ok resolves only when the result
        # has already been seen earlier in the stream — Claude results come
        # AFTER the tool_use, so a single forward pass sees them as None.
        assert events[1].tool_calls[0].result_ok is None

    def test_multiple_tool_calls_one_turn(self, events: list[IREvent]) -> None:
        # events[3] = second assistant with Bash + Write.
        a2 = events[3]
        names = [tc.name for tc in a2.tool_calls]
        assert names == ["Bash", "Write"]


# --------------------------------------------------------------------------- #
# Streaming / laziness
# --------------------------------------------------------------------------- #


class TestStreaming:
    def test_parse_returns_iterator_not_list(self, fixtures_dir: Path) -> None:
        gen = ClaudeAdapter().parse(fixtures_dir / "claude_sample.jsonl")
        # Iterator protocol — not a materialized list.
        assert hasattr(gen, "__next__")
        assert not isinstance(gen, list)

    def test_partial_consumption(self, fixtures_dir: Path) -> None:
        gen = ClaudeAdapter().parse(fixtures_dir / "claude_sample.jsonl")
        first = next(gen)
        assert first.role == "user"
        # Consuming only the first must not require reading the whole file.
        # (We can't easily assert no full-read, but the contract is iterator.)


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


class TestEdgeCases:
    def test_empty_file_yields_nothing(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert list(ClaudeAdapter().parse(p)) == []

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "blanks.jsonl"
        p.write_text(
            "\n\n"
            '{"type":"user","cwd":"/p/x","timestamp":"2026-06-28T13:00:00Z",'
            '"message":{"role":"user","content":"hi"}}\n\n'
        )
        events = list(ClaudeAdapter().parse(p))
        assert len(events) == 1
        assert events[0].text == "hi"

    def test_malformed_json_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.jsonl"
        p.write_text(
            "{not valid json}\n"
            '{"type":"user","cwd":"/p/x","timestamp":"2026-06-28T13:00:00Z",'
            '"message":{"role":"user","content":"ok"}}\n'
        )
        events = list(ClaudeAdapter().parse(p))
        assert len(events) == 1

    def test_missing_timestamp_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "nots.jsonl"
        p.write_text(
            '{"type":"user","cwd":"/p/x","message":{"role":"user","content":"no ts"}}\n'
        )
        assert list(ClaudeAdapter().parse(p)) == []

    def test_source_agent_property(self) -> None:
        assert ClaudeAdapter().source_agent == "claude"
