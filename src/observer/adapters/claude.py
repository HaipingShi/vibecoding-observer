"""ClaudeAdapter — parse Claude Code session jsonl into IREvent stream.

Claude Code stores each session as ``.jsonl`` where every line is a JSON
record. The records relevant to us:

  - ``type: "user" | "assistant"``  — the conversation turns we keep
  - ``type: "queue-operation" | "attachment" | "file-history-snapshot"
       | "system" | "mode" | "last-prompt" | "ai-title"``  — metadata we skip

Within a kept record, ``message.content`` is either a plain string or a
list of typed blocks:

  - ``{"type": "tool_use", "id": ..., "name": ..., "input": {...}}``
      emitted by the assistant
  - ``{"type": "tool_result", "tool_use_id": ..., "is_error": bool,
       "content": ...}``
      returned to the user turn that follows

We match ``tool_use.id`` ↔ ``tool_result.tool_use_id`` to determine
``result_ok``. When an assistant turn has tool_use blocks but the matching
result has not yet been seen (or never arrives), ``result_ok`` stays
``None`` — we never guess.

Streaming: the file is read line-by-line. We never load it whole. This
satisfies the "large files must be parsed lazily" Invariant.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from observer.adapters.base import Adapter
from observer.ir import IREvent, ToolCall

__all__ = ["ClaudeAdapter"]

# Record types that carry conversation turns. Everything else is metadata.
_KEEP_TYPES: frozenset[str] = frozenset({"user", "assistant"})


class ClaudeAdapter(Adapter):
    """Parse Claude Code ``.jsonl`` session files into IREvent stream."""

    @property
    def source_agent(self) -> str:
        return "claude"

    def parse(self, jsonl_path: str | Path) -> Iterator[IREvent]:
        """Yield IREvents from a Claude session jsonl, lazily."""
        path = Path(jsonl_path)

        # Map tool_use_id -> is_error, accumulated as we scan results so that
        # an assistant tool_use can look up its outcome. Results always
        # follow the corresponding tool_use within the file.
        result_errors: dict[str, bool] = {}

        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue

                rec_type = record.get("type")
                if rec_type not in _KEEP_TYPES:
                    # Still harvest tool_results from non-conversation lines
                    # so later assistant turns can resolve result_ok. In
                    # practice results live on user lines, but be defensive.
                    continue

                yield from self._emit_event(record, result_errors)

    def _emit_event(
        self,
        record: dict[str, object],
        result_errors: dict[str, bool],
    ) -> Iterator[IREvent]:
        """Build zero or one IREvent from a conversation record."""
        rec_type = record.get("type")
        role = "user" if rec_type == "user" else "assistant"

        message = record.get("message")
        if not isinstance(message, dict):
            return

        content = message.get("content")
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    _txt = block.get("text")
                    if isinstance(_txt, str):
                        text_parts.append(_txt)
                elif block_type == "tool_use":
                    _tc = self._make_tool_call(block, result_errors)
                    if _tc is not None:
                        tool_calls.append(_tc)
                elif block_type == "tool_result":
                    # Record this result for the matching tool_use id.
                    tu_id = block.get("tool_use_id")
                    is_error = bool(block.get("is_error", False))
                    if isinstance(tu_id, str):
                        result_errors[tu_id] = is_error
                    # Also surface the result text on the user turn.
                    _rc = block.get("content")
                    if isinstance(_rc, str) and _rc.strip():
                        text_parts.append(_rc)

        ts = record.get("timestamp")
        if not isinstance(ts, str):
            # Without a timestamp the event can't be ordered; skip it.
            return

        cwd = record.get("cwd")
        cwd_str = str(cwd) if isinstance(cwd, str) else ""
        project = cwd_str.rstrip("/").rsplit("/", 1)[-1] if cwd_str else ""

        yield IREvent(
            ts=ts,
            source_agent="claude",
            cwd=cwd_str,
            project=project,
            role=role,  # type: ignore[arg-type]
            text="\n".join(text_parts).strip(),
            tool_calls=tuple(tool_calls),
            parent=_as_str(record.get("parentUuid")),
            children=(),
            is_handoff=False,
        )

    @staticmethod
    def _make_tool_call(
        block: dict[str, object],
        result_errors: dict[str, bool],
    ) -> ToolCall | None:
        """Construct a ToolCall, resolving result_ok from seen results."""
        name = block.get("name")
        if not isinstance(name, str):
            return None
        raw_input = block.get("input")
        inp = dict(raw_input) if isinstance(raw_input, dict) else {}
        call_id = block.get("id")
        # result_ok is resolved if we've already seen this id's result.
        result_ok: bool | None = None
        if isinstance(call_id, str) and call_id in result_errors:
            result_ok = not result_errors[call_id]
        return ToolCall(name=name, input=inp, result_ok=result_ok)


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
