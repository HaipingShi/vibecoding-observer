"""Message lifecycle classifier.

This layer separates *what a message is* from *what labels it might carry*.
The Extractor should only treat human instructions as interaction intent.
Large pasted source material, tool outputs, and injected system context are
evidence, not user steering.
"""

from __future__ import annotations

import re
from enum import StrEnum

from observer.ir import IREvent

__all__ = ["MessageKind", "classify_message"]


class MessageKind(StrEnum):
    """Lifecycle role of an event's text."""

    HUMAN_INSTRUCTION = "human_instruction"
    PASTED_SOURCE = "pasted_source"
    TOOL_OUTPUT = "tool_output"
    SYSTEM_CONTEXT = "system_context"
    HANDOFF_SUMMARY = "handoff_summary"
    UNKNOWN = "unknown"


_TOOL_OUTPUT_MARKERS = re.compile(
    r"Chunk ID:|Wall time:|Process exited with code|Original token count:"
    r"|^Output:\n|^Exit code:|Traceback \(most recent call last\):"
    r"|^\s*(?:exec_command|write_stdin|apply_patch) failed\b"
    r"|^\s*(?:failed to parse function arguments|invalid agent id|unable to locate image)\b",
    re.MULTILINE,
)
_SYSTEM_CONTEXT_MARKERS = re.compile(
    r"^<environment_context>|^<permissions_instructions>|^# AGENTS\.md instructions"
    r"|^<INSTRUCTIONS>|</INSTRUCTIONS>|^<codex_internal_context\b"
    r"|^# In app browser:|^# Context from my IDE setup:"
    r"|^<turn_aborted>|^<subagent_notification>|^\s*aborted by user after\b",
    re.MULTILINE,
)
_RUNTIME_STATE_MARKERS = re.compile(
    r'^\s*\{\s*"goal"\s*:\s*\{'
    r"|^\s*\{\s*\"threadId\"\s*:"
    r"|^\s*\{\s*\"thoughtNumber\"\s*:"
    r"|^\s*\{\s*\"status\"\s*:\s*\{"
    r"|^\s*Plan updated\s*$",
    re.MULTILINE,
)
_HANDOFF_MARKERS = re.compile(
    r"\bhandoff\b|Resume Prompt|Current Strategy:|Divergence Log",
    re.IGNORECASE,
)
_PASTED_SOURCE_MARKERS = re.compile(
    r"All file contents are provided below|Staging files \(raw daily entries"
    r"|^---\s*$|^#{1,3}\s+.+|^\d+\t",
    re.MULTILINE,
)


def classify_message(event: IREvent) -> MessageKind:
    """Classify an event's text lifecycle role.

    The classifier is intentionally conservative: ambiguous short user text
    remains ``human_instruction`` so existing extraction behavior is preserved.
    Only strong structural evidence demotes text to source/tool/system material.
    """
    text = event.text.strip()
    if not text:
        return MessageKind.UNKNOWN

    if event.role != "user":
        return MessageKind.UNKNOWN

    if _SYSTEM_CONTEXT_MARKERS.search(text):
        return MessageKind.SYSTEM_CONTEXT

    if _RUNTIME_STATE_MARKERS.search(text):
        return MessageKind.SYSTEM_CONTEXT

    if _TOOL_OUTPUT_MARKERS.search(text):
        return MessageKind.TOOL_OUTPUT

    if _looks_like_handoff_summary(text):
        return MessageKind.HANDOFF_SUMMARY

    if _looks_like_pasted_source(text):
        return MessageKind.PASTED_SOURCE

    return MessageKind.HUMAN_INSTRUCTION


def _looks_like_handoff_summary(text: str) -> bool:
    if len(text) < 200:
        return False
    return bool(_HANDOFF_MARKERS.search(text))


def _looks_like_pasted_source(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False

    numbered = sum(1 for line in lines if re.match(r"^\d+\t", line))
    headings = sum(1 for line in lines if re.match(r"^#{1,4}\s+\S", line))
    frontmatter = text.startswith("---\n") or "\n---\n" in text[:200]

    if len(lines) >= 8 and numbered / len(lines) >= 0.25:
        return True
    if frontmatter and headings >= 1:
        return True

    if len(text) < 500:
        return False

    if headings >= 3 and len(text) > 900:
        return True

    marker_hits = len(_PASTED_SOURCE_MARKERS.findall(text))
    return marker_hits >= 3
