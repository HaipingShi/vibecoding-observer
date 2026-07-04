"""Tests for message lifecycle classification."""

from __future__ import annotations

from observer.ir import IREvent
from observer.message_classifier import MessageKind, classify_message


def _ev(text: str, role: str = "user") -> IREvent:
    return IREvent(
        ts="2026-06-28T13:00:00Z",
        source_agent="codex",
        cwd="/p/example",
        project="example",
        role=role,  # type: ignore[arg-type]
        text=text,
    )


def test_short_user_request_is_human_instruction() -> None:
    assert classify_message(_ev("继续实现 MessageKind 分类")) == MessageKind.HUMAN_INSTRUCTION


def test_tool_output_is_not_human_instruction() -> None:
    text = """Chunk ID: abc123
Wall time: 0.7485 seconds
Process exited with code 0
Original token count: 1856
Output:
  % Total    % Received % Xferd
"""
    assert classify_message(_ev(text)) == MessageKind.TOOL_OUTPUT


def test_system_context_is_not_human_instruction() -> None:
    text = """<environment_context>
  <cwd>/tmp/project</cwd>
</environment_context>
"""
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_runtime_goal_state_is_system_context() -> None:
    text = (
        '{"goal":{"threadId":"019ef9f9","objective":"push forward",'
        '"status":"active","tokensUsed":3186477}}'
    )
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_plan_update_status_is_system_context() -> None:
    assert classify_message(_ev("Plan updated")) == MessageKind.SYSTEM_CONTEXT


def test_codex_internal_goal_context_is_system_context() -> None:
    text = """<codex_internal_context source="goal">
Continue working toward the active thread goal.
</codex_internal_context>
"""
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_in_app_browser_context_is_system_context() -> None:
    text = """# In app browser:
- The user has the in-app browser open.
- Current URL: http://localhost:3000/

## My request for Codex:
为什么会被拦截？
"""
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_ide_context_is_system_context() -> None:
    text = """# Context from my IDE setup:

## Active file: docs/document-index.md

## Open tabs:
- document-index.md: docs/document-index.md
"""
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_subagent_notification_is_system_context() -> None:
    text = '<subagent_notification> {"agent_path":"abc","status":{"completed":"DONE"}}'
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_subagent_status_state_is_system_context() -> None:
    text = '{"status":{"019e1544":{"completed":"DONE"}}}'
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_sequential_thinking_state_is_system_context() -> None:
    text = '{"thoughtNumber":2,"totalThoughts":3,"nextThoughtNeeded":false}'
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_user_abort_state_is_system_context() -> None:
    assert classify_message(_ev("aborted by user after 66.7s")) == MessageKind.SYSTEM_CONTEXT


def test_tool_failure_state_is_tool_output() -> None:
    text = """exec_command failed for `/bin/zsh -lc 'ps -ax'`: CreateProcess {
message: "Codex(Sandbox(Denied ...))"
}
"""
    assert classify_message(_ev(text)) == MessageKind.TOOL_OUTPUT


def test_tool_argument_failure_state_is_tool_output() -> None:
    text = "failed to parse function arguments: missing field `cmd` at line 1 column 390"
    assert classify_message(_ev(text)) == MessageKind.TOOL_OUTPUT


def test_agent_id_failure_state_is_tool_output() -> None:
    text = "invalid agent id 40271: Error(ParseSimpleLength { len: 5 })"
    assert classify_message(_ev(text)) == MessageKind.TOOL_OUTPUT


def test_missing_image_state_is_tool_output() -> None:
    text = "unable to locate image at `/tmp/output.png`: No such file or directory"
    assert classify_message(_ev(text)) == MessageKind.TOOL_OUTPUT


def test_turn_aborted_state_is_system_context() -> None:
    text = "<turn_aborted> The user interrupted the previous turn on purpose."
    assert classify_message(_ev(text)) == MessageKind.SYSTEM_CONTEXT


def test_pasted_markdown_source_is_not_human_instruction() -> None:
    text = """---
time: 2026-05-21
summary: 这是一段被贴入的资料正文。
---

# Vibe Coding 出海正处红利窗口

## 核心论点
这里是原始素材正文，不是人类对 agent 的操作指令。

## 四条路线
更多正文内容。

## 技术栈
更多正文内容。
"""
    assert classify_message(_ev(text)) == MessageKind.PASTED_SOURCE


def test_numbered_source_dump_is_not_human_instruction() -> None:
    text = "\n".join(f"{i}\t# line {i} content" for i in range(1, 12))
    assert classify_message(_ev(text)) == MessageKind.PASTED_SOURCE


def test_assistant_text_is_unknown_for_lifecycle_classifier() -> None:
    assert classify_message(_ev("我先来分析一下", role="assistant")) == MessageKind.UNKNOWN
