"""Normalize raw agent events into engineering activity signals.

This layer deliberately separates generic engineering evidence from project
governance dialects. The episode analyzer consumes these normalized signals;
profiles only teach the normalizer where a team writes its loop evidence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from observer.ir import IREvent, ToolCall
from observer.message_classifier import MessageKind, classify_message

__all__ = [
    "CODE_RAIL_PROFILE",
    "DEFAULT_PROFILES",
    "GENERIC_PROFILE",
    "EventSignals",
    "SignalProfile",
    "compile_signal_patterns",
    "detect_event_signals",
]


_IMPLEMENT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "apply_patch"})
_CODE_EXT_RE = re.compile(
    r"\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|swift|c|cc|cpp|h|hpp|sql|sh|yml|yaml|toml|json)\b",
    re.IGNORECASE,
)
_FILE_WRITE_CMD_RE = re.compile(
    r"apply_patch|\*\*\* Begin Patch|"
    r"\b(?:cat|tee)\b[^;\n]*(?:>|>>)\s*[\w./-]+|"
    r"\b(?:sed|perl)\b[^;\n]*\s+-i\b|"
    r"\b(?:cp|mv|touch)\s+[\w./-]+|"
    r"write_text\(|Path\([^)]*\)\.write|open\([^)]*,\s*['\"]w",
    re.IGNORECASE | re.DOTALL,
)
_GIT_PERSIST_RE = re.compile(r"\bgit\s+(?:add|commit)\b", re.IGNORECASE)
_GIT_STATUS_CHANGE_RE = re.compile(
    r"Changes to be committed:|Changes not staged for commit:|"
    r"modified:|new file:|deleted:|Untracked files:",
    re.IGNORECASE,
)
_READ_ONLY_COMMAND_RE = re.compile(r"^\s*(?:cat|sed|rg|grep|find|head|tail|nl|ls|pwd)\b")


@dataclass(frozen=True, slots=True)
class SignalProfile:
    """A project-governance dialect for recognizing loop evidence."""

    name: str
    design_artifact_patterns: tuple[re.Pattern[str], ...] = ()
    verification_patterns: tuple[re.Pattern[str], ...] = ()
    governance_patterns: tuple[re.Pattern[str], ...] = ()
    persistence_patterns: tuple[re.Pattern[str], ...] = ()
    closure_patterns: tuple[re.Pattern[str], ...] = ()
    handoff_patterns: tuple[re.Pattern[str], ...] = ()
    ignore_patterns: tuple[re.Pattern[str], ...] = ()


@dataclass(frozen=True, slots=True)
class EventSignals:
    """Normalized engineering evidence extracted from one IR event."""

    code_edit: bool = False
    design_artifact: bool = False
    verification: bool = False
    governance: bool = False
    persistence: bool = False
    closure: bool = False
    handoff: bool = False
    matched_profiles: tuple[str, ...] = ()

    @property
    def implementation(self) -> bool:
        return self.code_edit or self.design_artifact or self.governance_persistence

    @property
    def governance_persistence(self) -> bool:
        return self.governance and self.persistence


def compile_signal_patterns(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in patterns)


GENERIC_PROFILE = SignalProfile(
    name="generic",
    design_artifact_patterns=compile_signal_patterns(
        r"(?:^|[\s'\"`])(?:docs/|README\.md|CHANGELOG\.md|"
        r"ADR|DECISIONS\.md|ARCHITECTURE\.md|HANDOFF\.md|TASKS\.md)"
    ),
    verification_patterns=compile_signal_patterns(
        r"pytest|ruff|mypy|pyright|uv build|npm test|pnpm test|cargo test|go test|git diff --check"
        r"|验证|测试|检查|check|verify|validate"
    ),
    governance_patterns=compile_signal_patterns(
        r"scope|forbidden|acceptance criteria|definition of done|checklist|验收|边界|禁止"
    ),
    persistence_patterns=compile_signal_patterns(r"\bgit\s+(?:add|commit)\b|PR opened|pull request|changelog"),
    closure_patterns=compile_signal_patterns(
        r"完成|搞定|通过|已修复|已更新|已提交|done|finished|passed|all checks passed"
        r"|closeout|closed|committed|PR opened"
    ),
    handoff_patterns=compile_signal_patterns(
        r"\bblocked\b|blocker|rollback note|handoff|next step|resume anchor"
        r"|阻塞|等待确认|无法继续|下一步"
    ),
)


CODE_RAIL_PROFILE = SignalProfile(
    name="coderail",
    design_artifact_patterns=compile_signal_patterns(
        r"TASKS\.md|DECISIONS\.md|HANDOFF\.md|TRACELOG\.jsonl|TRACE_INDEX\.md"
    ),
    verification_patterns=compile_signal_patterns(r"done_gate\.py|trace_index\.py|harness-result\s+passed"),
    governance_patterns=compile_signal_patterns(
        r"CodeRail|G[-/ ]T[-/ ]S[-/ ]V[-/ ]X[-/ ]P|Coordinate|done_gate\.py|"
        r"trace_event\.py|trace_index\.py|inspect_state\.py|TASKS\.md|"
        r"DECISIONS\.md|HANDOFF\.md|TRACELOG\.jsonl|TRACE_INDEX\.md"
    ),
    persistence_patterns=compile_signal_patterns(
        r"trace_event\.py|trace_index\.py|\bgit\s+commit\b"
    ),
    closure_patterns=compile_signal_patterns(
        r"done gate[:：]?\s*(?:pass|passed)|done_gate\.py.*(?:pass|passed)|"
        r"trace_event\.py[^\n]*(?:--kind\s+verify|verify)|"
        r"(?:task|T-\d+)[^\n]*(?:marked\s+)?(?:done|closed|completed)|"
        r"\bgit\s+commit\b|closeout"
    ),
    handoff_patterns=compile_signal_patterns(r"HANDOFF\.md|handoff|resume anchor|H[0-3]\b"),
)

DEFAULT_PROFILES = (GENERIC_PROFILE,)


def detect_event_signals(
    event: IREvent,
    profiles: Iterable[SignalProfile] = DEFAULT_PROFILES,
) -> EventSignals:
    """Classify one event into normalized engineering signals."""
    tool_text = "\n".join(_tool_signal_text(tc) for tc in event.tool_calls)
    progress_text = event.text if _text_can_signal_progress(event) else ""
    all_text = "\n".join(part for part in (event.text, tool_text) if part)
    profile_list = tuple(profiles)

    code_edit = _has_code_edit(event, profile_list)
    design_artifact = _has_design_artifact(event, all_text, profile_list)
    verification = _matches_any(
        f"{progress_text}\n{tool_text}",
        (p.verification_patterns for p in profile_list),
    )
    governance = _matches_any(all_text, (p.governance_patterns for p in profile_list))
    persistence = bool(_GIT_PERSIST_RE.search(all_text)) or _profile_persistence(all_text, profile_list)
    closure = (
        _matches_any(
            f"{progress_text}\n{tool_text}",
            (p.closure_patterns for p in profile_list),
        )
        or persistence
    )
    handoff = _matches_any(all_text, (p.handoff_patterns for p in profile_list))

    matched_profiles = tuple(
        profile.name
        for profile in profile_list
        if any(
            _matches_any(all_text, (patterns,))
            for patterns in (
                profile.design_artifact_patterns,
                profile.verification_patterns,
                profile.governance_patterns,
                profile.persistence_patterns,
                profile.closure_patterns,
                profile.handoff_patterns,
            )
        )
    )

    return EventSignals(
        code_edit=code_edit,
        design_artifact=design_artifact,
        verification=verification,
        governance=governance,
        persistence=persistence,
        closure=closure,
        handoff=handoff,
        matched_profiles=matched_profiles,
    )


def _has_code_edit(event: IREvent, profiles: tuple[SignalProfile, ...]) -> bool:
    for tc in event.tool_calls:
        if tc.name in _IMPLEMENT_TOOLS:
            fp = str(tc.input.get("file_path", ""))
            if fp and _is_ignored_path(fp, profiles):
                continue
            return not fp or not _is_design_path(fp, profiles)
        raw = _tool_signal_text(tc)
        if _is_ignored_path(raw, profiles):
            continue
        if _FILE_WRITE_CMD_RE.search(raw) and (
            "apply_patch" in raw or "*** Begin Patch" in raw or _CODE_EXT_RE.search(raw)
        ):
            return True
    return False


def _has_design_artifact(
    event: IREvent,
    all_text: str,
    profiles: tuple[SignalProfile, ...],
) -> bool:
    for tc in event.tool_calls:
        if tc.name in _IMPLEMENT_TOOLS:
            fp = str(tc.input.get("file_path", ""))
            if fp and _is_ignored_path(fp, profiles):
                continue
            if fp and _is_design_path(fp, profiles):
                return True
        raw = _tool_signal_text(tc)
        if _is_ignored_path(raw, profiles):
            continue
        if _is_design_path(raw, profiles) and (
            _FILE_WRITE_CMD_RE.search(raw) or _GIT_PERSIST_RE.search(raw)
        ):
            return True

    return bool(
        classify_message(event) == MessageKind.TOOL_OUTPUT
        and _is_design_path(all_text, profiles)
        and _GIT_STATUS_CHANGE_RE.search(all_text)
    )


def _profile_persistence(text: str, profiles: tuple[SignalProfile, ...]) -> bool:
    if _looks_read_only(text):
        return False
    return _matches_any(text, (p.persistence_patterns for p in profiles))


def _is_design_path(text: str, profiles: Iterable[SignalProfile]) -> bool:
    return _matches_any(text, (p.design_artifact_patterns for p in profiles))


def _is_ignored_path(text: str, profiles: Iterable[SignalProfile]) -> bool:
    return _matches_any(text, (p.ignore_patterns for p in profiles))


def _matches_any(
    text: str,
    pattern_groups: Iterable[Iterable[re.Pattern[str]]],
) -> bool:
    return any(pattern.search(text) for group in pattern_groups for pattern in group)


def _tool_signal_text(tool_call: ToolCall) -> str:
    return "\n".join([tool_call.name, *[str(v) for v in tool_call.input.values()]])


def _text_can_signal_progress(event: IREvent) -> bool:
    if event.role != "user":
        return True
    return classify_message(event) in {MessageKind.TOOL_OUTPUT, MessageKind.HANDOFF_SUMMARY}


def _looks_read_only(text: str) -> bool:
    if not _READ_ONLY_COMMAND_RE.search(text):
        return False
    return not _FILE_WRITE_CMD_RE.search(text)
