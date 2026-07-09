"""Tests for task-level episode segmentation."""

from __future__ import annotations

from observer.episode import EpisodeSegmenter, segment_episodes
from observer.event_signals import CODE_RAIL_PROFILE, GENERIC_PROFILE
from observer.ir import IREvent, ToolCall

_CODERAIL_PROFILES = (GENERIC_PROFILE, CODE_RAIL_PROFILE)


def _ev(
    role: str,
    text: str = "",
    ts: str = "2026-06-28T13:00:00Z",
    tool_calls: tuple[ToolCall, ...] = (),
) -> IREvent:
    return IREvent(
        ts=ts,
        source_agent="codex",
        cwd="/p/example",
        project="example",
        role=role,  # type: ignore[arg-type]
        text=text,
        tool_calls=tool_calls,
    )


def test_empty_events_return_empty() -> None:
    assert segment_episodes([]) == []


def test_single_episode_summarizes_engineering_loop() -> None:
    episodes = segment_episodes([
        _ev("user", "请实现导出功能，必须有 pytest 验收"),
        _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
        _ev("assistant", "运行 pytest 验证", tool_calls=(ToolCall(name="Bash", input={"command": "uv run pytest"}),)),
        _ev("assistant", "完成，All checks passed"),
    ])

    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.has_goal
    assert ep.has_implementation
    assert ep.has_verification
    assert ep.is_closed
    assert ep.loop_quality == "implementation_closed"
    assert ep.constraints == ("请实现导出功能，必须有 pytest 验收",)


def test_codex_apply_patch_shell_command_counts_as_implementation() -> None:
    episodes = segment_episodes([
        _ev("user", "请修复 parser bug，必须跑 pytest"),
        _ev(
            "assistant",
            tool_calls=(
                ToolCall(
                    name="exec_command",
                    input={"cmd": "apply_patch <<'PATCH'\n*** Begin Patch\n*** Update File: parser.py\nPATCH"},
                ),
            ),
        ),
        _ev(
            "assistant",
            tool_calls=(ToolCall(name="exec_command", input={"cmd": "uv run pytest"}),),
        ),
        _ev("assistant", "完成，All checks passed"),
    ])

    ep = episodes[0]
    assert ep.implementation_count == 1
    assert ep.verification_count >= 1
    assert ep.loop_quality == "implementation_closed"


def test_shell_verify_commands_include_static_checks_and_git_diff_check() -> None:
    episodes = segment_episodes([
        _ev("user", "请检查发布前质量"),
        _ev(
            "assistant",
            tool_calls=(
                ToolCall(
                    name="exec_command",
                    input={"cmd": "uv run ruff check . && uv run mypy . && git diff --check"},
                ),
            ),
        ),
    ])

    ep = episodes[0]
    assert ep.verification_count == 1
    assert ep.loop_quality == "verification_only"


def test_coderail_done_gate_trace_index_and_commit_close_loop() -> None:
    episodes = segment_episodes(
        [
            _ev("user", "按 CodeRail 任务完成 T-012，更新 trace 并 closeout"),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={
                            "cmd": "python scripts/trace_event.py --task T-012 --kind verify"
                        },
                    ),
                ),
            ),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(name="exec_command", input={"cmd": "python scripts/trace_index.py"}),
                ),
            ),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={"cmd": "python scripts/done_gate.py --task T-012"},
                    ),
                ),
            ),
            _ev("user", "Done Gate: pass"),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={
                            "cmd": "git add docs/TASKS.md docs/TRACELOG.jsonl && git commit -m 'Close T-012'"
                        },
                    ),
                ),
            ),
        ],
        profiles=_CODERAIL_PROFILES,
    )

    ep = episodes[0]
    assert ep.implementation_count >= 1
    assert ep.governance_signal_count >= 1
    assert ep.verification_count >= 1
    assert ep.is_closed
    assert ep.loop_quality == "design_closed"


def test_docs_only_adr_closeout_is_design_closed_not_goal_only() -> None:
    episodes = segment_episodes(
        [
            _ev("user", "请完成 ADR，记录架构决策并更新任务状态"),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={
                            "cmd": "python - <<'PY'\nfrom pathlib import Path\nPath('docs/DECISIONS.md').write_text('ADR-001')\nPY"
                        },
                    ),
                ),
            ),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={"cmd": "python scripts/trace_event.py --kind decision"},
                    ),
                ),
            ),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={"cmd": "git add docs/DECISIONS.md && git commit -m 'Record ADR'"},
                    ),
                ),
            ),
        ],
        profiles=_CODERAIL_PROFILES,
    )

    ep = episodes[0]
    assert ep.implementation_count >= 1
    assert ep.loop_quality == "design_closed"


def test_blocked_or_handoff_episode_is_not_goal_only() -> None:
    episodes = segment_episodes([
        _ev("user", "请推进 T-020，如果阻塞就写 handoff"),
        _ev(
            "assistant",
            "Blocked: 缺少产品决策，已更新 HANDOFF.md，下一步等待确认",
        ),
    ])

    ep = episodes[0]
    assert ep.loop_quality == "blocked_or_handoff"


def test_verified_and_closed_governance_loop_is_not_implemented_unverified() -> None:
    episodes = segment_episodes(
        [
            _ev("user", "请按 CodeRail 完成 T-030"),
            _ev(
                "assistant",
                tool_calls=(
                    ToolCall(
                        name="exec_command",
                        input={
                            "cmd": "python scripts/trace_event.py --task T-030 --kind verify"
                        },
                    ),
                ),
            ),
            _ev("assistant", "Done Gate: passed"),
        ],
        profiles=_CODERAIL_PROFILES,
    )

    ep = episodes[0]
    assert ep.verification_count > 0
    assert ep.closure_count > 0
    assert ep.loop_quality == "closed_verified"


def test_episode_splits_on_large_time_gap() -> None:
    episodes = EpisodeSegmenter(max_gap_seconds=60).segment([
        _ev("user", "请实现 A", ts="2026-06-28T13:00:00Z"),
        _ev("assistant", "完成", ts="2026-06-28T13:00:10Z"),
        _ev("user", "请实现 B", ts="2026-06-28T13:10:00Z"),
    ])

    assert len(episodes) == 2
    assert episodes[0].goal == "请实现 A"
    assert episodes[1].goal == "请实现 B"


def test_episode_splits_on_explicit_new_goal_after_closure() -> None:
    episodes = segment_episodes([
        _ev("user", "请实现 A"),
        _ev("assistant", "完成"),
        _ev("user", "接下来请修复 B"),
    ])

    assert len(episodes) == 2
    assert episodes[1].goal == "接下来请修复 B"


def test_pasted_source_does_not_become_goal() -> None:
    pasted = """---
time: 2026-05-21
summary: raw source
---

# Vibe Coding

## 核心论点
正文。
"""
    episodes = segment_episodes([
        _ev("user", pasted),
        _ev("user", "请基于上面的素材提炼约束"),
    ])

    assert len(episodes) == 1
    assert episodes[0].goal == "请基于上面的素材提炼约束"


def test_runtime_goal_state_does_not_become_goal() -> None:
    runtime_state = (
        '{"goal":{"threadId":"019ef9f9","objective":"push forward",'
        '"status":"active","tokensUsed":3186477}}'
    )
    episodes = segment_episodes([
        _ev("user", runtime_state),
        _ev("user", "请继续实现 episode profile"),
    ])

    assert len(episodes) == 1
    assert episodes[0].goal == "请继续实现 episode profile"


def test_plan_update_status_does_not_become_goal() -> None:
    episodes = segment_episodes([
        _ev("user", "Plan updated"),
        _ev("user", "请继续实现 episode profile"),
    ])

    assert len(episodes) == 1
    assert episodes[0].goal == "请继续实现 episode profile"


def test_codex_runtime_context_does_not_become_goal() -> None:
    episodes = segment_episodes([
        _ev("user", "<codex_internal_context source=\"goal\">continue</codex_internal_context>"),
        _ev("user", "# In app browser:\n- Current URL: http://localhost:3000/"),
        _ev("user", "# Context from my IDE setup:\n\n## Active file: docs/index.md"),
        _ev("user", '<subagent_notification> {"status":{"completed":"DONE"}}'),
        _ev("user", '{"thoughtNumber":2,"totalThoughts":3,"nextThoughtNeeded":false}'),
        _ev("user", "exec_command failed for `/bin/zsh -lc 'ps'`: CreateProcess"),
        _ev("user", "failed to parse function arguments: missing field `cmd`"),
        _ev("user", "invalid agent id 40271: Error(ParseSimpleLength { len: 5 })"),
        _ev("user", "unable to locate image at `/tmp/out.png`: No such file or directory"),
        _ev("user", "请继续实现 episode profile"),
    ])

    assert len(episodes) == 1
    assert episodes[0].goal == "请继续实现 episode profile"


def test_correction_count_uses_human_instruction_only() -> None:
    tool_output = """Chunk ID: abc
Wall time: 1.0 seconds
Process exited with code 0
Output:
不对，这不是匹配问题
"""
    episodes = segment_episodes([
        _ev("user", "请实现 A"),
        _ev("user", tool_output),
        _ev("user", "不对，方向错了"),
    ])

    assert episodes[0].correction_count == 1


def test_to_dict_includes_loop_quality() -> None:
    ep = segment_episodes([_ev("user", "请实现 A")])[0]
    data = ep.to_dict()
    assert data["loop_quality"] == "goal_only"
    assert data["goal"] == "请实现 A"
    assert data["goal_quality"] == "task_like"
    assert data["normalized_goal"] == "请实现 A"
    assert data["goal_extraction_method"] == "raw_goal"
    assert data["confidence"] == "medium"
    assert data["diagnostic_signals"] == []


def test_goal_quality_marks_weak_short_commands() -> None:
    ep = segment_episodes([_ev("user", "a")])[0]

    assert ep.goal_quality == "weak"
    assert ep.goal_quality_reasons == ("too_short", "generic_command")


def test_goal_quality_marks_metadata_json() -> None:
    ep = segment_episodes([
        _ev("user", '{"agent_id":"019e1544","nickname":"Lovelace"}')
    ])[0]

    assert ep.goal_quality == "metadata"
    assert ep.goal_quality_reasons == ("structured_runtime_state",)


def test_goal_quality_marks_previous_status_json_as_metadata() -> None:
    ep = segment_episodes([
        _ev("user", '{"previous_status":{"completed":"已实现 Phase 3/4 独立骨架"}}')
    ])[0]

    assert ep.goal_quality == "metadata"
    assert ep.goal_quality_reasons == ("structured_runtime_state",)


def test_goal_quality_marks_truncated_previous_status_json_as_metadata() -> None:
    ep = segment_episodes([
        _ev("user", '{"previous_status":{"completed":"已实现 Phase 3/4 独立骨架…')
    ])[0]

    assert ep.goal_quality == "metadata"
    assert ep.goal_quality_reasons == ("structured_runtime_state",)


def test_goal_quality_keeps_generic_progress_command_weak() -> None:
    ep = segment_episodes([_ev("user", "按你的理解，继续推进")])[0]

    assert ep.goal_quality == "weak"
    assert ep.goal_quality_reasons == ("generic_command",)


def test_goal_quality_marks_context_wrappers() -> None:
    ep = segment_episodes([
        _ev("user", "IMPORTANT: Do NOT read skill files. Inspect the repo and propose a plan.")
    ])[0]

    assert ep.goal_quality == "contextual"
    assert ep.goal_quality_reasons == ("context_wrapper",)


def test_normalized_goal_extracts_embedded_request() -> None:
    ep = segment_episodes([
        _ev("user", "# Selected text:\n忽略这段\n\n## My request for Codex:\n请检查 API contract 是否漂移")
    ])[0]

    assert ep.normalized_goal == "请检查 API contract 是否漂移"
    assert ep.goal_extraction_method == "embedded_request"


def test_normalized_goal_uses_selected_text_when_request_is_generic() -> None:
    ep = segment_episodes([
        _ev("user", "# Selected text:\n做 S-001/M-001 阶段复盘，决定是否创建下一 milestone\n\n## My request for Codex:\ngo")
    ])[0]

    assert ep.normalized_goal == "做 S-001/M-001 阶段复盘，决定是否创建下一 milestone"
    assert ep.goal_extraction_method == "selected_text_context"


def test_normalized_goal_extracts_selected_text_without_request() -> None:
    ep = segment_episodes([
        _ev("user", "# Selected text:\n## Selection 1\n修复 BullMQ-only 常驻模式的部署风险")
    ])[0]

    assert ep.normalized_goal == "修复 BullMQ-only 常驻模式的部署风险"
    assert ep.goal_extraction_method == "selected_text_context"


def test_normalized_goal_extracts_task_prefix() -> None:
    ep = segment_episodes([
        _ev("user", "在 /tmp/project 仅读分析。任务：检查 HumanGate.wait 改动影响。请给出最小建议。")
    ])[0]

    assert ep.normalized_goal == "检查 HumanGate.wait 改动影响。请给出最小建议。"
    assert ep.goal_extraction_method == "task_prefix"


def test_normalized_goal_extracts_target_prefix() -> None:
    ep = segment_episodes([
        _ev("user", "你在 /tmp/project 工作。目标：修复生产支付回调失败。先读 AGENTS.md。")
    ])[0]

    assert ep.normalized_goal == "修复生产支付回调失败。先读 AGENTS.md。"
    assert ep.goal_extraction_method == "task_prefix"


def test_normalized_goal_omits_metadata_and_generic_commands() -> None:
    metadata = segment_episodes([_ev("user", '{"agent_id":"019e1544"}')])[0]
    generic = segment_episodes([_ev("user", "开做")])[0]

    assert metadata.normalized_goal == ""
    assert metadata.goal_extraction_method == "ignored_metadata"
    assert generic.normalized_goal == ""
    assert generic.goal_extraction_method == "weak_generic"


def test_diagnostic_signals_mark_weak_and_unusable_goals() -> None:
    ep = segment_episodes([_ev("user", "开做")])[0]

    assert ep.diagnostic_signals == ("weak_goal", "unusable_goal")


def test_diagnostic_signals_mark_implementation_without_verification() -> None:
    ep = segment_episodes([
        _ev("user", "请实现导出功能"),
        _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
    ])[0]

    assert "implementation_without_verification" in ep.diagnostic_signals


def test_diagnostic_signals_mark_long_goal_only_episode() -> None:
    events = [_ev("user", "请分析 API contract 漂移风险")]
    events.extend(_ev("assistant", "继续分析") for _ in range(50))

    ep = segment_episodes(events)[0]

    assert "long_goal_only_episode" in ep.diagnostic_signals
    assert "top_level_goal_without_engineering_loop" in ep.diagnostic_signals


def test_diagnostic_signals_mark_wrapped_goal_decoded() -> None:
    ep = segment_episodes([
        _ev("user", "在 /tmp/project 仅读分析。任务：检查 HumanGate.wait 改动影响。")
    ])[0]

    assert ep.diagnostic_signals == ("wrapped_goal_decoded",)
