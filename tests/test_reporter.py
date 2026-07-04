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
from observer.reporter import generate_html_report, generate_profile, generate_report
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
        )
        profile = generate_profile(_make_report(), [], episodes=[episode])

        assert profile["episode_summary"]["total"] == 1
        assert profile["episode_summary"]["loop_quality_counts"] == {"closed_verified": 1}
        assert profile["episode_summary"]["goal_quality_counts"] == {"task_like": 1}
        assert profile["episode_summary"]["goal_extraction_counts"] == {"raw_goal": 1}
        assert profile["episode_summary"]["diagnostic_signal_counts"] == {}
        assert profile["episodes"][0]["goal"] == "请实现导出功能"
        assert profile["episodes"][0]["goal_quality"] == "task_like"
        assert profile["episodes"][0]["normalized_goal"] == "请实现导出功能"
        assert profile["episodes"][0]["goal_extraction_method"] == "raw_goal"
        assert profile["episodes"][0]["diagnostic_signals"] == []

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
        assert ".analysis-profile.json" in html
        assert "consulting_routes" in html
        assert "动态咨询路线" in html
        assert "协作类型速写" in html
        assert "MBTI" not in html
        assert "弱目标启动型" in html
        assert "验收后置型" in html
        assert "宏大目标滞留型" in html
        assert "验证激活型" in html
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
