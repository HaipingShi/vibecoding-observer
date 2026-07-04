"""CodexAdapter — parse Codex session jsonl into IREvent stream.

Codex stores sessions as ``.jsonl`` with four record types:

  - ``session_meta``    — one per file; carries ``payload.cwd`` (the project)
  - ``turn_context``    — per-turn context; also carries cwd (redundant)
  - ``event_msg``       — lifecycle events (task_started, etc.); skipped
  - ``response_item``   — the conversation; this is what we parse

Within ``response_item``, the relevant ``payload.type`` values:

  - ``message`` (role=user|assistant|developer)
      * developer = system instructions (permissions/env) → filtered out
      * user may contain ``<environment_context>`` injection → filtered
      * assistant = the model's visible text → kept
  - ``reasoning``       — encrypted CoT; skipped
  - ``function_call``   — tool invocation: name, arguments(JSON str), call_id
  - ``function_call_output`` — tool result: call_id, output(text)

Tool result_ok is inferred from the output text: Codex prints
``Process exited with code N``. Code != 0 ⇒ failure. If the marker is
absent (e.g. non-shell tools), result_ok stays None — never guessed.

Streaming: file read line-by-line. A single Codex file can be 187 MB.
This satisfies the "large files must be parsed lazily" Invariant.

cwd resolution: we capture cwd from session_meta (or turn_context) as it
appears, since message records themselves don't carry cwd.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

from observer.adapters.base import Adapter
from observer.ir import IREvent, ToolCall

__all__ = ["CodexAdapter"]

# Marker Codex prints for shell command results: "Process exited with code N".
_EXIT_CODE_RE = re.compile(r"Process exited with code (\d+)")

# Roles we keep as conversation. "developer" is injected system context.
_KEEP_ROLES: frozenset[str] = frozenset({"user", "assistant"})

# User messages injected by Codex itself (not typed by the human). These
# wrap environment/shell context and would pollute the interaction analysis.
_INJECTED_PREFIXES: tuple[str, ...] = (
    "<environment_context>",
    "<permissions_instructions>",
)


class CodexAdapter(Adapter):
    """Parse Codex ``.jsonl`` session files into IREvent stream."""

    @property
    def source_agent(self) -> str:
        return "codex"

    def parse(self, jsonl_path: str | Path) -> Iterator[IREvent]:
        """Yield IREvents from a Codex session jsonl, lazily."""
        path = Path(jsonl_path)

        # cwd captured from session_meta / turn_context; message records
        # don't carry it, so we hold the latest known value.
        cwd = ""
        # call_id -> exit code (int), accumulated from function_call_output
        # so a function_call emitted earlier can resolve result_ok. In
        # Codex the output follows the call, so a single forward pass sees
        # calls before their outputs — result_ok resolves to None at emit
        # time (same limitation as the Claude adapter; documented).
        call_exits: dict[str, int] = {}

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
                ts = record.get("timestamp")
                if not isinstance(ts, str):
                    continue

                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue

                # Update cwd from meta records whenever seen.
                cwd_now = _extract_cwd(rec_type, payload)
                if cwd_now:
                    cwd = cwd_now

                if rec_type != "response_item":
                    # event_msg / turn_context / session_meta: only cwd matters.
                    continue

                yield from self._emit_response_item(
                    payload, ts, cwd, call_exits
                )

    def _emit_response_item(
        self,
        payload: dict[str, object],
        ts: str,
        cwd: str,
        call_exits: dict[str, int],
    ) -> Iterator[IREvent]:
        """Build zero or one IREvent from a response_item payload."""
        ptype = payload.get("type")

        if ptype == "function_call":
            # Record the call so its output (seen later) can match back.
            # We do NOT emit a separate event for the bare call; instead the
            # assistant message that triggered it carries the tool_calls.
            # But Codex separates function_call from the assistant message,
            # so we emit the call as its own assistant event to preserve
            # the tool-invocation signal for downstream analysis.
            tc = self._make_tool_call(payload, call_exits)
            if tc is not None:
                yield IREvent(
                    ts=ts,
                    source_agent="codex",
                    cwd=cwd,
                    project=_project_of(cwd),
                    role="assistant",
                    text="",
                    tool_calls=(tc,),
                    is_handoff=False,
                )
            return

        if ptype == "function_call_output":
            # Stash exit code for the matching call_id, then emit a user
            # turn carrying the output text (it's part of the conversation).
            call_id = payload.get("call_id")
            output = payload.get("output")
            if isinstance(call_id, str) and isinstance(output, str):
                m = _EXIT_CODE_RE.search(output)
                if m:
                    call_exits[call_id] = int(m.group(1))
            if isinstance(output, str) and output.strip():
                yield IREvent(
                    ts=ts,
                    source_agent="codex",
                    cwd=cwd,
                    project=_project_of(cwd),
                    role="user",
                    text=output.strip(),
                    tool_calls=(),
                    is_handoff=False,
                )
            return

        if ptype == "message":
            role = payload.get("role")
            if role not in _KEEP_ROLES:
                return  # developer = system, skip
            text = _extract_message_text(payload)
            if text is None:
                return  # injected context or empty
            yield IREvent(
                ts=ts,
                source_agent="codex",
                cwd=cwd,
                project=_project_of(cwd),
                role=role,  # type: ignore[arg-type]
                text=text,
                tool_calls=(),
                is_handoff=False,
            )
            return

        # reasoning / other types: skip.

    @staticmethod
    def _make_tool_call(
        payload: dict[str, object],
        call_exits: dict[str, int],
    ) -> ToolCall | None:
        name = payload.get("name")
        if not isinstance(name, str):
            return None
        raw_args = payload.get("arguments")
        inp: dict[str, object]
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                inp = parsed if isinstance(parsed, dict) else {"_raw": parsed}
            except json.JSONDecodeError:
                inp = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            inp = raw_args
        else:
            inp = {}
        call_id = payload.get("call_id")
        result_ok: bool | None = None
        if isinstance(call_id, str) and call_id in call_exits:
            result_ok = call_exits[call_id] == 0
        return ToolCall(name=name, input=inp, result_ok=result_ok)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _extract_cwd(rec_type: object, payload: dict[str, object]) -> str:
    """Pull cwd from session_meta or turn_context payloads."""
    if rec_type in ("session_meta", "turn_context"):
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd:
            return cwd
    return ""


def _project_of(cwd: str) -> str:
    return cwd.rstrip("/").rsplit("/", 1)[-1] if cwd else ""


def _extract_message_text(payload: dict[str, object]) -> str | None:
    """Extract human-visible text from a message payload.

    Returns None if the message is injected system context (filtered)
    or has no usable text.
    """
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        text_val = block.get("text")
        if not isinstance(text_val, str):
            continue
        if btype in ("input_text", "output_text"):
            stripped = text_val.strip()
            # Filter Codex-injected environment/permission context.
            if stripped.startswith(_INJECTED_PREFIXES):
                continue
            if stripped:
                parts.append(stripped)
    return "\n".join(parts) if parts else None
