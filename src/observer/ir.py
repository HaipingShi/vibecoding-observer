"""Unified Intermediate Representation (IR) for observer.

The IR is the single contract between data-source adapters (Claude/Codex/ZCode)
and every downstream component (Federator, Extractor, Aggregator, ...).
Adapters convert heterogeneous jsonl into ``IREvent`` objects; nothing upstream
ever touches raw jsonl again. This is the portability and multi-source fusion
pivot.

Field set is the minimal event contract:

    ts, source_agent, cwd, project, role, text,
    tool_calls, parent, children, is_handoff
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "IREvent",
    "Role",
    "SourceAgent",
    "ToolCall",
]

SourceAgent = Literal["claude", "codex", "zcode"]
"""Closed enumeration of supported agent sources.

Adding a new agent = adding a literal here + writing an Adapter.
Keeps the IR self-documenting and gives static checkers something to verify.
"""

Role = Literal["user", "assistant"]
"""Role of the message author within a single turn."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation extracted from an assistant message.

    ``result_ok`` is mandatory: it drives ``degen-stops-at-works`` and
    ``tool-fail`` detection. Adapters that cannot determine success must set
    it to ``None`` rather than guessing.
    """

    name: str
    input: dict[str, Any] = field(default_factory=dict)
    result_ok: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "input": self.input, "result_ok": self.result_ok}

    @classmethod
    def from_dict(cls, data: ToolCall | dict[str, Any]) -> ToolCall:
        """Accept a dict or an already-constructed ToolCall (idempotent).

        Idempotency matters because ``IREvent.from_dict`` may receive
        tool_calls that downstream code pre-constructed; treating a live
        ToolCall as already-valid avoids a TypeError on re-parsing.
        """
        if isinstance(data, ToolCall):
            return data
        return cls(
            name=str(data["name"]),
            input=dict(data.get("input", {})),
            result_ok=data.get("result_ok"),
        )


@dataclass(frozen=True, slots=True)
class IREvent:
    """A single normalized interaction event.

    This is the atom of the entire analysis pipeline. A project's full
    interaction timeline is a sequence of ``IREvent`` ordered by ``ts``.

    Design choices:
      - ``frozen=True``: events are immutable once created. Downstream
        passes them around; mutation would corrupt the audit trail.
      - ``slots=True``: memory-tight; the pipeline processes millions of
        these across hundreds of sessions.
      - ``ts`` is an ISO-8601 string, not ``datetime``: JSON has no native
        datetime type, and keeping the wire format stable means from/to
        round-trips are trivially lossless. Parsing to datetime happens at
        the point of use (Federator sorting).
      - ``is_handoff`` defaults False; set True by the Federator when a
        cross-agent handoff is detected at this event.
    """

    ts: str
    source_agent: SourceAgent
    cwd: str
    project: str
    role: Role
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    parent: str | None = None
    children: tuple[str, ...] = ()
    is_handoff: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict.

        Round-trip guarantee: ``IREvent.from_dict(e.to_dict()) == e``.
        Tuples become lists on the wire (JSON has no tuple); ``from_dict``
        converts them back.
        """
        return {
            "ts": self.ts,
            "source_agent": self.source_agent,
            "cwd": self.cwd,
            "project": self.project,
            "role": self.role,
            "text": self.text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "parent": self.parent,
            "children": list(self.children),
            "is_handoff": self.is_handoff,
        }

    def with_handoff(self, is_handoff: bool = True) -> IREvent:
        """Return a copy with ``is_handoff`` set.

        IREvent is frozen, so the Federator marks handoff points by
        producing a new event rather than mutating. This is the only
        field downstream legitimately rewrites.
        """
        return IREvent(
            ts=self.ts,
            source_agent=self.source_agent,
            cwd=self.cwd,
            project=self.project,
            role=self.role,
            text=self.text,
            tool_calls=self.tool_calls,
            parent=self.parent,
            children=self.children,
            is_handoff=is_handoff,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IREvent:
        """Construct from a dict (e.g. loaded from JSON fixture).

        Tolerant of missing optional fields so partial fixtures still work,
        but the three identity fields (ts/source_agent/role) are required —
        an event without them is meaningless.
        """
        required = ("ts", "source_agent", "role")
        missing = [k for k in required if k not in data]
        if missing:
            msg = f"IREvent requires fields {required}; missing: {missing}"
            raise ValueError(msg)

        cwd = str(data.get("cwd", ""))
        project = str(data.get("project", ""))
        if not project and cwd:
            # Derive project from cwd basename as a convenience default.
            project = cwd.rstrip("/").rsplit("/", 1)[-1]

        return cls(
            ts=str(data["ts"]),
            source_agent=data["source_agent"],  # type: ignore[arg-type]
            cwd=cwd,
            project=project,
            role=data["role"],  # type: ignore[arg-type]
            text=str(data.get("text", "")),
            tool_calls=tuple(ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])),
            parent=data.get("parent"),
            children=tuple(data.get("children", [])),
            is_handoff=bool(data.get("is_handoff", False)),
        )
