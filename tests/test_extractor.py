"""Tests for the Event Extractor (taxonomy tagging).

Validates that every label class has at least one positive case.
Focuses on the rule logic since labels are the skill's analytical core.
"""

from __future__ import annotations

from observer.extractor import extract
from observer.ir import IREvent, ToolCall

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ev(
    role: str,
    text: str = "",
    agent: str = "claude",
    tool_calls: tuple[ToolCall, ...] = (),
    is_handoff: bool = False,
    ts: str = "2026-06-28T13:00:00Z",
) -> IREvent:
    return IREvent(
        ts=ts,
        source_agent=agent,  # type: ignore[arg-type]
        cwd="/p/example",
        project="example",
        role=role,  # type: ignore[arg-type]
        text=text,
        tool_calls=tool_calls,
        is_handoff=is_handoff,
    )


def _labels_at(events: list[IREvent], idx: int) -> frozenset[str]:
    return extract(events)[idx].label_values


# --------------------------------------------------------------------------- #
# Dimension 2: Activations
# --------------------------------------------------------------------------- #


class TestActivations:
    def test_first_principle(self) -> None:
        events = [_ev("user", "人类是怎么区分主角配角的？")]
        assert "act-first-principle" in _labels_at(events, 0)

    def test_first_principle_english(self) -> None:
        events = [_ev("user", "How does a human actually distinguish main characters?")]
        assert "act-first-principle" in _labels_at(events, 0)

    def test_scale_stress(self) -> None:
        events = [_ev("user", "如果是 128 分钟的长片呢？")]
        assert "act-scale-stress" in _labels_at(events, 0)

    def test_scale_stress_large_count(self) -> None:
        events = [_ev("user", "如果有上万条数据呢？")]
        assert "act-scale-stress" in _labels_at(events, 0)

    def test_scale_stress_gb(self) -> None:
        events = [_ev("user", "如果数据是 3.2GB 呢？")]
        assert "act-scale-stress" in _labels_at(events, 0)

    def test_scale_stress_not_triggered_by_bare_numbers(self) -> None:
        """Bare numbers (line refs, token counts, exit codes) are NOT activations."""
        events = [_ev("user", "Process exited with code 0\nOriginal token count: 871")]
        assert "act-scale-stress" not in _labels_at(events, 0)

    def test_scale_stress_not_triggered_by_file_list(self) -> None:
        events = [_ev("user", "10: test.pdf\n20: config.toml\n300: data.json")]
        assert "act-scale-stress" not in _labels_at(events, 0)

    def test_scale_stress_not_triggered_by_timestamp(self) -> None:
        events = [_ev("user", "Wall time: 12.2519 seconds\n2026-06-28T13:00:00Z")]
        assert "act-scale-stress" not in _labels_at(events, 0)

    def test_scale_stress_english(self) -> None:
        events = [_ev("user", "What if there are millions of users?")]
        assert "act-scale-stress" in _labels_at(events, 0)

    def test_ab_falsify(self) -> None:
        events = [_ev("user", "我们做个 A/B 对比实验")]
        assert "act-ab-falsify" in _labels_at(events, 0)

    def test_ab_falsify_english(self) -> None:
        events = [_ev("user", "Let's compare the two approaches")]
        assert "act-ab-falsify" in _labels_at(events, 0)

    def test_constraint_reason(self) -> None:
        events = [_ev("user", "这是什么类型的问题？约束是什么？")]
        assert "act-constraint-reason" in _labels_at(events, 0)

    def test_constraint_reason_english(self) -> None:
        events = [_ev("user", "What type of problem is this? What are the constraints?")]
        assert "act-constraint-reason" in _labels_at(events, 0)

    def test_passive_short_message(self) -> None:
        events = [_ev("user", "继续")]
        assert "act-passive" in _labels_at(events, 0)

    def test_passive_not_triggered_for_long(self) -> None:
        events = [_ev("user", "请继续实现剩余的三个测试用例并修复失败的断言")]
        assert "act-passive" not in _labels_at(events, 0)

    def test_multiple_activations_one_message(self) -> None:
        events = [_ev("user", "人类是怎么做的？如果数据是 3.2GB 呢？")]
        labels = _labels_at(events, 0)
        assert {"act-first-principle", "act-scale-stress"} <= labels

    def test_assistant_text_not_tagged_as_activation(self) -> None:
        events = [_ev("assistant", "人类是这么做的...")]
        assert "act-first-principle" not in _labels_at(events, 0)

    def test_pasted_source_not_tagged_as_activation(self) -> None:
        events = [
            _ev(
                "user",
                """---
time: 2026-05-21
summary: 原始素材。
---

# Vibe Coding 出海正处红利窗口

## 核心论点
这里写了很多关于约束、对比和人类如何工作的资料正文。

## 技术栈
如果有上万用户也只是资料内容。

## 路线
继续正文。
""",
            )
        ]
        assert _labels_at(events, 0) == frozenset()


# --------------------------------------------------------------------------- #
# Dimension 1: Response patterns
# --------------------------------------------------------------------------- #


class TestResponsePatterns:
    def test_tool_fail(self) -> None:
        events = [
            _ev(
                "assistant",
                tool_calls=(ToolCall(name="Bash", result_ok=False),),
            )
        ]
        assert "degen-tool-fail" in _labels_at(events, 0)

    def test_eng_decompose_detected(self) -> None:
        events = [_ev("assistant", "我先来分析一下子问题，拆解成几个步骤")]
        assert "eng-decompose" in _labels_at(events, 0)

    def test_eng_decompose_tradeoff(self) -> None:
        events = [_ev("assistant", "有两种方案，各有优缺点和权衡")]
        assert "eng-decompose" in _labels_at(events, 0)

    def test_eng_verify_detected(self) -> None:
        events = [_ev("assistant", "我先写测试验证一下是否能正常工作")]
        assert "eng-verify" in _labels_at(events, 0)

    def test_eng_verify_pytest(self) -> None:
        events = [_ev("assistant", "跑一遍 pytest 看看")]
        assert "eng-verify" in _labels_at(events, 0)

    def test_eng_decompose_english(self) -> None:
        events = [_ev("assistant", "Let's break this down into sub-problems first")]
        assert "eng-decompose" in _labels_at(events, 0)

    def test_eng_decompose_english_tradeoffs(self) -> None:
        events = [_ev("assistant", "Here are two approaches with their trade-offs")]
        assert "eng-decompose" in _labels_at(events, 0)

    def test_eng_verify_english(self) -> None:
        events = [_ev("assistant", "Let's run the tests to verify this works")]
        assert "eng-verify" in _labels_at(events, 0)

    def test_user_pushback_english(self) -> None:
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Bash", input={"command": "ls"}),)),
            _ev("user", "That's wrong, why did you pick this approach?"),
        ]
        assert "degen-intuition" in _labels_at(events, 1)

    def test_wrong_layer_english(self) -> None:
        events = [_ev("user", "This is reasoning, not pattern matching. Think about it differently.")]
        assert "degen-wrong-layer" in _labels_at(events, 0)

    def test_eng_not_triggered_by_user(self) -> None:
        events = [_ev("user", "我先来分析一下子问题")]
        assert "eng-decompose" not in _labels_at(events, 0)

    def test_tool_success_not_flagged(self) -> None:
        events = [
            _ev(
                "assistant",
                tool_calls=(ToolCall(name="Bash", result_ok=True),),
            )
        ]
        assert "degen-tool-fail" not in _labels_at(events, 0)

    def test_stops_at_works(self) -> None:
        # assistant says done, then edits the same area → rework.
        events = [
            _ev("assistant", "完成了。", tool_calls=(ToolCall(name="Bash", result_ok=True),)),
            _ev(
                "assistant",
                "修一下",
                tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),),
            ),
        ]
        assert "degen-stops-at-works" in _labels_at(events, 0)
        assert "degen-stops-at-works" in _labels_at(events, 1)

    def test_done_without_rework_not_flagged(self) -> None:
        events = [
            _ev("assistant", "完成了。"),
            _ev("user", "谢谢"),  # no edit → no rework
        ]
        assert "degen-stops-at-works" not in _labels_at(events, 0)

    # --- ICSE 2026 labels ---

    def test_instant_gratification(self) -> None:
        """User accepts quickly then degen appears → instant-gratification."""
        events = [
            _ev("assistant", "here's the code"),
            _ev("user", "好的"),
            _ev("assistant", tool_calls=(ToolCall(name="Bash", result_ok=False),)),
        ]
        assert "degen-instant-gratification" in _labels_at(events, 1)

    def test_instant_gratification_not_triggered_without_degen(self) -> None:
        events = [
            _ev("assistant", "here's the code"),
            _ev("user", "好的"),
            _ev("assistant", "continuing..."),
        ]
        assert "degen-instant-gratification" not in _labels_at(events, 1)

    def test_suggester_preference(self) -> None:
        """User blindly accepts LLM output then later corrects it."""
        events = [
            _ev("assistant", "x" * 60),  # substantial output
            _ev("user", "looks good"),
            _ev("assistant", "more code"),
            _ev("user", "不对，这里错了"),
        ]
        assert "degen-suggester-preference" in _labels_at(events, 1)

    def test_fixation(self) -> None:
        """Same file edited 3+ times → fixation on the 3rd."""
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
        ]
        assert "degen-fixation" in _labels_at(events, 2)
        assert "degen-fixation" not in _labels_at(events, 1)

    def test_intuition_pushback(self) -> None:
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Bash", input={"command": "ls"}),)),
            _ev("user", "为什么选这个方案？不对"),
        ]
        assert "degen-intuition" in _labels_at(events, 1)

    def test_knowledge_as_ability(self) -> None:
        events = [
            _ev("user", "记住：你是角色识别专家，必须使用角色名"),
            _ev("assistant", "好的"),
            _ev("user", "不对，你怎么没用角色名"),
        ]
        assert "degen-knowledge-as-ability" in _labels_at(events, 0)

    def test_wrong_layer(self) -> None:
        events = [
            _ev("user", "这不是匹配问题，这是推理问题，换个思路"),
        ]
        assert "degen-wrong-layer" in _labels_at(events, 0)

    def test_ignore_lifecycle(self) -> None:
        events = [_ev("user", "哪些是永久资产？数据流是什么？")]
        assert "degen-ignore-lifecycle" in _labels_at(events, 0)

    def test_tool_output_not_tagged_as_user_pushback(self) -> None:
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Bash", input={"command": "curl"}),)),
            _ev(
                "user",
                """Chunk ID: c4c9c6
Wall time: 0.7485 seconds
Process exited with code 0
Original token count: 1856
Output:
这不是匹配问题，这是推理问题
""",
            ),
        ]
        assert _labels_at(events, 1) == frozenset()


# --------------------------------------------------------------------------- #
# Dimension 3: Waste
# --------------------------------------------------------------------------- #


class TestWaste:
    def test_blind_edit(self) -> None:
        # Edit a file that was never Read.
        events = [
            _ev(
                "assistant",
                tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),),
            )
        ]
        assert "waste-blind-edit" in _labels_at(events, 0)

    def test_edit_after_read_not_blind(self) -> None:
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Read", input={"file_path": "x.py"}),)),
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
        ]
        assert "waste-blind-edit" not in _labels_at(events, 1)

    def test_restate(self) -> None:
        events = [_ev("user", "我的意思是先读再改，不是直接写")]
        assert "waste-restate" in _labels_at(events, 0)

    def test_direction_alongside_wrong_layer(self) -> None:
        events = [_ev("user", "这不是匹配是推理，换个思路")]
        labels = _labels_at(events, 0)
        assert {"degen-wrong-layer", "waste-direction"} <= labels

    def test_rework_alongside_stops_at_works(self) -> None:
        events = [
            _ev("assistant", "完成了。"),
            _ev(
                "assistant",
                tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),),
            ),
        ]
        assert "waste-rework" in _labels_at(events, 0)
        assert "waste-rework" in _labels_at(events, 1)

    def test_reversal_action(self) -> None:
        """Same file edited twice with correction in between → waste-reversal."""
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
            _ev("user", "不对，这里改错了"),
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
        ]
        assert "waste-reversal" in _labels_at(events, 2)

    def test_reversal_not_triggered_without_correction(self) -> None:
        """Same file edited twice but no correction between → no reversal."""
        events = [
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
            _ev("user", "继续"),
            _ev("assistant", tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),)),
        ]
        assert "waste-reversal" not in _labels_at(events, 2)

    def test_handoff_firefighting_correction_after(self) -> None:
        """Switch + user pushback in next N events → waste-handoff."""
        events = [
            _ev("user", is_handoff=True),
            _ev("assistant", "here's the code"),
            _ev("user", "不对，这不是我要的"),
        ]
        assert "waste-handoff" in _labels_at(events, 0)

    def test_handoff_cross_verify_explicit(self) -> None:
        """Switch + verification intent → eng-cross-verify (positive)."""
        events = [
            _ev("user", is_handoff=True),
            _ev("assistant", "done"),
            _ev("user", "验证一下结果是否正确"),
        ]
        assert "eng-cross-verify" in _labels_at(events, 0)
        assert "waste-handoff" not in _labels_at(events, 0)

    def test_handoff_cross_verify_ab_falsify(self) -> None:
        """Switch + A/B comparison intent → eng-cross-verify."""
        events = [
            _ev("user", is_handoff=True),
            _ev("user", "对比一下两个 agent 的输出"),
        ]
        assert "eng-cross-verify" in _labels_at(events, 0)

    def test_handoff_neutral_no_labels(self) -> None:
        """Switch + no correction/verify in window → neutral (normative)."""
        events = [
            _ev("user", is_handoff=True),
            _ev("assistant", "继续实现"),
            _ev("user", "继续"),
        ]
        labels = _labels_at(events, 0)
        assert "waste-handoff" not in labels
        assert "eng-cross-verify" not in labels

    def test_handoff_firefighting_takes_priority_over_verify(self) -> None:
        """If both correction AND verify appear, correction wins (it's still firefighting)."""
        events = [
            _ev("user", is_handoff=True),
            _ev("user", "验证一下"),
            _ev("user", "不对，方向错了"),
        ]
        assert "waste-handoff" in _labels_at(events, 0)
        assert "eng-cross-verify" not in _labels_at(events, 0)


# --------------------------------------------------------------------------- #
# Multi-label & structural
# --------------------------------------------------------------------------- #


class TestMultiLabel:
    def test_event_can_carry_many_labels(self) -> None:
        events = [
            _ev("assistant", "完成了。"),
            _ev(
                "user",
                "不对，这不是匹配是推理，换个思路",
                is_handoff=True,
            ),
        ]
        labeled = extract(events)
        # The handoff event can carry direction + handoff + intuition.
        lbls = labeled[1].label_values
        assert "waste-handoff" in lbls
        assert "degen-wrong-layer" in lbls
        assert "waste-direction" in lbls

    def test_original_order_preserved(self) -> None:
        events = [
            _ev("user", "hello"),
            _ev("assistant", "hi"),
            _ev("user", "继续"),
        ]
        labeled = extract(events)
        assert [le.event.text for le in labeled] == ["hello", "hi", "继续"]


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


class TestEdgeCases:
    def test_empty_input(self) -> None:
        assert extract([]) == []

    def test_no_labels_for_neutral_text(self) -> None:
        events = [_ev("user", "请实现这个功能")]
        labeled = extract(events)
        # No activation, no waste, no response pattern.
        assert labeled[0].label_values == frozenset()

    def test_labeled_event_is_frozen(self) -> None:
        import pytest

        events = [_ev("user", "继续")]
        le = extract(events)[0]
        with pytest.raises((AttributeError, TypeError)):
            le.event = events[0]  # type: ignore[misc]
