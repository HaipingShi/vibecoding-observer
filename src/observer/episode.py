"""Episode segmentation for task-level collaboration analysis.

Events are too small to explain vibe-coding quality by themselves. An episode
groups a project's timeline into task-shaped slices and summarizes whether the
slice has the engineering loop we care about: goal, constraints,
implementation, verification, correction, and closure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from observer.event_signals import DEFAULT_PROFILES, SignalProfile, detect_event_signals
from observer.ir import IREvent
from observer.message_classifier import MessageKind, classify_message

__all__ = ["EpisodeSegmenter", "EpisodeSummary", "segment_episodes"]

_DEFAULT_MAX_GAP_SECONDS = 30 * 60
_MAX_SNIPPET = 220

_NEW_GOAL_RE = re.compile(
    r"^(?:现在|接下来|然后|继续)?(?:请|帮我)?(?:实现|新增|修复|重构|设计|分析|创建|更新)"
    r"|^(?:new task|next task|now|please)\b",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"约束|边界|前提|必须|不要|禁止|只能|验收|测试|allowed|forbidden|constraint|must|should not|acceptance",
    re.IGNORECASE,
)
_CORRECTION_RE = re.compile(
    r"不对|错了|不是|方向|重新|换个思路|回退|别这样"
    r"|wrong|incorrect|not what|redo|start over|different approach",
    re.IGNORECASE,
)
_TASK_GOAL_RE = re.compile(
    r"实现|新增|修复|重构|设计|分析|创建|更新|检查|输出|提炼|制定|推进|部署|发布|测试|验证"
    r"|implement|add|fix|refactor|design|analy[sz]e|create|update|inspect|propose|build|deploy|test|verify",
    re.IGNORECASE,
)
_GENERIC_GOAL_RE = re.compile(
    r"^(?:a|ok|yes|go|continue|proceed|do it|开做|继续|继续推进|按你的理解，继续推进|根据你的理解，采用适当的方式push)$",
    re.IGNORECASE,
)
_METADATA_GOAL_RE = re.compile(
    r'^\s*\{.*"(?:agent_id|agent_path|previous_status|status|threadId|thoughtNumber|branches)"',
    re.DOTALL,
)
_CONTEXTUAL_GOAL_RE = re.compile(
    r"^(?:IMPORTANT:|You are |# Context from |All file contents are provided below)",
    re.IGNORECASE,
)
_EMBEDDED_REQUEST_RE = re.compile(
    r"##\s*My request for Codex:\s*(.+?)(?=\n##\s+|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_SELECTED_TEXT_RE = re.compile(
    r"#\s*Selected text:\s*(.+?)(?=\n##\s+My request for Codex:|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TASK_PREFIX_RE = re.compile(
    r"(?:任务|目标|Task|Goal)\s*[:：]\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
_SELECTION_HEADING_RE = re.compile(r"^##\s*Selection\s+\d+\s*", re.IGNORECASE)

_LONG_EPISODE_EVENTS = 50


@dataclass(frozen=True, slots=True)
class EpisodeSummary:
    """A task-shaped slice of a project timeline."""

    project: str
    cwd: str
    start_ts: str
    end_ts: str
    start_index: int
    end_index: int
    event_count: int
    goal: str
    constraints: tuple[str, ...]
    implementation_count: int
    verification_count: int
    correction_count: int
    closure_count: int
    code_implementation_count: int = 0
    docs_implementation_count: int = 0
    governance_signal_count: int = 0
    git_closeout_count: int = 0
    blocked_or_handoff_count: int = 0

    @property
    def has_goal(self) -> bool:
        return bool(self.goal)

    @property
    def has_implementation(self) -> bool:
        return self.implementation_count > 0

    @property
    def has_verification(self) -> bool:
        return self.verification_count > 0

    @property
    def has_correction(self) -> bool:
        return self.correction_count > 0

    @property
    def is_closed(self) -> bool:
        return self.closure_count > 0

    @property
    def loop_quality(self) -> str:
        """Coarse engineering-loop classification for downstream diagnosis."""
        if (
            self.blocked_or_handoff_count > 0
            and self.code_implementation_count == 0
            and self.git_closeout_count == 0
        ):
            return "blocked_or_handoff"
        if self.code_implementation_count > 0 and self.has_verification and self.is_closed:
            return "implementation_closed"
        if (
            self.docs_implementation_count > 0
            and (
                self.is_closed
                or self.governance_signal_count > 0
                or self.git_closeout_count > 0
            )
        ):
            return "design_closed"
        if self.has_verification and self.is_closed:
            return "closed_verified"
        if self.has_verification and not self.has_implementation:
            return "verification_only"
        if self.code_implementation_count > 0 and self.has_verification:
            return "implemented_verified_unclosed"
        if self.has_implementation:
            return "implemented_unverified"
        if self.has_goal:
            return "goal_only"
        return "unstructured"

    @property
    def goal_quality(self) -> str:
        return _classify_goal_quality(self.goal)[0]

    @property
    def goal_quality_reasons(self) -> tuple[str, ...]:
        return _classify_goal_quality(self.goal)[1]

    @property
    def normalized_goal(self) -> str:
        return _normalize_goal(self.goal)[0]

    @property
    def goal_extraction_method(self) -> str:
        return _normalize_goal(self.goal)[1]

    @property
    def diagnostic_signals(self) -> tuple[str, ...]:
        return _episode_diagnostic_signals(self)

    @property
    def confidence(self) -> str:
        """Confidence that the loop-quality label reflects real task state."""
        if self.loop_quality == "implementation_closed":
            return "high" if self.has_verification and self.is_closed else "medium"
        if self.loop_quality == "design_closed":
            return "high" if self.git_closeout_count > 0 or self.governance_signal_count > 0 else "medium"
        if self.loop_quality == "closed_verified":
            return "medium"
        if self.loop_quality in {"verification_only", "blocked_or_handoff"}:
            return "medium"
        if self.loop_quality in {"implemented_unverified", "implemented_verified_unclosed"}:
            return "medium"
        if self.loop_quality == "goal_only" and self.event_count >= _LONG_EPISODE_EVENTS:
            return "high"
        if self.loop_quality == "goal_only":
            return "medium"
        return "low"

    @property
    def coderail_count(self) -> int:
        """Deprecated compatibility alias for governance signal count."""
        return self.governance_signal_count

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "cwd": self.cwd,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "event_count": self.event_count,
            "goal": self.goal,
            "constraints": list(self.constraints),
            "implementation_count": self.implementation_count,
            "verification_count": self.verification_count,
            "correction_count": self.correction_count,
            "closure_count": self.closure_count,
            "code_implementation_count": self.code_implementation_count,
            "docs_implementation_count": self.docs_implementation_count,
            "governance_signal_count": self.governance_signal_count,
            "git_closeout_count": self.git_closeout_count,
            "blocked_or_handoff_count": self.blocked_or_handoff_count,
            "loop_quality": self.loop_quality,
            "goal_quality": self.goal_quality,
            "goal_quality_reasons": list(self.goal_quality_reasons),
            "normalized_goal": self.normalized_goal,
            "goal_extraction_method": self.goal_extraction_method,
            "confidence": self.confidence,
            "diagnostic_signals": list(self.diagnostic_signals),
        }


class EpisodeSegmenter:
    """Split ordered project events into task-level episodes."""

    def __init__(
        self,
        max_gap_seconds: int = _DEFAULT_MAX_GAP_SECONDS,
        profiles: Iterable[SignalProfile] = DEFAULT_PROFILES,
    ) -> None:
        self.max_gap_seconds = max_gap_seconds
        self.profiles = tuple(profiles)

    def segment(self, events: Iterable[IREvent]) -> list[EpisodeSummary]:
        evs = list(events)
        if not evs:
            return []

        groups: list[tuple[int, list[IREvent]]] = []
        current_start = 0
        current: list[IREvent] = []
        previous: IREvent | None = None
        previous_closed = False

        for idx, ev in enumerate(evs):
            starts_new = bool(
                current
                and _is_human_instruction(ev)
                and (
                    _gap_exceeds(previous, ev, self.max_gap_seconds)
                    or previous_closed
                    or _starts_new_goal(ev.text)
                )
            )
            if starts_new:
                groups.append((current_start, current))
                current_start = idx
                current = []
                previous_closed = False

            current.append(ev)
            if _can_close_episode_boundary(ev, self.profiles):
                previous_closed = True
            previous = ev

        if current:
            groups.append((current_start, current))

        summaries = [
            _summarize_episode(start_idx, group, self.profiles)
            for start_idx, group in groups
            if group
        ]
        return [summary for summary in summaries if _has_episode_signal(summary)]


def segment_episodes(
    events: Iterable[IREvent],
    max_gap_seconds: int = _DEFAULT_MAX_GAP_SECONDS,
    profiles: Iterable[SignalProfile] = DEFAULT_PROFILES,
) -> list[EpisodeSummary]:
    """One-shot episode segmentation."""
    return EpisodeSegmenter(max_gap_seconds=max_gap_seconds, profiles=profiles).segment(events)


def _summarize_episode(
    start_idx: int,
    events: list[IREvent],
    profiles: tuple[SignalProfile, ...],
) -> EpisodeSummary:
    first = events[0]
    last = events[-1]
    constraints: list[str] = []
    goal = ""
    implementation = 0
    verification = 0
    correction = 0
    closure = 0
    code_implementation = 0
    docs_implementation = 0
    governance_signals = 0
    git_closeout = 0
    blocked_or_handoff = 0

    for ev in events:
        if _is_human_instruction(ev):
            if not goal:
                goal = _goal_snippet(ev.text)
            if _CONSTRAINT_RE.search(ev.text) and len(constraints) < 5:
                constraints.append(_snippet(ev.text))
            if _CORRECTION_RE.search(ev.text):
                correction += 1

        signals = detect_event_signals(ev, profiles=profiles)
        if signals.implementation:
            implementation += 1
        if signals.code_edit:
            code_implementation += 1
        if signals.design_artifact:
            docs_implementation += 1
        if signals.governance:
            governance_signals += 1
        if signals.persistence:
            git_closeout += 1
        if signals.handoff:
            blocked_or_handoff += 1
        if signals.verification:
            verification += 1
        if signals.closure:
            closure += 1

    return EpisodeSummary(
        project=first.project,
        cwd=first.cwd,
        start_ts=first.ts,
        end_ts=last.ts,
        start_index=start_idx,
        end_index=start_idx + len(events) - 1,
        event_count=len(events),
        goal=goal,
        constraints=tuple(constraints),
        implementation_count=implementation,
        verification_count=verification,
        correction_count=correction,
        closure_count=closure,
        code_implementation_count=code_implementation,
        docs_implementation_count=docs_implementation,
        governance_signal_count=governance_signals,
        git_closeout_count=git_closeout,
        blocked_or_handoff_count=blocked_or_handoff,
    )


def _is_human_instruction(event: IREvent) -> bool:
    return classify_message(event) == MessageKind.HUMAN_INSTRUCTION


def _starts_new_goal(text: str) -> bool:
    return bool(_NEW_GOAL_RE.search(text.strip()))


def _can_close_episode_boundary(
    event: IREvent,
    profiles: tuple[SignalProfile, ...],
) -> bool:
    """Only conversational completion claims should split the next user task.

    Tool-level closeout signals such as done_gate.py and trace_index.py are
    evidence inside the current task; otherwise the following commit or handoff
    update can be orphaned into a separate episode.
    """
    return bool(
        event.role == "assistant"
        and event.text
        and detect_event_signals(event, profiles=profiles).closure
    )


def _has_episode_signal(summary: EpisodeSummary) -> bool:
    return bool(
        summary.has_goal
        or summary.has_implementation
        or summary.has_verification
        or summary.has_correction
        or summary.is_closed
    )


def _classify_goal_quality(goal: str) -> tuple[str, tuple[str, ...]]:
    text = goal.strip()
    if not text:
        return "missing", ("empty_goal",)

    reasons: list[str] = []
    if _METADATA_GOAL_RE.search(text):
        return "metadata", ("structured_runtime_state",)

    if _CONTEXTUAL_GOAL_RE.search(text):
        reasons.append("context_wrapper")

    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 2:
        reasons.append("too_short")

    if _GENERIC_GOAL_RE.search(text):
        reasons.append("generic_command")
        return "weak", tuple(reasons)

    if _TASK_GOAL_RE.search(text):
        if reasons == ["context_wrapper"]:
            return "contextual", tuple(reasons)
        return "task_like", tuple(reasons) if reasons else ("actionable_goal",)

    if reasons:
        return "weak", tuple(reasons)

    if len(text) >= 12:
        return "task_like", ("descriptive_goal",)

    return "weak", ("low_information_goal",)


def _normalize_goal(goal: str) -> tuple[str, str]:
    text = goal.strip()
    if not text:
        return "", "missing"
    if _METADATA_GOAL_RE.search(text):
        return "", "ignored_metadata"

    embedded_request = _extract_match(_EMBEDDED_REQUEST_RE, text)
    selected_text = _extract_match(_SELECTED_TEXT_RE, text)
    if embedded_request:
        if _is_generic_goal(embedded_request) and selected_text:
            return _snippet(selected_text), "selected_text_context"
        return _snippet(embedded_request), "embedded_request"
    if selected_text:
        return _snippet(selected_text), "selected_text_context"

    task_body = _extract_match(_TASK_PREFIX_RE, text)
    if task_body:
        return _snippet(task_body), "task_prefix"

    if _is_generic_goal(text):
        return "", "weak_generic"

    return text, "raw_goal"


def _episode_diagnostic_signals(ep: EpisodeSummary) -> tuple[str, ...]:
    signals: list[str] = []

    if ep.goal_quality in {"weak", "metadata", "missing"}:
        signals.append(f"{ep.goal_quality}_goal")
    if ep.has_goal and not ep.normalized_goal:
        signals.append("unusable_goal")
    if ep.goal_extraction_method in {"embedded_request", "selected_text_context", "task_prefix"}:
        signals.append("wrapped_goal_decoded")

    if ep.has_implementation and not ep.has_verification:
        signals.append("implementation_without_verification")
    if ep.has_implementation and ep.has_verification and not ep.is_closed:
        signals.append("verified_but_unclosed")
    if ep.loop_quality == "goal_only" and ep.event_count >= _LONG_EPISODE_EVENTS:
        signals.append("long_goal_only_episode")
    if (
        ep.goal_quality == "task_like"
        and ep.has_goal
        and ep.loop_quality == "goal_only"
        and ep.event_count >= _LONG_EPISODE_EVENTS
    ):
        signals.append("top_level_goal_without_engineering_loop")

    return tuple(signals)


def _extract_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    return _clean_extracted_goal(match.group(1))


def _clean_extracted_goal(text: str) -> str:
    cleaned = _SELECTION_HEADING_RE.sub("", text.strip())
    return _snippet(cleaned)


def _is_generic_goal(text: str) -> bool:
    return bool(_GENERIC_GOAL_RE.search(text.strip()))


def _gap_exceeds(prev: IREvent | None, current: IREvent, threshold_seconds: int) -> bool:
    if prev is None:
        return False
    prev_dt = _parse_ts(prev.ts)
    curr_dt = _parse_ts(current.ts)
    if prev_dt is None or curr_dt is None:
        return False
    return (curr_dt - prev_dt).total_seconds() > threshold_seconds


def _parse_ts(ts: str) -> datetime | None:
    cleaned = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _snippet(text: str) -> str:
    compact = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    if len(compact) <= _MAX_SNIPPET:
        return compact
    return compact[: _MAX_SNIPPET - 1].rstrip() + "…"


def _goal_snippet(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _MAX_SNIPPET:
        return stripped
    return _snippet(stripped)
