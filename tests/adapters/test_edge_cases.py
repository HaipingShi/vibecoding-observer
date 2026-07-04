"""Edge case tests for adapter robustness and base.py parse_many.

Focuses on coverage gaps identified by pytest --cov:
- base.py parse_many chaining
- codex.py malformed payloads, missing fields, empty sessions
- claude.py content type variants (string vs list, mixed blocks)
"""

from __future__ import annotations

import json
from pathlib import Path

from observer.adapters.claude import ClaudeAdapter
from observer.adapters.codex import CodexAdapter

# --------------------------------------------------------------------------- #
# base.py parse_many
# --------------------------------------------------------------------------- #


class TestParseMany:
    def test_chains_multiple_files(self, tmp_path: Path) -> None:
        """parse_many chains events from multiple jsonl files."""
        f1 = tmp_path / "s1.jsonl"
        f2 = tmp_path / "s2.jsonl"
        for f in (f1, f2):
            f.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "cwd": "/p/test",
                        "timestamp": "2026-06-28T13:00:00Z",
                        "message": {"role": "user", "content": "hello"},
                    }
                )
                + "\n"
            )
        adapter = ClaudeAdapter()
        events = list(adapter.parse_many([f1, f2]))
        assert len(events) == 2


# --------------------------------------------------------------------------- #
# Claude adapter edge cases
# --------------------------------------------------------------------------- #


class TestClaudeEdgeCases:
    def test_string_content(self, tmp_path: Path) -> None:
        """message.content as a plain string (not a list of blocks)."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            json.dumps(
                {
                    "type": "user",
                    "cwd": "/p/test",
                    "timestamp": "2026-06-28T13:00:00Z",
                    "message": {"role": "user", "content": "plain string message"},
                }
            )
            + "\n"
        )
        events = list(ClaudeAdapter().parse(f))
        assert len(events) == 1
        assert events[0].text == "plain string message"

    def test_non_dict_message_skipped(self, tmp_path: Path) -> None:
        """Records with non-dict message are skipped gracefully."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            json.dumps(
                {
                    "type": "user",
                    "cwd": "/p/test",
                    "timestamp": "2026-06-28T13:00:00Z",
                    "message": "not a dict",
                }
            )
            + "\n"
        )
        assert list(ClaudeAdapter().parse(f)) == []

    def test_tool_use_without_id(self, tmp_path: Path) -> None:
        """tool_use block without id doesn't crash, result_ok stays None."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "cwd": "/p/test",
                    "timestamp": "2026-06-28T13:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "name": "Bash", "input": {}}
                            # no "id" field
                        ],
                    },
                }
            )
            + "\n"
        )
        events = list(ClaudeAdapter().parse(f))
        assert len(events) == 1
        assert len(events[0].tool_calls) == 1
        assert events[0].tool_calls[0].result_ok is None

    def test_tool_use_without_name_skipped(self, tmp_path: Path) -> None:
        """tool_use block without name is silently dropped."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "cwd": "/p/test",
                    "timestamp": "2026-06-28T13:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "input": {}}  # no name
                        ],
                    },
                }
            )
            + "\n"
        )
        events = list(ClaudeAdapter().parse(f))
        assert len(events[0].tool_calls) == 0


# --------------------------------------------------------------------------- #
# Codex adapter edge cases
# --------------------------------------------------------------------------- #


class TestCodexEdgeCases:
    def test_non_dict_payload_skipped(self, tmp_path: Path) -> None:
        """response_item with non-dict payload is skipped."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item","payload":"not a dict"}\n'
        )
        assert list(CodexAdapter().parse(f)) == []

    def test_message_with_empty_content_skipped(self, tmp_path: Path) -> None:
        """message with empty content list produces no text → skipped."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"message","role":"user","content":[]}}\n'
        )
        assert list(CodexAdapter().parse(f)) == []

    def test_function_call_with_non_string_arguments(self, tmp_path: Path) -> None:
        """function_call with non-string/non-dict arguments doesn't crash."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"function_call","name":"exec",'
            '"arguments":123,"call_id":"c1"}}\n'
        )
        events = list(CodexAdapter().parse(f))
        assert len(events) == 1
        assert events[0].tool_calls[0].input == {}  # fallback to empty

    def test_function_call_without_name_skipped(self, tmp_path: Path) -> None:
        """function_call without name is dropped."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"function_call","arguments":"{}","call_id":"c1"}}\n'
        )
        events = list(CodexAdapter().parse(f))
        assert len(events) == 0

    def test_function_call_output_without_exit_code(self, tmp_path: Path) -> None:
        """function_call_output without 'Process exited' marker → result_ok stays None."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"function_call_output","call_id":"c1",'
            '"output":"some output without exit code marker"}}\n'
        )
        events = list(CodexAdapter().parse(f))
        # Should produce a user event with the output text.
        assert len(events) == 1
        assert events[0].role == "user"

    def test_function_call_output_non_string_output(self, tmp_path: Path) -> None:
        """function_call_output with non-string output doesn't crash."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"function_call_output","call_id":"c1",'
            '"output":{"not": "a string"}}}\n'
        )
        # Should not crash; non-string output just produces no event.
        events = list(CodexAdapter().parse(f))
        assert len(events) == 0

    def test_unknown_response_item_type_skipped(self, tmp_path: Path) -> None:
        """Unknown payload types are skipped silently."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"some_new_type","data":"stuff"}}\n'
        )
        assert list(CodexAdapter().parse(f)) == []

    def test_response_item_without_payload_skipped(self, tmp_path: Path) -> None:
        """response_item without payload dict is skipped."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item"}\n'
        )
        assert list(CodexAdapter().parse(f)) == []

    def test_reasoning_with_summary_content(self, tmp_path: Path) -> None:
        """reasoning records are skipped entirely."""
        f = tmp_path / "s.jsonl"
        f.write_text(
            '{"timestamp":"2026-05-15T12:00:00Z","type":"response_item",'
            '"payload":{"type":"reasoning","summary":["thinking..."],'
            '"encrypted_content":"abc123"}}\n'
        )
        assert list(CodexAdapter().parse(f)) == []
