"""Tests for the Reporter (report.md + profile.json generation).

Validates: six-section report + checklist + profile.json.
Uses synthetic Aggregator Report and Anomaly list.
"""

from __future__ import annotations

import json

from observer.aggregator import AgentBreakdown, ProjectSummary, Report
from observer.anomaly import Anomaly, AnomalyKind
from observer.diagnostic_engine import Diagnosis
from observer.episode import EpisodeSummary
from observer.extractor import LabeledEvent
from observer.ir import IREvent
from observer.reporter import (
    generate_html_report,
    generate_profile,
    generate_report,
    generate_share_card_svg,
)
from observer.taxonomy import ResponsePattern


def _make_report() -> Report:
    ps = ProjectSummary(
        project="alpha",
        cwd="/p/alpha",
        event_count=50,
        label_counts={
            "degen-intuition": 5,
            "degen-tool-fail": 3,
            "act-first-principle": 8,
            "act-passive": 4,
            "waste-rework": 6,
            "waste-handoff": 2,
            "eng-verify": 10,
            "degen-fixation": 9,
        },
        degenerate_count=8,
        waste_total=8,
        handoff_count=2,
        user_event_count=25,
        assistant_event_count=25,
    )
    ab1 = AgentBreakdown(
        agent="claude", event_count=30,
        label_counts={"degen-intuition": 5}, degenerate_count=5,
    )
    ab2 = AgentBreakdown(
        agent="codex", event_count=20,
        label_counts={"degen-tool-fail": 3}, degenerate_count=3,
    )
    return Report(
        project_summaries=[ps],
        agent_breakdowns=[ab1, ab2],
        global_label_counts={
            "degen-intuition": 5, "degen-tool-fail": 3,
            "act-first-principle": 8, "act-passive": 4,
            "waste-rework": 6, "waste-handoff": 2,
            "eng-verify": 10, "degen-fixation": 9,
        },
        total_events=50, total_projects=1, total_handoffs=2,
        top_waste_projects=[("alpha", 8)],
        top_degenerate_projects=[("alpha", 8)],
        label_by_agent={
            "claude": {"degen-intuition": 5},
            "codex": {"degen-tool-fail": 3},
        },
    )


def _make_anomalies() -> list[Anomaly]:
    ev = IREvent(
        ts="2026-06-28T13:00:00Z",
        source_agent="claude", cwd="/p/alpha", project="alpha",
        role="user", text="不对，这不是匹配是推理",
    )
    le = LabeledEvent(event=ev, labels=frozenset({ResponsePattern.DEGEN_WRONG_LAYER}))
    return [
        Anomaly(
            kind=AnomalyKind.HANDOFF_DENSE,
            project="alpha",
            description="High handoff density (4 switches)",
            events=(le,),
            metric_value=4.0,
        ),
    ]


class TestGenerateReport:
    def test_has_all_six_sections(self) -> None:
        md = generate_report(_make_report(), _make_anomalies())
        assert "## 一、全景" in md
        assert "## 二、LLM 退化模式诊断" in md
        assert "## 三、有效激活手法" in md
        assert "## 四、最速线偏差定位" in md
        assert "## LLM 工程化思考检查清单" in md
        assert "## 六、异常点详解" in md

    def test_overview_contains_totals(self) -> None:
        md = generate_report(_make_report(), [])
        assert "总项目: **1**" in md
        assert "总交互事件: **50**" in md

    def test_degenerate_table_has_all_defects(self) -> None:
        md = generate_report(_make_report(), [])
        for lbl in [
            "degen-intuition", "degen-stops-at-works",
            "degen-knowledge-as-ability", "degen-wrong-layer",
            "degen-ignore-lifecycle", "degen-tool-fail",
        ]:
            assert lbl in md

    def test_agent_comparison_present(self) -> None:
        md = generate_report(_make_report(), [])
        assert "claude" in md
        assert "codex" in md

    def test_activation_rate_computed(self) -> None:
        md = generate_report(_make_report(), [])
        assert "67%" in md

    def test_anomaly_events_embedded(self) -> None:
        md = generate_report(_make_report(), _make_anomalies())
        assert "这不是匹配是推理" in md
        assert "degen-wrong-layer" in md
        assert "异常 1" in md

    def test_empty_anomalies_section(self) -> None:
        md = generate_report(_make_report(), [])
        assert "（无异常点）" in md

    def test_title_suffix(self) -> None:
        md = generate_report(_make_report(), [], title_suffix="2026-06")
        assert "2026-06" in md


class TestGenerateProfile:
    def test_profile_has_required_keys(self) -> None:
        profile = generate_profile(_make_report(), _make_anomalies())
        assert profile["version"] == "0.1.0"
        assert profile["total_events"] == 50
        assert "label_distribution" in profile
        assert "anomalies" in profile
        assert "consulting_routes" in profile
        json.dumps(profile)

    def test_anomalies_in_profile(self) -> None:
        profile = generate_profile(_make_report(), _make_anomalies())
        assert len(profile["anomalies"]) == 1
        assert profile["anomalies"][0]["kind"] == AnomalyKind.HANDOFF_DENSE

    def test_effective_activations_sorted(self) -> None:
        profile = generate_profile(_make_report(), [])
        acts = profile["effective_activations"]
        assert acts[0]["activation"] == "act-first-principle"

    def test_checklist_structured(self) -> None:
        profile = generate_profile(_make_report(), [])
        assert len(profile["checklist"]) == 5

    def test_profile_includes_positive_share_card(self) -> None:
        profile = generate_profile(_make_report(), [])
        card = profile["share_card"]

        assert set(card) == {
            "title",
            "language",
            "score",
            "score_label",
            "headline",
            "subtitle",
            "achievements",
            "title_pool",
            "llm_title_prompt",
            "cta",
            "note",
        }
        assert card["title"] == "验证洁癖型 Vibe Coder"
        assert card["language"] == "zh"
        assert 0 <= card["score"] <= 100
        assert card["score_label"] == "本次高光指数"
        assert "能跑就行" in card["headline"]
        assert card["subtitle"] == "气氛组排名，仅供开心。"
        assert card["cta"] == "测测你的 AI 搭子人格"
        assert "这张卡只负责让你开心一下" in card["note"]
        assert "Prompt 玄学家" in card["title_pool"]
        assert "重写夸夸卡称号" in card["llm_title_prompt"]
        assert len(card["achievements"]) == 3
        assert card["achievements"][0]["title"] == "测试洁癖患者"
        assert "10 次主动验证" in card["achievements"][0]["evidence"]
        assert "degen-" not in json.dumps(card, ensure_ascii=False)
        assert "waste-" not in json.dumps(card, ensure_ascii=False)

    def test_profile_can_emit_english_share_card(self) -> None:
        profile = generate_profile(_make_report(), [], report_language="en")
        card = profile["share_card"]

        assert profile["report_language"] == "en"
        assert card["language"] == "en"
        assert card["title"] == "Proof-First Vibe Coder"
        assert card["score_label"] == "Highlight Score"
        assert "ship-it-and-pray" in card["headline"]
        assert card["subtitle"] == "Vibes leaderboard. For fun only."
        assert card["cta"] == "Find your AI pair persona"
        assert "Prompt DJ" in card["title_pool"]
        assert "Rewrite the share-card title" in card["llm_title_prompt"]
        assert card["achievements"][0]["title"] == "Verification Addict"

    def test_share_card_svg_is_self_contained(self) -> None:
        profile = generate_profile(_make_report(), [])

        svg = generate_share_card_svg(profile)

        assert svg.startswith("<svg ")
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert "VibeCoding Observer 夸夸卡" in svg
        assert "验证洁癖型" in svg
        assert "Vibe Coder" in svg
        assert "本次高光指数" in svg
        assert "你击败了" in svg
        assert "气氛组排名" in svg
        assert "测测你的" in svg
        assert "AI 搭子人格" in svg
        assert "这张卡只负责" in svg
        assert "测试洁癖患者" in svg
        assert "10 次主动验证" in svg
        assert "夸夸卡像素宠物" in svg
        assert "<script" not in svg
        assert "<image" not in svg
        assert "href=" not in svg
        assert "https://" not in svg

    def test_share_card_svg_can_render_english(self) -> None:
        profile = generate_profile(_make_report(), [], report_language="en")

        svg = generate_share_card_svg(profile)

        assert 'aria-label="VibeCoding Observer share card"' in svg
        assert "VibeCoding Observer Share Card" in svg
        assert "Proof-First" in svg
        assert "Highlight Score" in svg
        assert "Vibes leaderboard" in svg
        assert "Find your" in svg
        assert "AI pair persona" in svg
        assert "Verification Addict" in svg
        assert "测试洁癖" not in svg

    def test_profile_includes_episode_summaries_when_provided(self) -> None:
        episode = EpisodeSummary(
            project="alpha",
            cwd="/p/alpha",
            start_ts="2026-06-28T13:00:00Z",
            end_ts="2026-06-28T13:02:00Z",
            start_index=0,
            end_index=3,
            event_count=4,
            goal="请实现导出功能",
            constraints=("必须有 pytest",),
            implementation_count=1,
            verification_count=1,
            correction_count=0,
            closure_count=1,
            code_implementation_count=1,
        )
        profile = generate_profile(_make_report(), [], episodes=[episode])

        assert profile["episode_summary"]["total"] == 1
        assert profile["episode_summary"]["emitted_total"] == 1
        assert profile["episode_summary"]["analyzed_total"] == 1
        assert profile["episode_summary"]["loop_quality_counts"] == {"implementation_closed": 1}
        assert profile["episode_summary"]["goal_quality_counts"] == {"task_like": 1}
        assert profile["episode_summary"]["goal_extraction_counts"] == {"raw_goal": 1}
        assert profile["episode_summary"]["diagnostic_signal_counts"] == {}
        assert profile["episodes"][0]["goal"] == "请实现导出功能"
        assert profile["episodes"][0]["goal_quality"] == "task_like"
        assert profile["episodes"][0]["normalized_goal"] == "请实现导出功能"
        assert profile["episodes"][0]["goal_extraction_method"] == "raw_goal"
        assert profile["episodes"][0]["confidence"] == "high"
        assert "governance_signal_count" in profile["episodes"][0]
        assert "coderail_count" not in profile["episodes"][0]
        assert profile["episodes"][0]["diagnostic_signals"] == []

    def test_episode_summary_total_matches_emitted_episode_array_when_capped(self) -> None:
        episodes = [
            EpisodeSummary(
                project="alpha",
                cwd="/p/alpha",
                start_ts="2026-06-28T13:00:00Z",
                end_ts="2026-06-28T13:02:00Z",
                start_index=idx,
                end_index=idx,
                event_count=idx + 1,
                goal=f"请实现功能 {idx}",
                constraints=(),
                implementation_count=0,
                verification_count=0,
                correction_count=0,
                closure_count=0,
            )
            for idx in range(61)
        ]

        profile = generate_profile(_make_report(), [], episodes=episodes)

        assert len(profile["episodes"]) == 50
        assert profile["episode_summary"]["total"] == len(profile["episodes"])
        assert profile["episode_summary"]["emitted_total"] == 50
        assert profile["episode_summary"]["analyzed_total"] == 61

    def test_design_closed_counts_as_activation_efficacy(self) -> None:
        episode = EpisodeSummary(
            project="alpha",
            cwd="/p/alpha",
            start_ts="2026-06-28T13:00:00Z",
            end_ts="2026-06-28T13:02:00Z",
            start_index=0,
            end_index=3,
            event_count=4,
            goal="请完成 ADR",
            constraints=(),
            implementation_count=1,
            verification_count=0,
            correction_count=0,
            closure_count=1,
            docs_implementation_count=1,
            governance_signal_count=1,
        )

        profile = generate_profile(_make_report(), [], episodes=[episode])

        assert {
            "activation": "act-design-closure",
            "count": 1,
            "source": "episode_loop_quality",
        } in profile["effective_activations"]

    def test_profile_prioritizes_high_quality_episode_goals(self) -> None:
        weak = EpisodeSummary(
            project="alpha",
            cwd="/p/alpha",
            start_ts="2026-06-28T13:00:00Z",
            end_ts="2026-06-28T13:02:00Z",
            start_index=0,
            end_index=99,
            event_count=100,
            goal="a",
            constraints=(),
            implementation_count=0,
            verification_count=0,
            correction_count=0,
            closure_count=0,
        )
        task = EpisodeSummary(
            project="alpha",
            cwd="/p/alpha",
            start_ts="2026-06-28T13:03:00Z",
            end_ts="2026-06-28T13:04:00Z",
            start_index=100,
            end_index=104,
            event_count=5,
            goal="请检查 API contract 是否漂移",
            constraints=(),
            implementation_count=0,
            verification_count=0,
            correction_count=0,
            closure_count=0,
        )

        profile = generate_profile(_make_report(), [], episodes=[weak, task])

        assert profile["episode_summary"]["goal_quality_counts"] == {
            "task_like": 1,
            "weak": 1,
        }
        assert profile["episode_summary"]["diagnostic_signal_counts"] == {
            "long_goal_only_episode": 1,
            "unusable_goal": 1,
            "weak_goal": 1,
        }
        assert profile["episodes"][0]["goal"] == "请检查 API contract 是否漂移"

    def test_profile_generates_consulting_routes_from_diagnoses(self) -> None:
        diagnosis = Diagnosis(
            title="顶层目标存在但工程闭环缺失",
            severity="warning",
            root_cause="有目标但缺少执行闭环",
            recommendation="补目标-约束-验收闭环",
            signals=["episode_signal: top_level_goal_without_engineering_loop=12"],
        )

        profile = generate_profile(_make_report(), [], diagnoses=[diagnosis])
        routes = profile["consulting_routes"]

        assert routes[0]["title"] == "把项目目标转成可执行工程闭环"
        assert routes[0]["source"] == "diagnosis"
        assert routes[0]["why_this_route"] == [
            "diagnosis: 顶层目标存在但工程闭环缺失",
            "episode_signal: top_level_goal_without_engineering_loop=12",
        ]
        assert "Definition of Done" in routes[0]["what_i_can_produce"]
        assert routes[0]["consulting_output"]["output_type"] == "project_start_prompt"
        assert "验收标准" in routes[0]["consulting_output"]["sections"]
        assert routes[0]["consulting_output"]["starter_questions"]
        assert routes[0]["consulting_output"]["completion_criteria"]
        assert profile["diagnoses"][0]["confidence"] == "medium"
        assert profile["diagnoses"][0]["uncertainty_reasons"] == []

    def test_html_report_shows_signal_profile_risk_and_diagnosis_confidence(self) -> None:
        diagnosis = Diagnosis(
            title="实现后验证/收束不足",
            severity="warning",
            root_cause="当前 profile 下未识别到闭环",
            recommendation="补 observer.yaml",
            signals=["implementation_without_verification=12"],
            confidence="low",
            uncertainty_reasons=["possible_unconfigured_project_profile"],
        )
        profile = generate_profile(
            _make_report(),
            [],
            diagnoses=[diagnosis],
            signal_config={
                "profile_names": ["generic"],
                "confidence_hint": "low",
                "unrecognized_keys": ["custom_done_marker"],
                "auto_detected_profiles": [],
            },
        )

        html = generate_html_report(profile)

        assert "诊断置信度与未识别规范风险" in html
        assert "置信度：low" in html
        assert "custom_done_marker" in html

    def test_profile_generates_consulting_routes_from_episode_signals(self) -> None:
        episode = EpisodeSummary(
            project="alpha",
            cwd="/p/alpha",
            start_ts="2026-06-28T13:00:00Z",
            end_ts="2026-06-28T13:10:00Z",
            start_index=0,
            end_index=80,
            event_count=81,
            goal="请先分析整个项目架构和执行路径",
            constraints=(),
            implementation_count=0,
            verification_count=0,
            correction_count=0,
            closure_count=0,
        )

        profile = generate_profile(_make_report(), [], episodes=[episode])
        titles = [route["title"] for route in profile["consulting_routes"]]

        assert "恢复项目方向和控制" in titles
        assert any(
            "top_level_goal_without_engineering_loop=1" in signal
            for route in profile["consulting_routes"]
            for signal in route["why_this_route"]
        )
        route = next(
            route
            for route in profile["consulting_routes"]
            if route["title"] == "恢复项目方向和控制"
        )
        assert route["consulting_output"]["output_type"] == "mid_project_recovery_plan"

    def test_profile_fallback_routes_include_consulting_output(self) -> None:
        empty_report = Report(
            project_summaries=[],
            agent_breakdowns=[],
            global_label_counts={},
            total_events=0,
            total_projects=0,
            total_handoffs=0,
            top_waste_projects=[],
            top_degenerate_projects=[],
            label_by_agent={},
        )

        profile = generate_profile(empty_report, [])
        route = profile["consulting_routes"][0]

        assert route["source"] == "fallback"
        assert route["consulting_output"]["output_type"] == "project_preflight"
        assert "第一轮任务" in route["consulting_output"]["sections"]

    def test_consulting_routes_follow_profile_contract(self) -> None:
        diagnosis = Diagnosis(
            title="数据生命周期混淆",
            severity="warning",
            root_cause="临时产物和长期资产混用",
            recommendation="先画数据生命周期",
            signals=["degen-ignore-lifecycle=7", "project_type=complex-app"],
        )

        profile = generate_profile(_make_report(), [], diagnoses=[diagnosis])

        for route in profile["consulting_routes"]:
            assert set(route) == {
                "title",
                "why_this_route",
                "what_i_can_produce",
                "consulting_output",
                "source",
                "priority",
            }
            assert isinstance(route["title"], str) and route["title"]
            assert isinstance(route["why_this_route"], list)
            assert 1 <= len(route["why_this_route"]) <= 3
            assert all(isinstance(signal, str) and signal for signal in route["why_this_route"])
            assert isinstance(route["what_i_can_produce"], str)
            assert isinstance(route["source"], str) and route["source"]
            assert isinstance(route["priority"], int)

            output = route["consulting_output"]
            assert set(output) == {
                "output_type",
                "sections",
                "starter_questions",
                "completion_criteria",
            }
            assert isinstance(output["output_type"], str) and output["output_type"]
            assert isinstance(output["sections"], list) and output["sections"]
            assert isinstance(output["starter_questions"], list)
            assert output["starter_questions"]
            assert isinstance(output["completion_criteria"], list)
            assert output["completion_criteria"]
            assert all(isinstance(section, str) and section for section in output["sections"])
            assert all(
                isinstance(question, str) and question
                for question in output["starter_questions"]
            )
            assert all(
                isinstance(criterion, str) and criterion
                for criterion in output["completion_criteria"]
            )


class TestGenerateHtmlReport:
    def test_html_report_is_self_contained_user_deliverable(self) -> None:
        diagnosis = Diagnosis(
            title="任务入口目标质量偏弱",
            severity="warning",
            root_cause="大量 episode 的起点是弱目标",
            recommendation="补齐目标、边界和验收",
            signals=["weak_goal=334", "metadata_goal=282"],
        )
        profile = generate_profile(_make_report(), _make_anomalies(), diagnoses=[diagnosis])

        html = generate_html_report(profile)

        assert html.startswith("<!doctype html>")
        assert "VibeCoding Observer 可视化诊断报告" in html
        assert "代码生成的诊断宠物头像" in html
        assert "诊断宠物，会根据本次报告的状态换颜色和表情" in html
        assert '<svg class="pet-svg"' in html
        assert 'shape-rendering="crispEdges"' in html
        assert '<rect x="22" y="22" width="6" height="6"' in html
        assert '<div class="mini-pet">' in html
        assert "<img" not in html
        assert ".png" not in html
        assert ".analysis-profile.json" in html
        assert "consulting_routes" in html
        assert "可截图分享的夸夸卡" in html
        assert "VibeCoding Observer 夸夸卡" in html
        assert "验证洁癖型 Vibe Coder" in html
        assert "本次高光指数" in html
        assert "你击败了" in html
        assert "气氛组排名，仅供开心。" in html
        assert "测测你的 AI 搭子人格" in html
        assert "测试洁癖患者" in html
        assert "10 次主动验证" in html
        assert "这张卡只负责让你开心一下" in html
        assert "github.com/HaipingShi/vibecoding-observer" not in html
        assert "你的 vibe coding 协作画像" in html
        assert "一句话结论" in html
        assert "你做得好的地方" in html
        assert "最拖慢你的 3 个问题" in html
        assert "优先级行动" in html
        assert "开发者附录：内部标签、置信度和原始信号" in html
        assert "你是强目标驱动的 AI 协作者" in html
        assert "你已经能让 AI 产出代码，但主要损耗发生在" in html
        assert "你会要求 AI 验证结果" in html
        assert "任务入口太省字" in html
        assert "请先复述我的目标，再开始做。" in html
        assert "下一次对话就改" in html
        assert "MBTI" not in html
        assert "meme" not in html
        assert "AI 协作能力矩阵" in html
        assert "主动验证" in html
        assert "eng-verify" in html
        assert "声称完成前运行测试、构建、检查或人工验收。" in html
        assert "方案固着" in html
        assert "degen-fixation" in html
        assert "经常出现主动验证和对比证伪信号" in html
        assert "用户会要求先判断问题边界和硬约束" in html
        assert "已验证并收束" in html
        assert "wrong-layer and lifecycle signals" not in html
        assert "constraint-reason activations" not in html
        assert "来自诊断：" in html
        assert "原始信号" in html
        assert "目标偏弱：" in html or "顶层目标未落地：" in html
        assert "任务入口提示词模板" in html
        assert "产物类型 code" in html
        assert "task_prompt_template" in html
        assert "overflow-x:hidden" in html
        assert ".grid > *" in html
        assert "grid-template-columns:1fr auto" in html
        assert ".route-card { min-height:auto; }" in html
        assert ".persona-card { min-height:auto; }" in html
        assert "table-layout:fixed" in html
        assert "<script" not in html
        assert "<link" not in html
        assert "@import" not in html
        assert "http://" not in html
        assert "https://" not in html
        assert "src=" not in html

    def test_html_report_uses_english_shell_when_requested(self) -> None:
        profile = generate_profile(_make_report(), [], report_language="en")

        html = generate_html_report(profile)

        assert '<html lang="en">' in html
        assert "VibeCoding Observer Visual Report" in html
        assert "Screenshot-Friendly Share Card" in html
        assert "Your Vibe Coding Collaboration Profile" in html
        assert "Developer Appendix: labels, confidence, and raw signals" in html
        assert "VibeCoding Observer Share Card" in html
        assert "Proof-First Vibe Coder" in html
