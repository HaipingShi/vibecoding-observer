"""Event Extractor — tag a fused timeline with the closed vocabulary.

Operates on a single project's time-ordered interaction line (the output of
the Federator). Pure local rule-matching, zero LLM calls (Strategic Principle
#2). Each event can carry 0..N labels across the three dimensions.

Signal sources:
  - Activation labels: pure sentence-pattern / keyword matching on user text.
  - ResponsePattern labels: rule matching combining user text, assistant text,
    and tool_call outcomes, often needing adjacent-event context.
  - Waste labels: counting rework rounds, blind edits, direction corrections.

Context handling:
    Many signals are relational (e.g. "done then rework" needs the "done"
    event AND a later edit to the same artifact). The extractor therefore
    scans the whole timeline, building small sliding-window state, rather
    than deciding each event in isolation. It yields LabeledEvents preserving
    original order.

This module is deliberately deterministic and keyword-based so results are
reproducible and the rules are auditable. Tuning the keyword dictionaries
below is the main iteration point for recall.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from observer.ir import IREvent
from observer.message_classifier import MessageKind, classify_message
from observer.taxonomy import Activation, Label, ResponsePattern, Waste

__all__ = ["Extractor", "LabeledEvent", "extract"]


# --------------------------------------------------------------------------- #
# Output type
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LabeledEvent:
    """An IREvent plus the labels the extractor attached to it."""

    event: IREvent
    labels: frozenset[Label] = field(default_factory=frozenset)

    @property
    def label_values(self) -> frozenset[str]:
        """Label values as plain strings (for serialization/group-by).

        StrEnum members ARE str instances, and their str value equals the
        enum's value. So str(lbl) works for both StrEnum and plain strings.
        """
        return frozenset(str(lbl) for lbl in self.labels)


# --------------------------------------------------------------------------- #
# Keyword / pattern dictionaries (the tunable core)
# --------------------------------------------------------------------------- #

# --- Activation patterns (match against user text) -------------------------
# Bilingual: Chinese + English keyword equivalents.
_ACT_FIRST_PRINCIPLE = re.compile(
    r"人类|人看|是怎么工作|本质|第一性原理|本质上|人是怎么"
    r"|how.{0,10}(?:human|people|actually work|fundamentally)"
    r"|first principle|fundamental|essentially|under the hood",
    re.IGNORECASE,
)
# Scale-stress: user proactively stresses an extreme scale. Must require a
# quantifier context — bare numbers (line numbers, token counts, exit codes,
# timestamps) are NOT activations.
_ACT_SCALE_STRESS = re.compile(
    # Chinese conditional + magnitude
    r"(?:如果|要是|假设|比如).{0,20}?\d{2,}\s*(?:万|千|亿|行|条|个|次|分钟|小时|GB|MB|TB|倍)"
    r"|上(?:百|万|千|亿)(?:万|千|亿|条|个|行|数据)?"
    r"|成千上万|海量|大规模|超大规模"
    r"|\d+(?:\.\d+)?\s*GB(?:以上|级别)?"
    r"|\d{4,}\s*(?:行|条|个|事件|用户|请求)"
    # English conditional + magnitude
    r"|(?:what\s+if|imagine|suppose).{0,30}?\d{3,}\s*(?:users?|rows?|files?|records?|requests?|hours?|minutes?)"
    r"|millions?\s+of|thousands?\s+of|at\s+scale|huge\s+dataset|massive"
    r"|\d+(?:\.\d+)?\s*GB\b",
    re.IGNORECASE,
)
_ACT_AB_FALSIFY = re.compile(
    r"a/b|ab\s*测试|对比|对照组|实验|实测|对照|证伪|跑一遍|跑一次"
    r"|compar[ei]|control\s+group|experi|falsif|test\s+against|benchmark"
    r"|let'?s\s+(?:test|compare|try)",
    re.IGNORECASE,
)
_ACT_CONSTRAINT_REASON = re.compile(
    r"是什么类型|什么类型|约束|前提|边界|限制|属于哪|是哪一(?:类|层)|假设"
    r"|what\s+(?:type|kind)\s+of|constraint|premise|boundary|assumpt"
    r"|which\s+layer|what\s+level",
    re.IGNORECASE,
)

# --- Engineering-response patterns (match against assistant text) ------------
_ENG_DECOMPOSE = re.compile(
    r"(?:我先?(?:来)?(?:分析|拆解|梳理|列出|枚举|分解).{0,10}?(?:子问题|步骤|方案|模块|阶段|维度))"
    r"|(?:方案[一二三四12345])"
    r"|(?:先.{0,5}?再.{0,5}?(?:然后|最后))"
    r"|(?:有几种(?:思路|方案|方向|做法))"
    r"|(?:tradeoff|权衡|利弊|优缺点)"
    r"|(?:分两步|分三步|分几步)"
    # English
    r"|(?:let'?s\s+break\s+(?:this|it)\s+down)"
    r"|(?:here\s+are\s+(?:the\s+)?(?:steps?|options?|approaches?|alternatives?))"
    r"|(?:approach\s+[123AB])"
    r"|(?:trade-?offs?|pros\s+and\s+cons|weighing\s+(?:the|up))"
    r"|(?:sub-?problems?|decompos)"
    r"|(?:first.*then.*finally)"  # sequential plan
    r"|(?:phase\s+[123])",
    re.IGNORECASE,
)
_ENG_VERIFY = re.compile(
    r"(?:跑(?:一遍|一次|一下)?\s*(?:测试|harness|pytest|单元测试|e2e|集成测试))"
    r"|(?:验证(?:一下|是否|能不能))"
    r"|(?:先写(?:测试|spec|用例))"
    r"|(?:acceptance|验收)"
    r"|(?:smoke\s*test)"
    # English
    r"|(?:run\s+(?:the\s+)?tests?|run\s+pytest|run\s+harness)"
    r"|(?:let'?s\s+(?:verify|check|validate))"
    r"|(?:write\s+tests?\s+first|test-?driven)"
    r"|(?:acceptance\s+criteria)"
    r"|(?:integration\s+test|unit\s+test)",
    re.IGNORECASE,
)

# --- Degenerate-response triggers -----------------------------------------
_USER_PUSHBACK = re.compile(
    r"不是|不对|为什么选|为什么用|不该|错了|搞错|换(?:一个|成)"
    r"|that'?s\s+(?:wrong|not\s+right|incorrect)"
    r"|no,?\s+(?:this|that|it)\s+(?:should|is|means)"
    r"|why\s+(?:did|do)\s+you\s+(?:choose|pick|use|select)"
    r"|this\s+isn'?t\s+(?:right|what\s+I\s+meant)"
    r"|don'?t\s+(?:do|use)\s+that"
    r"|start\s+over|redo\s+(?:this|that)"
    r"|not\s+what\s+I\s+(?:wanted|meant|asked)",
    re.IGNORECASE,
)
_DONE_CLAIM = re.compile(
    r"(?:^|\s)(?:完成了?|done|完成|搞定|已(?:经|完成)|实现完毕|结束)"
    r"(?:[。，.!\s]|$)"
    r"|(?:^|\s)(?:all\s+done|finished|implement(?:ed)?\s+complete|done\s+with)"
    r"(?:[.!,\s]|$)"
    r"|(?:^|\s)(?:i'?m\s+done|i'?ve\s+(?:finished|completed|implemented))"
    r"(?:[.!,\s]|$)",
    re.IGNORECASE,
)
_DIRECTION_CORRECTION = re.compile(
    r"不是.*(?:是|应该)|这不(?:是|属于).*这是|换个思路|重新来|推倒|全部删|方向(?:不对|错了)|"
    r"匹配.*推理|推理.*匹配"
    # English
    r"|this\s+is(?:n't| not)\s+a\s+\w+\s+problem,?\s*(?:it'?s|this\s+is)\s+a\s+\w+\s+problem"
    r"|wrong\s+(?:approach|layer|level|direction|abstraction)"
    r"|think\s+about\s+it\s+(?:differently|another\s+way)"
    r"|this\s+is\s+(?:reasoning|semantic|inference),?\s*not\s+(?:matching|pattern)"
    r"|not\s+(?:matching|pattern\s+match),?\s*(?:it'?s|this\s+is)\s+(?:reasoning|inference|semantic)",
    re.IGNORECASE,
)
_LIFECYCLE_QUERY = re.compile(
    r"哪些是.*(?:永久|资产)|永久.*资产|数据流|生命周期|中间产物|复用|会被几次"
    # English — require compound phrases to avoid code-identifier false positives.
    r"|which\s+(?:are|is)\s+(?:permanent|long-?lived|persistent)"
    r"|data\s+(?:flow|lifecycle|pipeline)"
    r"|intermediate\s+(?:product|artifact|result|step)"
    r"|how\s+many\s+times\s+(?:is|will|does|can)"
    r"|permanent\s+asset|long-?lived\s+asset|data\s+asset",
    re.IGNORECASE,
)
_PROMPT_INJECTION = re.compile(
    r"^(?:记住|你是|规则[:：]|从现在|你的(?:身份|角色)|设定[:：])"
    r"|(?:^(?:remember[:\s]|you\s+are|rule[:\s]|from\s+now\s+on|your\s+(?:role|identity)|act\s+as))",
    re.IGNORECASE,
)
_RESTATE_MARKERS = re.compile(
    r"我的意思是|我是说|换句话说|也就是说|重新(?:描述|说明)一下|再(?:说|讲)一遍|"
    r"具体(?:来说|就是|一点)|不是.*而是"
    # English
    r"|what\s+I\s+meant\s+(?:was|is)|I\s+mean|in\s+other\s+words|that\s+is\s+to\s+say"
    r"|let\s+me\s+(?:rephrase|clarify|explain\s+again)"
    r"|to\s+be\s+more\s+specific|more\s+precisely"
    r"|not\s+\w+,?\s+but\s+(?:rather|instead)",
    re.IGNORECASE,
)
# Acceptance markers: short positive user replies that accept LLM output
# without critical evaluation (drives instant-gratification / suggester-preference).
_ACCEPT_MARKERS = re.compile(
    r"^(?:好的?|行|可以|嗯|对|没问题|看起来不错|就这样)"
    r"|^(?:ok|okay|sure|fine|good|great|looks? good|perfect|lgtm|nice|cool|right|yeah)"
    r"(?:[.!,\s]|$)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Extractor
# --------------------------------------------------------------------------- #


class Extractor:
    """Tag a project timeline with closed-vocabulary labels.

    Stateless across projects: instantiate once, call :meth:`extract` per
    project's event list. The scan maintains sliding-window state within a
    single call (e.g. tracking the last "done" claim to detect rework).
    """

    def extract(self, events: Iterable[IREvent]) -> list[LabeledEvent]:
        """Return LabeledEvents in original order, each tagged.

        Args:
            events: A single project's time-ordered IREvent list (from
                Federator). Order is preserved; multi-pass scanning uses
                index-based lookups.

        Returns:
            One LabeledEvent per input event. Empty input → empty output.
        """
        ev_list = list(events)
        if not ev_list:
            return []

        labels_per_event: list[set[Label]] = [set() for _ in ev_list]

        self._tag_activations(ev_list, labels_per_event)
        self._tag_response_patterns(ev_list, labels_per_event)
        self._tag_waste(ev_list, labels_per_event)

        return [
            LabeledEvent(event=ev, labels=frozenset(lbls))
            for ev, lbls in zip(ev_list, labels_per_event, strict=True)
        ]

    # ----------------------------------------------------------------- #
    # Dimension 2: Activations (per-event, user text only)
    # ----------------------------------------------------------------- #
    def _tag_activations(
        self,
        events: list[IREvent],
        out: list[set[Label]],
    ) -> None:
        for i, ev in enumerate(events):
            if not _is_human_instruction(ev):
                continue
            text = ev.text
            # Passive: very short user message with no question, no constraint.
            if self._is_passive(text):
                out[i].add(Activation.ACT_PASSIVE)
                continue  # passive dominates; other activations unlikely
            if _ACT_FIRST_PRINCIPLE.search(text):
                out[i].add(Activation.ACT_FIRST_PRINCIPLE)
            if _ACT_SCALE_STRESS.search(text):
                out[i].add(Activation.ACT_SCALE_STRESS)
            if _ACT_AB_FALSIFY.search(text):
                out[i].add(Activation.ACT_AB_FALSIFY)
            if _ACT_CONSTRAINT_REASON.search(text):
                out[i].add(Activation.ACT_CONSTRAINT_REASON)

    @staticmethod
    def _is_passive(text: str) -> bool:
        stripped = text.strip()
        # Short, no question mark, no constraint keyword, no imperative verb.
        # Imperatives like "实现/做/改/加/删" indicate a directive, not passivity.
        if len(stripped) >= 12:
            return False
        if "?" in stripped or "？" in stripped:
            return False
        if re.search(
            r"实现|来做|去做|修改|改成|添加|增加|删除|去掉|修复|重构"
            r"|implement|create|build|modify|change|add|delete|remove|fix|refactor",
            stripped,
            re.IGNORECASE,
        ):
            return False
        return not bool(
            _ACT_CONSTRAINT_REASON.search(stripped)
            or _ACT_FIRST_PRINCIPLE.search(stripped)
        )

    # ----------------------------------------------------------------- #
    # Dimension 1: Response patterns (relational)
    # ----------------------------------------------------------------- #
    def _tag_response_patterns(
        self,
        events: list[IREvent],
        out: list[set[Label]],
    ) -> None:
        last_done_claim_at: int | None = None
        seen_files_edited: dict[str, int] = {}  # file -> first edit index

        for i, ev in enumerate(events):
            # Tool failure: any tool_call with result_ok False.
            if any(tc.result_ok is False for tc in ev.tool_calls):
                out[i].add(ResponsePattern.DEGEN_TOOL_FAIL)

            # Engineering-response detection (drives activation efficacy).
            if ev.role == "assistant" and ev.text:
                if _ENG_DECOMPOSE.search(ev.text):
                    out[i].add(ResponsePattern.ENG_DECOMPOSE)
                if _ENG_VERIFY.search(ev.text):
                    out[i].add(ResponsePattern.ENG_VERIFY)

            # Assistant "done" claim → record position.
            if ev.role == "assistant" and _DONE_CLAIM.search(ev.text):
                last_done_claim_at = i

            # Rework signal: an edit after a "done" claim.
            if (
                last_done_claim_at is not None
                and i > last_done_claim_at
                and self._has_edit_like_tool(ev)
            ):
                # Mark both the premature done and the rework event.
                out[last_done_claim_at].add(ResponsePattern.DEGEN_STOPS_AT_WORKS)
                out[i].add(ResponsePattern.DEGEN_STOPS_AT_WORKS)
                last_done_claim_at = None  # reset; one rework per claim

            # User pushback after a selection/tool → degen-intuition.
            if (
                _is_human_instruction(ev)
                and _USER_PUSHBACK.search(ev.text)
                and self._prev_had_selection_or_tool(events, i)
            ):
                out[i].add(ResponsePattern.DEGEN_INTUITION)

            # Knowledge-as-ability: user injects prompt rules AND a later
            # pushback appears (the injection didn't help).
            if (
                _is_human_instruction(ev)
                and _PROMPT_INJECTION.search(ev.text)
                and self._later_has_pushback(events, i)
            ):
                out[i].add(ResponsePattern.DEGEN_KNOWLEDGE_AS_ABILITY)

            # Wrong layer: user direction correction.
            if _is_human_instruction(ev) and _DIRECTION_CORRECTION.search(ev.text):
                out[i].add(ResponsePattern.DEGEN_WRONG_LAYER)

            # Ignore lifecycle: user lifecycle query.
            if _is_human_instruction(ev) and _LIFECYCLE_QUERY.search(ev.text):
                out[i].add(ResponsePattern.DEGEN_IGNORE_LIFECYCLE)

            # Track edited files for blind-edit + fixation detection.
            for tc in ev.tool_calls:
                if tc.name in ("Edit", "Write", "MultiEdit") and i not in seen_files_edited.values():
                    fp = str(tc.input.get("file_path", ""))
                    if fp:
                        seen_files_edited.setdefault(fp, i)

            # --- ICSE 2026 labels ---

            # Instant gratification: user accepts (short positive) without
            # verification, then a degen-* appears within the next 5 events.
            if (
                _is_human_instruction(ev)
                and _ACCEPT_MARKERS.search(ev.text.strip())
                and self._later_has_degen(events, out, i, window=5)
            ):
                out[i].add(ResponsePattern.DEGEN_INSTANT_GRATIFICATION)

            # Suggester preference: user blindly accepts LLM output verbatim,
            # then later corrects it. Like instant-gratification but specifically
            # the accept is of a suggestion/code block (assistant had tool_calls
            # or substantial output right before).
            if (
                _is_human_instruction(ev)
                and _ACCEPT_MARKERS.search(ev.text.strip())
                and i > 0
                and events[i - 1].role == "assistant"
                and (events[i - 1].tool_calls or len(events[i - 1].text) > 50)
                and self._later_has_pushback(events, i)
            ):
                out[i].add(ResponsePattern.DEGEN_SUGGESTER_PREFERENCE)

            # Fixation: same file edited 3+ times across the session.
            # Mark the 3rd+ edit event.
            if ev.role == "assistant":
                for tc in ev.tool_calls:
                    if tc.name in ("Edit", "Write", "MultiEdit"):
                        fp = str(tc.input.get("file_path", ""))
                        if fp:
                            edit_count = sum(
                                1
                                for j in range(i + 1)
                                if any(
                                    t.name in ("Edit", "Write", "MultiEdit")
                                    and str(t.input.get("file_path", "")) == fp
                                    for t in events[j].tool_calls
                                )
                            )
                            if edit_count >= 3:
                                out[i].add(ResponsePattern.DEGEN_FIXATION)
                                break

        _ = seen_files_edited

    @staticmethod
    def _later_has_degen(
        events: list[IREvent],
        out: list[set[Label]],
        i: int,
        window: int = 5,
    ) -> bool:
        """Check if any degenerate signal appears within the next N events.

        Scans events directly (not out[]) because out[] may not be populated
        yet for future indices during the same pass. Looks for hard signals:
        tool failures, user pushback, direction corrections.
        """
        for j in range(i + 1, min(i + 1 + window, len(events))):
            ev = events[j]
            # Tool failure (hard signal, doesn't need out[]).
            if any(tc.result_ok is False for tc in ev.tool_calls):
                return True
            # User pushback / direction correction (text-based, scan directly).
            if (
                _is_human_instruction(ev)
                and (_USER_PUSHBACK.search(ev.text) or _DIRECTION_CORRECTION.search(ev.text))
            ):
                return True
        return False

    @staticmethod
    def _has_edit_like_tool(ev: IREvent) -> bool:
        return any(
            tc.name in ("Edit", "Write", "MultiEdit", "exec_command")
            and tc.name != "exec_command"
            for tc in ev.tool_calls
        ) or any(tc.name in ("Edit", "Write", "MultiEdit") for tc in ev.tool_calls)

    @staticmethod
    def _prev_had_selection_or_tool(events: list[IREvent], i: int) -> bool:
        """Did the immediately preceding assistant turn use a tool?"""
        if i == 0:
            return False
        prev = events[i - 1]
        return prev.role == "assistant" and len(prev.tool_calls) > 0

    @staticmethod
    def _later_has_pushback(events: list[IREvent], i: int) -> bool:
        """Is there a user pushback at any index after i?"""
        for j in range(i + 1, len(events)):
            if _is_human_instruction(events[j]) and _USER_PUSHBACK.search(events[j].text):
                return True
        return False

    # ----------------------------------------------------------------- #
    # Dimension 3: Waste (relational counting)
    # ----------------------------------------------------------------- #
    def _tag_waste(
        self,
        events: list[IREvent],
        out: list[set[Label]],
    ) -> None:
        files_read: set[str] = set()
        files_edited_without_read: list[int] = []

        for i, ev in enumerate(events):
            # Track reads.
            for tc in ev.tool_calls:
                if tc.name == "Read":
                    fp = str(tc.input.get("file_path", ""))
                    if fp:
                        files_read.add(fp)

            # Blind edit: edit a file not yet read.
            for tc in ev.tool_calls:
                if tc.name in ("Edit", "Write", "MultiEdit"):
                    fp = str(tc.input.get("file_path", ""))
                    if fp and fp not in files_read:
                        out[i].add(Waste.WASTE_BLIND_EDIT)
                        files_edited_without_read.append(i)

            # Restate waste: user restatement marker.
            if _is_human_instruction(ev) and _RESTATE_MARKERS.search(ev.text):
                out[i].add(Waste.WASTE_RESTATE)

            # Direction waste: tagged alongside wrong-layer.
            if ResponsePattern.DEGEN_WRONG_LAYER in out[i]:
                out[i].add(Waste.WASTE_DIRECTION)

            # Handoff classification: not all switches are waste.
            # See handoff context (next N events) to classify:
            #   - correction after switch → waste-handoff (firefighting)
            #   - verification intent → eng-cross-verify (intentional check)
            #   - neither → neutral (normative handoff, e.g. StraTA template)

        # Reversal action detection (ICSE 2026): same file edited multiple
        # times within a 10-event window with a correction in between.
        self._tag_reversals(events, out)

        # Classify handoffs using a forward window.
        self._classify_handoffs(events, out)

        # Rework waste: tagged alongside stops-at-works.
        for lbls in out:
            if ResponsePattern.DEGEN_STOPS_AT_WORKS in lbls:
                lbls.add(Waste.WASTE_REWORK)

    # ----------------------------------------------------------------- #
    # Handoff classification
    # ----------------------------------------------------------------- #
    _HANDOFF_WINDOW = 5
    """How many events after a handoff to scan for classification signals."""

    def _classify_handoffs(
        self,
        events: list[IREvent],
        out: list[set[Label]],
    ) -> None:
        """Classify each handoff event as firefighting, cross-verify, or neutral.

        A handoff is an event where ``is_handoff=True`` (set by the Federator).
        We scan the next ``_HANDOFF_WINDOW`` events for:

          - correction signals (degen-*, user pushback, direction correction):
            → ``waste-handoff`` (the user switched because the previous
            agent went wrong — firefighting).
          - verification intent (act-ab-falsify, or explicit "check/verify"
            language from the user): → ``eng-cross-verify`` (intentional
            cross-agent verification — a positive engineering practice).
          - neither: no label (normative handoff, e.g. StraTA template-driven
            task completion handoff — neutral, not waste).
        """
        # Reuse the pushback regex for correction detection.
        for i, ev in enumerate(events):
            if not ev.is_handoff:
                continue

            window_end = min(i + 1 + self._HANDOFF_WINDOW, len(events))
            has_correction = False
            has_verify_intent = False

            # Check the handoff event's own text first — the user often
            # states the reason for switching right at the handoff point.
            if _is_human_instruction(ev):
                if _USER_PUSHBACK.search(ev.text) or _DIRECTION_CORRECTION.search(ev.text):
                    has_correction = True
                if _ACT_AB_FALSIFY.search(ev.text) or re.search(
                    r"验证|检查|check|review|对比.*结果|交叉", ev.text, re.IGNORECASE
                ):
                    has_verify_intent = True

            # Then scan the forward window.
            for j in range(i + 1, window_end):
                w_ev = events[j]
                # Correction: user pushback or direction correction in window.
                if _is_human_instruction(w_ev) and _USER_PUSHBACK.search(w_ev.text):
                    has_correction = True
                if _is_human_instruction(w_ev) and _DIRECTION_CORRECTION.search(w_ev.text):
                    has_correction = True
                # Verify intent: explicit falsification or check language.
                if _is_human_instruction(w_ev) and _ACT_AB_FALSIFY.search(w_ev.text):
                    has_verify_intent = True
                if _is_human_instruction(w_ev) and re.search(
                    r"验证|检查|check|review|对比.*结果|交叉", w_ev.text, re.IGNORECASE
                ):
                    has_verify_intent = True

            if has_correction:
                out[i].add(Waste.WASTE_HANDOFF)
            elif has_verify_intent:
                out[i].add(ResponsePattern.ENG_CROSS_VERIFY)
            # else: neutral — no label attached.

    # ----------------------------------------------------------------- #
    # Reversal action detection (ICSE 2026)
    # ----------------------------------------------------------------- #
    _REVERSAL_WINDOW = 10

    def _tag_reversals(
        self,
        events: list[IREvent],
        out: list[set[Label]],
    ) -> None:
        """Detect reversal actions: same file edited twice+ within a window
        with a user correction (pushback/restate) between the edits.

        This is broader than waste-rework: doesn't require a done-claim.
        Captures the "edit → user says wrong → edit again" pattern.
        """
        edit_events: dict[str, list[int]] = {}  # file_path -> [event indices]

        for i, ev in enumerate(events):
            for tc in ev.tool_calls:
                if tc.name not in ("Edit", "Write", "MultiEdit"):
                    continue
                fp = str(tc.input.get("file_path", ""))
                if not fp:
                    continue
                edit_events.setdefault(fp, []).append(i)

        for _fp, indices in edit_events.items():
            if len(indices) < 2:
                continue
            for idx_pos in range(1, len(indices)):
                prev_idx = indices[idx_pos - 1]
                curr_idx = indices[idx_pos]
                if curr_idx - prev_idx > self._REVERSAL_WINDOW:
                    continue
                # Check for user correction between the two edits.
                has_correction = False
                for j in range(prev_idx + 1, curr_idx):
                    if _is_human_instruction(events[j]) and (
                        _USER_PUSHBACK.search(events[j].text)
                        or _RESTATE_MARKERS.search(events[j].text)
                    ):
                        has_correction = True
                        break
                if has_correction:
                    out[curr_idx].add(Waste.WASTE_REVERSAL)


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def extract(events: Iterable[IREvent]) -> list[LabeledEvent]:
    """One-shot extract without instantiating."""
    return Extractor().extract(events)


def _is_human_instruction(event: IREvent) -> bool:
    return classify_message(event) == MessageKind.HUMAN_INSTRUCTION
