"""Reporter — render the analysis report + profile.json for agent consumption.

Consumes the Aggregator's Report and the Anomaly Detector's Anomaly list.
The report is the *input* for the consuming agent — Section VI embeds actual
anomalous event fragments so the agent (which IS an LLM) reads them directly
and produces insights. No separate LLM analyzer module needed.
"""

from __future__ import annotations

import contextlib
from html import escape
from typing import Any

from observer.aggregator import Report
from observer.anomaly import Anomaly
from observer.checklist import CHECKLIST_ITEMS, render_checklist
from observer.diagnostic_engine import Diagnosis
from observer.efficiency import EfficiencyProfile, classify_efficiency
from observer.episode import EpisodeSummary
from observer.git_analyzer import GitMetrics
from observer.project_scanner import ProjectProfile

__all__ = ["generate_html_report", "generate_profile", "generate_report"]


def generate_report(
    report: Report,
    anomalies: list[Anomaly],
    title_suffix: str = "",
    diagnoses: list[Diagnosis] | None = None,
    project: ProjectProfile | None = None,
    git: GitMetrics | None = None,
) -> str:
    title = "# 协作工程化效能分析报告"
    if title_suffix:
        title += f" — {title_suffix}"
    sections = [title, ""]

    if diagnoses or project or git:
        sections.append(_section_diagnostic_overview(report, project, git, diagnoses))

    sections.extend([
        _section_overview(report),
        _section_degenerate(report),
        _section_activations(report),
        _section_waste(report),
        _section_checklist(),
        _section_anomalies(anomalies),
    ])

    if diagnoses:
        sections.append(_section_diagnoses(diagnoses))

    return "\n\n".join(sections) + "\n"


def _section_overview(r: Report) -> str:
    lines = [
        "## 一、全景",
        "",
        f"- 总项目: **{r.total_projects}**",
        f"- 总交互事件: **{r.total_events}**",
        f"- 总 cross-agent handoff: **{r.total_handoffs}**",
        f"- Agent 分布: {_agent_summary(r)}",
        f"- 协作类型: **{r.developer_type}**",
    ]
    top_labels = sorted(r.global_label_counts.items(), key=lambda x: -x[1])[:10]
    if top_labels:
        lines += ["", "标签 Top 10:", "", "| 标签 | 次数 |", "|------|------|"]
        for lbl, cnt in top_labels:
            lines.append(f"| `{lbl}` | {cnt} |")
    return "\n".join(lines)


def _section_degenerate(r: Report) -> str:
    lines = [
        "## 二、LLM 退化模式诊断",
        "",
        "缺陷出现次数:",
        "",
        "| 缺陷 | 次数 |",
        "|------|------|",
    ]
    for lbl in [
        "degen-intuition",
        "degen-stops-at-works",
        "degen-knowledge-as-ability",
        "degen-wrong-layer",
        "degen-ignore-lifecycle",
        "degen-tool-fail",
        "degen-instant-gratification",
        "degen-suggester-preference",
        "degen-fixation",
    ]:
        lines.append(f"| `{lbl}` | {r.label_count(lbl)} |")
    if len(r.agent_breakdowns) > 1:
        lines += ["", "Agent 维度对比:", "", "| Agent | 事件数 | 退化次数 |", "|-------|--------|---------|"]
        for ab in r.agent_breakdowns:
            lines.append(f"| {ab.agent} | {ab.event_count} | {ab.degenerate_count} |")
    return "\n".join(lines)


def _section_activations(r: Report) -> str:
    lines = [
        "## 三、有效激活手法",
        "",
        "四种激活模式使用次数:",
        "",
        "| 激活模式 | 次数 |",
        "|---------|------|",
    ]
    act_labels = [
        "act-first-principle",
        "act-scale-stress",
        "act-ab-falsify",
        "act-constraint-reason",
        "act-passive",
    ]
    for lbl in act_labels:
        lines.append(f"| `{lbl}` | {r.label_count(lbl)} |")
    total_act = sum(r.label_count(lbl) for lbl in act_labels if lbl != "act-passive")
    total_passive = r.label_count("act-passive")
    if total_act + total_passive > 0:
        rate = total_act / (total_act + total_passive)
        lines += ["", f"主动激活占比: **{rate:.0%}** (主动 {total_act} / 被动 {total_passive})"]
    return "\n".join(lines)


def _section_waste(r: Report) -> str:
    lines = [
        "## 四、最速线偏差定位",
        "",
        "浪费类型分布:",
        "",
        "| 类型 | 次数 |",
        "|------|------|",
    ]
    for lbl in ["waste-restate", "waste-rework", "waste-blind-edit", "waste-direction", "waste-handoff", "waste-reversal"]:
        lines.append(f"| `{lbl}` | {r.label_count(lbl)} |")
    if r.top_waste_projects:
        lines += ["", "浪费最严重的项目 Top 5:", "", "| 项目 | 浪费总量 |", "|------|---------|"]
        for proj, cnt in r.top_waste_projects[:5]:
            lines.append(f"| {proj} | {cnt} |")
    return "\n".join(lines)


def _section_checklist() -> str:
    return render_checklist()


def _section_anomalies(anomalies: list[Anomaly]) -> str:
    """Section VI — anomalous event slices for the consuming agent to read.

    Embeds actual interaction fragments so the agent (IS an LLM) reads them
    directly and produces insights. No separate LLM call needed.
    """
    lines = [
        "## 六、异常点详解",
        "",
        "> 以下是统计筛选出的高信号交互片段。请逐个阅读，分析其中的"
        "工程化思考偏差模式，给出改进建议。",
        "",
    ]
    if not anomalies:
        lines.append("（无异常点）")
        return "\n".join(lines)
    for i, anomaly in enumerate(anomalies, 1):
        lines.append(f"### 异常 {i}: `{anomaly.kind}` — {anomaly.project}")
        lines.append("")
        lines.append(f"**描述**: {anomaly.description}")
        if anomaly.metric_value:
            lines.append(f"**指标值**: {anomaly.metric_value:.2f}")
        lines.append("")
        if anomaly.events:
            lines.append("**交互片段**:")
            lines.append("```")
            for j, le in enumerate(anomaly.events[:8], 1):
                role = le.event.role.upper()
                agent = le.event.source_agent
                labels = ", ".join(sorted(le.label_values)) if le.label_values else "-"
                text = le.event.text.strip()[:300] if le.event.text else "(no text)"
                lines.append(f"[{j}] {role} ({agent}) labels=[{labels}]")
                lines.append(f"    {text}")
            if len(anomaly.events) > 8:
                lines.append(f"    ... ({len(anomaly.events) - 8} more events)")
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _agent_summary(r: Report) -> str:
    if not r.agent_breakdowns:
        return "N/A"
    return ", ".join(f"{ab.agent}({ab.event_count})" for ab in r.agent_breakdowns)


def _section_diagnostic_overview(
    report: Report,
    project: ProjectProfile | None,
    git: GitMetrics | None,
    diagnoses: list[Diagnosis] | None,
) -> str:
    """Section 〇 — 四诊概览 (diagnostic overview from all four dimensions)."""
    lines = ["## 〇、四诊概览", ""]

    # 望 (observe)
    if project:
        lines.append("**望** (项目结构):")
        lines.append(f"- 类型: `{project.project_type}` | 语言: `{project.primary_language}`")
        lines.append(f"- 文件数: {project.total_files} | 树深: {project.file_tree_depth}")
        lines.append(f"- 约束成熟度: {project.constraint_maturity} (constraint={project.has_ai_constraint}, strata={project.strata_completeness})")
        lines.append("")

    # 闻+问 (conversation analysis)
    lines.append("**闻+问** (交互分析):")
    lines.append(f"- 协作类型: `{report.developer_type}`")
    top3 = sorted(report.global_label_counts.items(), key=lambda x: -x[1])[:3]
    lines.append(f"- 标签 Top 3: {', '.join(f'{lbl}({cnt})' for lbl, cnt in top3)}")
    lines.append("")

    # 切 (git pulse)
    if git and git.is_repo:
        eff = classify_efficiency(git, project)
        eff_profile = EfficiencyProfile(eff)
        lines.append("**切** (Git 脉象):")
        lines.append(f"- 效率画像: `{eff.value}`")
        lines.append(f"- 净增代码: {git.net_lines} 行 | commits: {git.total_commits}")
        lines.append(f"- commit/交互比: {git.commit_per_interaction:.4f}")
        lines.append(f"- 删除率: {git.deletion_ratio:.0%} | 测试占比: {git.test_line_ratio:.0%}")
        lines.append(f"- 诊断: {eff_profile.description}")
        lines.append("")

    if diagnoses:
        critical = sum(1 for d in diagnoses if d.severity == "critical")
        warning = sum(1 for d in diagnoses if d.severity == "warning")
        lines.append(f"**交叉诊断**: {len(diagnoses)} 项 ({critical} critical, {warning} warning)")
        lines.append("")

    return "\n".join(lines)


def _section_diagnoses(diagnoses: list[Diagnosis]) -> str:
    """Section 七 — 诊断与建议 (cross-diagnostic findings)."""
    lines = ["## 七、诊断与建议", ""]
    lines.append("> 以下诊断由四诊交叉规则产出。每条含根因分析和具体建议。")
    lines.append("")

    for i, d in enumerate(diagnoses, 1):
        icon = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(d.severity, "⚪")
        lines.append(f"### {icon} 诊断 {i}: {d.title}")
        lines.append("")
        lines.append(f"**严重度**: {d.severity}")
        lines.append(f"**根因**: {d.root_cause}")
        lines.append(f"**建议**: {d.recommendation}")
        if d.signals:
            lines.append(f"**信号**: {', '.join(d.signals)}")
        lines.append("")

    return "\n".join(lines)


def generate_profile(
    report: Report,
    anomalies: list[Anomaly],
    diagnoses: list[Diagnosis] | None = None,
    episodes: list[EpisodeSummary] | None = None,
) -> dict[str, Any]:
    """Generate the machine-readable profile for Phase B consumption."""
    profile: dict[str, Any] = {
        "version": "0.1.0",
        "total_events": report.total_events,
        "total_projects": report.total_projects,
        "developer_type": report.developer_type,
        "label_distribution": dict(report.global_label_counts),
        "label_by_agent": {
            agent: dict(counts) for agent, counts in report.label_by_agent.items()
        },
        "top_waste_projects": [
            {"project": p, "waste": w} for p, w in report.top_waste_projects[:10]
        ],
        "top_degenerate_projects": [
            {"project": p, "degenerate": d}
            for p, d in report.top_degenerate_projects[:10]
        ],
        "effective_activations": _effective_activation_signatures(report),
        "anomalies": [
            {
                "kind": a.kind,
                "project": a.project,
                "description": a.description,
                "metric_value": a.metric_value,
                "event_count": len(a.events),
                "event_labels": sorted(
                    {lbl for le in a.events for lbl in le.label_values}
                ),
            }
            for a in anomalies
        ],
        "checklist": [
            {"title": t, "question": q, "prevents": p}
            for t, q, p in CHECKLIST_ITEMS
        ],
    }

    if episodes is not None:
        profile["episode_summary"] = _episode_summary(episodes)
        profile["episodes"] = [
            ep.to_dict()
            for ep in sorted(
                episodes,
                key=lambda e: (_goal_quality_rank(e), e.event_count),
                reverse=True,
            )[:50]
        ]

    if diagnoses:
        profile["diagnoses"] = [
            {
                "title": d.title,
                "severity": d.severity,
                "root_cause": d.root_cause,
                "recommendation": d.recommendation,
                "signals": d.signals,
            }
            for d in diagnoses
        ]

    profile["consulting_routes"] = _consulting_routes(
        report=report,
        diagnoses=diagnoses or [],
        episodes=episodes or [],
    )

    return profile


def generate_html_report(profile: dict[str, Any]) -> str:
    """Generate a self-contained user-facing HTML report from the profile."""
    total_events = _as_int(profile.get("total_events"))
    total_projects = _as_int(profile.get("total_projects"))
    developer_type = str(profile.get("developer_type", "unknown"))
    diagnoses = _as_list(profile.get("diagnoses"))
    routes = _as_list(profile.get("consulting_routes"))
    episode_summary = _as_dict(profile.get("episode_summary"))
    loop_counts = _as_dict(episode_summary.get("loop_quality_counts"))
    goal_counts = _as_dict(episode_summary.get("goal_quality_counts"))
    signal_counts = _as_dict(episode_summary.get("diagnostic_signal_counts"))
    episode_total = _as_int(episode_summary.get("total"))
    label_counts = _as_dict(profile.get("label_distribution"))
    label_rows = sorted(
        (
            (str(k), _as_int(v))
            for k, v in label_counts.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    waste_rows = [
        (str(item.get("project", "")), _as_int(item.get("waste")))
        for item in _as_list(profile.get("top_waste_projects"))[:8]
        if isinstance(item, dict)
    ]
    degenerate_rows = [
        (str(item.get("project", "")), _as_int(item.get("degenerate")))
        for item in _as_list(profile.get("top_degenerate_projects"))[:8]
        if isinstance(item, dict)
    ]
    route_cards = "\n".join(
        _html_route_card(route, idx)
        for idx, route in enumerate(routes[:5], 1)
        if isinstance(route, dict)
    )
    diagnosis_items = "\n".join(
        _html_diagnosis_item(item)
        for item in diagnoses[:5]
        if isinstance(item, dict)
    )
    closed_verified = _as_int(loop_counts.get("closed_verified"))
    goal_only = _as_int(loop_counts.get("goal_only"))
    closed_rate = (closed_verified / episode_total * 100) if episode_total else 0.0
    goal_only_rate = (goal_only / episode_total * 100) if episode_total else 0.0
    weak_goal = _as_int(signal_counts.get("weak_goal"))
    unusable_goal = _as_int(signal_counts.get("unusable_goal"))
    top_goal_gap = _as_int(signal_counts.get("top_level_goal_without_engineering_loop"))
    persona_strip = _html_persona_strip(
        weak_goal=weak_goal,
        unusable_goal=unusable_goal,
        goal_only=goal_only,
        top_goal_gap=top_goal_gap,
        closed_rate=closed_rate,
        verify_count=_as_int(label_counts.get("eng-verify")),
    )
    capability_rows = [
        ("验证意识", 78, "经常出现主动验证和对比证伪信号", "把验证转成完成定义。"),
        ("约束反推", 68, "用户会要求先判断问题边界和硬约束", "任务开头固定约束和禁止范围。"),
        (
            "目标入口",
            47,
            f"弱目标 {weak_goal} 次，不可执行目标 {unusable_goal} 次",
            "用目标+边界+验收替代弱指令。",
        ),
        (
            "闭环收束",
            32,
            f"已验证并收束 {closed_verified} / {episode_total} 个任务片段",
            "每轮任务必须有完成证据。",
        ),
        (
            "任务拆分",
            56,
            f"只有目标未闭环 {goal_only} 次，顶层目标未落地 {top_goal_gap} 次",
            "长 episode 强制重切任务。",
        ),
        ("抽象判断", 70, "存在抽象层级和数据生命周期相关信号", "动手前先做问题层级判断。"),
    ]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VibeCoding Observer 可视化诊断报告</title>
  <style>
    :root {{
      --bg:#f6f7f9; --panel:#fff; --ink:#17202a; --muted:#667085;
      --line:#d9dee7; --brand:#1f6feb; --good:#1f8a5b; --warn:#b7791f;
      --risk:#c2410c; --bad:#b42318; --cyan:#0e7490; --violet:#6f4fbf;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; overflow-x:hidden; background:var(--bg); color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.55; }}
    header {{ background:#111827; color:#fff; padding:30px 32px 26px; }}
    header h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,46px); line-height:1.08; letter-spacing:0; }}
    header p {{ margin:0; max-width:980px; color:#cbd5e1; }}
    nav {{ position:sticky; top:0; z-index:5; overflow-x:auto; white-space:nowrap; background:rgba(255,255,255,.94); border-bottom:1px solid var(--line); padding:10px 24px; }}
    nav a {{ display:inline-flex; color:#344054; text-decoration:none; padding:7px 10px; border-radius:6px; font-size:14px; }}
    nav a:hover {{ background:#eef4ff; color:var(--brand); }}
    main {{ max-width:1240px; margin:0 auto; padding:28px 24px 48px; }}
    section {{ margin-bottom:28px; }}
    h2 {{ margin:0 0 14px; font-size:22px; letter-spacing:0; }}
    h3 {{ margin:0 0 10px; font-size:16px; letter-spacing:0; }}
    .grid {{ display:grid; gap:14px; }}
    .grid > * {{ min-width:0; }}
    .kpi {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
    .two {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    .three {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
    .four {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
    .routes {{ grid-template-columns:repeat(5,minmax(0,1fr)); }}
    .panel {{ min-width:0; overflow-x:auto; overflow-wrap:anywhere; background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 1px 2px rgba(16,24,40,.08),0 8px 24px rgba(16,24,40,.06); padding:18px; }}
    .persona-strip {{ border:2px solid #17202a; background:#fffdf7; box-shadow:6px 6px 0 #17202a; }}
    .persona-card {{ min-height:148px; border:2px solid #17202a; border-radius:8px; background:#fff; box-shadow:4px 4px 0 #17202a; padding:14px; display:flex; flex-direction:column; gap:8px; }}
    .persona-card strong {{ font-size:17px; line-height:1.25; }}
    .persona-card p {{ margin:0; color:#475467; font-size:13px; }}
    .persona-punchline {{ margin-top:auto; border-top:1px dashed #98a2b3; padding-top:8px; color:#17202a; font-weight:720; font-size:13px; }}
    .metric .label {{ color:var(--muted); font-size:13px; margin-bottom:6px; }}
    .metric .value {{ font-size:30px; line-height:1; font-weight:720; }}
    .metric .note,.subtle {{ color:var(--muted); font-size:13px; }}
    .tag {{ display:inline-flex; border:1px solid var(--line); border-radius:999px; padding:4px 8px; background:#f8fafc; font-size:12px; margin:0 4px 6px 0; }}
    .tag.good {{ border-color:#9bd4b5; background:#edfdf4; color:#166534; }}
    .tag.warn {{ border-color:#f4d28f; background:#fff7e6; color:#8a5a00; }}
    .tag.risk {{ border-color:#f7bfa8; background:#fff1eb; color:#9a3412; }}
    .bar-list {{ display:grid; gap:10px; }}
    .bar-row {{ display:grid; grid-template-columns:minmax(160px,1.6fr) minmax(90px,1fr) 64px; gap:10px; align-items:start; font-size:13px; }}
    .bar-label {{ min-width:0; overflow:visible; white-space:normal; color:#344054; }}
    .bar-track {{ background:#eef2f7; border-radius:999px; height:10px; overflow:hidden; }}
    .bar-fill {{ height:100%; border-radius:999px; background:var(--brand); }}
    .good-fill {{ background:var(--good); }} .warn-fill {{ background:var(--warn); }} .risk-fill {{ background:var(--risk); }} .bad-fill {{ background:var(--bad); }} .cyan-fill {{ background:var(--cyan); }}
    .bar-value {{ align-self:start; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }}
    .bar-label strong {{ display:block; color:#182230; font-weight:680; line-height:1.25; }}
    .bar-label code {{ display:block; color:#344054; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; margin-top:2px; }}
    .bar-label span {{ display:block; color:var(--muted); font-size:12px; margin-top:2px; white-space:normal; }}
    .matrix {{ width:100%; table-layout:fixed; border-collapse:collapse; font-size:13px; }}
    .matrix th,.matrix td {{ border-bottom:1px solid var(--line); padding:9px 8px; text-align:left; vertical-align:top; }}
    .matrix th {{ color:#475467; background:#f8fafc; }}
    .matrix th:nth-child(2),.matrix td:nth-child(2) {{ width:62px; }}
    .matrix th,.matrix td {{ overflow-wrap:anywhere; }}
    .score {{ display:inline-flex; min-width:42px; height:24px; align-items:center; justify-content:center; border-radius:6px; color:#fff; font-weight:700; font-size:12px; }}
    .score.good {{ background:var(--good); }} .score.mid {{ background:var(--warn); }} .score.low {{ background:var(--risk); }}
    .diagnosis {{ border-left:4px solid var(--warn); padding-left:12px; margin-bottom:16px; }}
    .diagnosis strong {{ display:block; margin-bottom:4px; }}
    .signal-list {{ margin:8px 0 0; padding-left:18px; color:#475467; font-size:13px; }}
    .signal-list li {{ margin-bottom:4px; }}
    .signal-raw {{ margin-top:8px; color:var(--muted); font-size:12px; }}
    .signal-raw code {{ display:block; margin-top:4px; white-space:normal; overflow-wrap:anywhere; color:#344054; }}
    .route-card {{ display:flex; flex-direction:column; min-height:252px; gap:10px; }}
    .priority {{ width:28px; height:28px; display:inline-flex; align-items:center; justify-content:center; border-radius:50%; background:#eef4ff; color:var(--brand); font-weight:720; }}
    .route-card ul {{ margin:0; padding-left:16px; color:#475467; font-size:13px; }}
    .artifact {{ margin-top:auto; border-top:1px solid var(--line); padding-top:10px; color:#344054; font-size:13px; }}
    .callout {{ border:1px solid #b8d4ff; background:#eef6ff; border-radius:8px; padding:16px; }}
    .footer {{ color:var(--muted); font-size:12px; padding-top:18px; border-top:1px solid var(--line); }}
    @media (max-width:1100px) {{ .kpi,.routes,.three,.four {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:760px) {{ header {{ padding:24px 18px; }} nav {{ padding:8px 12px; }} nav a {{ font-size:13px; }} main {{ padding:22px 14px 36px; }} .panel {{ padding:14px; }} .persona-strip {{ box-shadow:4px 4px 0 #17202a; }} .persona-card {{ min-height:auto; }} .kpi,.two,.three,.four,.routes {{ grid-template-columns:1fr; }} .bar-row {{ grid-template-columns:1fr auto; gap:6px 10px; }} .bar-label {{ grid-column:1 / -1; }} .bar-track {{ grid-column:1; }} .bar-value {{ grid-column:2; }} .route-card {{ min-height:auto; }} .matrix th,.matrix td {{ padding:8px 6px; font-size:12px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>VibeCoding Observer 可视化诊断报告</h1>
    <p>基于 {_fmt(total_projects)} 个项目、{_fmt(total_events)} 条 AI coding agent 交互事件生成。报告目标不是给出分数，而是把 AI 协作方式转成可理解的画像、风险地图和可执行改进路线。</p>
  </header>
  <nav>
    <a href="#overview">总览</a><a href="#persona">类型速写</a><a href="#profile">协作画像</a><a href="#loop">工程闭环</a><a href="#capability">能力矩阵</a><a href="#risks">风险</a><a href="#routes">咨询路线</a><a href="#actions">行动建议</a>
  </nav>
  <main>
    <section id="overview">
      <h2>一、总览</h2>
      <div class="grid kpi">
        {_html_metric("分析项目", _fmt(total_projects), "多源融合后的项目数")}
        {_html_metric("交互事件", _fmt(total_events), "本地会话历史，无网络上传")}
        {_html_metric("任务片段", _fmt(episode_total), "用于判断目标、实现、验证、收束")}
        {_html_metric("交叉诊断", _fmt(len(diagnoses)), "诊断与建议数量")}
      </div>
    </section>
    <section id="persona" class="panel persona-strip">
      <h2>二、协作类型速写</h2>
      <div class="grid four">
        {persona_strip}
      </div>
    </section>
    <section id="profile">
      <h2>三、协作画像</h2>
      <div class="grid two">
        <div class="panel">
          <h3>{escape(developer_type)}</h3>
          <p>你更像战略型委托者：会用验证、约束和多 agent 协作推进复杂项目，但主要损耗来自高产高纠缠、任务入口不稳和工程闭环不足。</p>
          {_html_top_tags(label_rows[:5])}
        </div>
        <div class="panel">
          <h3>关键矛盾</h3>
          <p>你已经具备把 agent 拉回工程判断的能力，但任务入口和收束协议不稳定。大量 episode 有明确目标，却长期停留在讨论或动作展开。</p>
          <div class="callout"><strong>优先改善：</strong>让每个任务更快从目标进入可验证交付。</div>
        </div>
      </div>
    </section>
    <section>
      <h2>四、标签分布</h2>
      <div class="grid two">
        <div class="panel"><h3>Top 标签</h3>{_html_bar_list(label_rows, "bar-fill")}</div>
        <div class="panel"><h3>目标质量</h3>{_html_bar_list(_dict_rows(goal_counts), "warn-fill")}</div>
      </div>
    </section>
    <section id="loop">
      <h2>五、工程闭环漏斗</h2>
      <div class="grid two">
        <div class="panel">
          <h3>Loop quality</h3>
          {_html_bar_list(_dict_rows(loop_counts), "cyan-fill")}
          <p class="subtle">closed_verified: {closed_rate:.1f}%；goal_only: {goal_only_rate:.1f}%。</p>
        </div>
        <div class="panel">
          <h3>Episode diagnostic signals</h3>
          {_html_bar_list(_dict_rows(signal_counts)[:8], "risk-fill")}
        </div>
      </div>
    </section>
    <section id="capability">
      <h2>六、AI 协作能力矩阵</h2>
      <div class="panel">{_html_capability_table(capability_rows)}</div>
    </section>
    <section id="risks">
      <h2>七、风险与项目热点</h2>
      <div class="grid two">
        <div class="panel"><h3>浪费最严重项目</h3>{_html_bar_list(waste_rows, "bad-fill")}</div>
        <div class="panel"><h3>退化最严重项目</h3>{_html_bar_list(degenerate_rows, "risk-fill")}</div>
      </div>
    </section>
    <section>
      <h2>八、诊断摘要</h2>
      <div class="panel">{diagnosis_items or '<p class="subtle">暂无诊断。</p>'}</div>
    </section>
    <section id="routes">
      <h2>九、动态咨询路线</h2>
      <div class="grid routes">{route_cards or '<div class="panel">暂无咨询路线。</div>'}</div>
    </section>
    <section id="actions">
      <h2>十、下一步改善建议</h2>
      <div class="grid three">
        <div class="panel"><h3>立即做：任务入口模板</h3><p>把“继续 / 按你理解 / go”替换为目标、允许范围、禁止范围、验收命令、交付格式。</p></div>
        <div class="panel"><h3>本周做：工程闭环门禁</h3><p>episode 超过 50 个事件仍未实现或验证时，暂停并重述目标、拆分任务、写 Definition of Done。</p></div>
        <div class="panel"><h3>本月做：项目约束层</h3><p>为高损耗项目补 AGENTS.md / CLAUDE.md / HANDOFF，减少冷启动退化。</p></div>
      </div>
    </section>
    <section class="footer">
      <p>本 HTML 由 VibeCoding Observer 从 `.analysis-profile.json` 自动生成，动态路线来自 `consulting_routes`。它是用户侧静态交付物，不包含外部脚本、外部图片或网络请求。</p>
    </section>
  </main>
</body>
</html>
"""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            return int(float(value))
    return 0


def _fmt(value: int) -> str:
    return f"{value:,}"


_LABEL_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "eng-decompose": ("先拆解", "动手前先列子问题、边界或执行步骤。"),
    "eng-verify": ("主动验证", "声称完成前运行测试、构建、检查或人工验收。"),
    "eng-cross-verify": ("交叉验证", "有意识切换 agent 或视角来复核结论。"),
    "degen-intuition": ("直觉选型", "凭名字、熟悉度或第一反应行动，未反推约束。"),
    "degen-stops-at-works": ("能跑就停", "实现刚可运行就宣布完成，后续被纠正或返工。"),
    "degen-knowledge-as-ability": ("把知道当会做", "以为提示、说明或知识已经等于稳定能力。"),
    "degen-wrong-layer": ("抽象层级误判", "把架构/推理/流程问题降级成局部实现问题。"),
    "degen-ignore-lifecycle": ("生命周期混淆", "混用原始素材、中间产物、永久资产或运行态数据。"),
    "degen-tool-fail": ("工具失败", "工具调用报错、结果不可用或没有被正确处理。"),
    "degen-instant-gratification": ("即时满足", "接受第一个能工作的方案，未评估长期代价。"),
    "degen-suggester-preference": ("偏信建议", "接受模型建议但缺少独立约束校验。"),
    "degen-fixation": ("方案固着", "锚定初始路径反复补丁，而不是重新判断方向。"),
    "act-first-principle": ("第一性原理", "用户要求按本质、人工流程或底层机制推导。"),
    "act-scale-stress": ("尺度压力测试", "用户用大规模、极端输入或容量约束测试方案。"),
    "act-ab-falsify": ("对比证伪", "用户要求比较方案、A/B 验证或反例检查。"),
    "act-constraint-reason": ("约束反推", "用户要求先判断问题类型、边界、约束和禁止范围。"),
    "act-passive": ("被动放手", "任务入口过短或缺少目标、边界、验收标准。"),
    "waste-restate": ("重复解释", "用户不得不重新说明已经给过的需求。"),
    "waste-rework": ("返工", "完成声明后又被纠正，产生重复实现成本。"),
    "waste-blind-edit": ("盲改", "没有充分读取上下文就直接编辑或改动。"),
    "waste-direction": ("方向纠偏", "用户纠正的不是细节，而是问题方向或抽象层级。"),
    "waste-handoff": ("救火切换", "切换 agent 是为了补救错误，而不是计划内复核。"),
    "waste-reversal": ("反向改动", "先前动作被撤销、重写或方向反转。"),
    "task_like": ("明确任务", "目标较清楚，可直接转成工程任务。"),
    "weak": ("弱目标", "目标过短或过泛，缺少边界和验收。"),
    "metadata": ("元信息目标", "目标来自上下文/元数据，用户意图不够直接。"),
    "missing": ("缺失目标", "无法抽取可执行任务目标。"),
    "contextual": ("上下文目标", "需要结合上下文才能判断任务目标。"),
    "goal_only": ("只有目标", "有目标但缺少实现、验证或收束闭环。"),
    "closed_verified": ("验证并收束", "任务完成前有验证证据，也有结束/交付动作。"),
    "verified_unclosed": ("验证未收束", "有验证证据，但没有明确交付或关闭。"),
    "implemented_unverified": ("实现未验证", "发生了实现动作，但缺少测试/构建/验收。"),
    "unstructured": ("未结构化", "片段无法稳定归入目标、实现、验证、收束。"),
    "long_goal_only_episode": ("长讨论无闭环", "长 episode 停留在目标/讨论，未进入完整工程闭环。"),
    "top_level_goal_without_engineering_loop": ("顶层目标未落地", "有顶层方向，但没有转成任务拆分、验证和交付。"),
    "unusable_goal": ("目标不可用", "抽取到的目标不足以指导 agent 执行。"),
    "weak_goal": ("目标偏弱", "目标缺少明确范围、约束或可验收结果。"),
    "metadata_goal": ("元数据目标", "任务目标主要来自文件名、摘要或会话元信息。"),
    "wrapped_goal_decoded": ("包装目标已解码", "目标从包装文本或转述中被恢复出来。"),
    "verified_but_unclosed": ("验证后未关闭", "已经验证，但缺少最终交付说明或 handoff。"),
    "implementation_without_verification": ("实现无验证", "有改动但没有看到测试、构建或检查。"),
}


_SIGNAL_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "constraint_maturity": ("项目约束成熟度", "越低说明 AI 协作约束、任务文档或测试约定越缺。"),
    "degen_rate": ("退化信号占比", "退化标签在交互中的占比，用于判断冷启动或执行偏差。"),
    "efficiency": ("效率画像", "综合代码产出和交互成本后的协作效率类型。"),
    "net_lines": ("净增代码行数", "新增行减删除行后的代码产出规模。"),
    "interactions": ("交互次数", "本次诊断统计到的 agent 协作交互数量。"),
    "project_type": ("项目类型", "从目录结构和配置推断的项目形态。"),
    "episode_total": ("任务片段总数", "从会话中切分出的可分析任务片段数量。"),
}


_VALUE_EXPLANATIONS: dict[str, str] = {
    "eff-grindy": "高产但高纠缠：产出不少，但需要大量来回拉扯。",
    "eff-high-leverage": "高杠杆协作：较少交互带来较多代码产出。",
    "eff-idle": "空转型协作：交互很多，但代码产出较少。",
    "eff-scaffold": "脚手架型协作：小规模任务快速完成。",
    "eff-maintenance": "维护调试型协作：存量项目上的修补和调整较多。",
    "complex-app": "复杂应用：文件和模块较多，需要明确架构边界。",
    "library": "库/工具包：应重点关注 API contract、测试和发布约束。",
    "scaffold": "脚手架/原型：适合快速成型，但要尽早补验收标准。",
    "doc-vault": "文档/知识库：重点是素材、草稿、永久资产的生命周期。",
    "data-pipeline": "数据管线：重点是数据流、产物生命周期和可重复运行。",
    "unknown": "未知项目类型：当前结构信号不足以稳定分类。",
}


_OUTPUT_TYPE_NAMES: dict[str, str] = {
    "project_start_prompt": "项目启动提示词",
    "task_prompt_template": "任务入口提示词模板",
    "verification_closure_checklist": "验证与收束清单",
    "data_lifecycle_map": "数据生命周期地图",
    "task_flow_plan": "低纠缠任务流方案",
    "agent_instructions_snippet": "AI 协作约束片段",
    "mid_project_recovery_plan": "项目中途恢复计划",
    "prompt_rewrite": "提示词重写方案",
    "delivery_closure_protocol": "交付收束协议",
    "architecture_level_review": "架构层级审查框架",
    "activation_sop": "高效激活 SOP",
    "project_preflight": "项目启动前检查",
    "frontend_preflight": "前端开发预检",
    "scope_recovery": "范围恢复方案",
    "diagnosis_action_plan": "诊断行动计划",
    "consulting_action_plan": "咨询行动计划",
}


def _dict_rows(values: dict[str, Any]) -> list[tuple[str, int]]:
    return sorted(
        ((str(key), _as_int(value)) for key, value in values.items()),
        key=lambda item: item[1],
        reverse=True,
    )


def _html_metric(label: str, value: str, note: str) -> str:
    return (
        '<div class="panel metric">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div>'
        f'<div class="note">{escape(note)}</div>'
        "</div>"
    )


def _html_persona_strip(
    *,
    weak_goal: int,
    unusable_goal: int,
    goal_only: int,
    top_goal_gap: int,
    closed_rate: float,
    verify_count: int,
) -> str:
    cards = [
        (
            "弱目标启动型",
            f"弱目标 {_fmt(weak_goal)} 次，不可执行目标 {_fmt(unusable_goal)} 次。",
            "把一句话冲动，换成目标+边界+验收。",
        ),
        (
            "验收后置型",
            f"已验证收束率 {closed_rate:.1f}%。",
            "Definition of Done 不写，返工会替你写。",
        ),
        (
            "宏大目标滞留型",
            f"只有目标未闭环 {_fmt(goal_only)} 次，顶层目标未落地 {_fmt(top_goal_gap)} 次。",
            "长 episode 不是史诗，是拆分信号。",
        ),
        (
            "验证激活型",
            f"主动验证信号 {_fmt(verify_count)} 次。",
            "让验证变成默认动作，而不是最后补票。",
        ),
    ]
    return "".join(
        '<div class="persona-card">'
        f"<strong>{escape(title)}</strong>"
        f"<p>{escape(detail)}</p>"
        f'<div class="persona-punchline">{escape(punchline)}</div>'
        "</div>"
        for title, detail, punchline in cards
    )


def _html_top_tags(rows: list[tuple[str, int]]) -> str:
    if not rows:
        return ""
    tags = []
    for label, count in rows:
        kind = "good" if label.startswith(("eng-", "act-")) else "risk"
        tags.append(f'<span class="tag {kind}">{escape(label)} {_fmt(count)}</span>')
    return "<div>" + "".join(tags) + "</div>"


def _html_bar_list(rows: list[tuple[str, int]], fill_class: str) -> str:
    if not rows:
        return '<p class="subtle">暂无数据。</p>'
    max_value = max((value for _, value in rows), default=1) or 1
    parts = ['<div class="bar-list">']
    for label, value in rows:
        width = max(2, round(value / max_value * 100))
        parts.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{_html_label_text(label)}</div>'
            '<div class="bar-track">'
            f'<div class="bar-fill {fill_class}" style="width:{width}%"></div>'
            "</div>"
            f'<div class="bar-value">{_fmt(value)}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _html_label_text(label: str) -> str:
    title, description = _LABEL_EXPLANATIONS.get(label, (label, ""))
    if not description:
        return escape(label)
    return (
        f"<strong>{escape(title)}</strong>"
        f"<code>{escape(label)}</code>"
        f"<span>{escape(description)}</span>"
    )


def _html_capability_table(rows: list[tuple[str, int, str, str]]) -> str:
    body = []
    for name, score, evidence, action in rows:
        score_class = "good" if score >= 68 else "mid" if score >= 50 else "low"
        body.append(
            "<tr>"
            f"<td>{escape(name)}</td>"
            f'<td><span class="score {score_class}">{score}</span></td>'
            f"<td>{escape(evidence)}</td>"
            f"<td>{escape(action)}</td>"
            "</tr>"
        )
    return (
        '<table class="matrix"><thead><tr>'
        "<th>能力项</th><th>评分</th><th>证据</th><th>提升方向</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _html_diagnosis_item(item: dict[str, Any]) -> str:
    signals = [str(signal) for signal in _as_list(item.get("signals"))[:3]]
    return (
        '<div class="diagnosis">'
        f"<strong>{escape(str(item.get('title', '未命名诊断')))}</strong>"
        f"{escape(str(item.get('root_cause', '')))}"
        f"{_html_signal_list(signals)}"
        f"{_html_raw_signals(signals)}"
        "</div>"
    )


def _html_route_card(route: dict[str, Any], idx: int) -> str:
    signals = [str(signal) for signal in _as_list(route.get("why_this_route"))[:3]]
    output = _as_dict(route.get("consulting_output"))
    output_type = str(output.get("output_type", "consulting_action_plan"))
    return (
        '<div class="panel route-card">'
        f'<span class="priority">{idx}</span>'
        f"<h3>{escape(str(route.get('title', '咨询路线')))}</h3>"
        f"{_html_signal_list(signals)}"
        f"{_html_raw_signals(signals)}"
        '<div class="artifact">'
        f"<strong>产物：</strong>{escape(str(route.get('what_i_can_produce', '')))}"
        f'<div class="subtle">产物类型：{escape(_output_type_name(output_type))}</div>'
        f'<details class="signal-raw"><summary>产物类型 code</summary><code>{escape(output_type)}</code></details>'
        "</div>"
        "</div>"
    )


def _html_signal_list(signals: list[str]) -> str:
    if not signals:
        return '<p class="subtle">暂无信号。</p>'
    items = "".join(f"<li>{escape(_signal_summary(signal))}</li>" for signal in signals)
    return f'<ul class="signal-list">{items}</ul>'


def _html_raw_signals(signals: list[str]) -> str:
    if not signals:
        return ""
    raw = "；".join(signals)
    return (
        '<details class="signal-raw">'
        "<summary>原始信号</summary>"
        f"<code>{escape(raw)}</code>"
        "</details>"
    )


def _signal_summary(signal: str) -> str:
    if signal.startswith("diagnosis:"):
        title = signal.split(":", 1)[1].strip()
        return f"来自诊断：{title}"
    if signal.startswith("episode_signal:"):
        signal = signal.split(":", 1)[1].strip()
    key, sep, value = signal.partition("=")
    if sep:
        title, description = _signal_explanation(key)
        value_text = _signal_value_text(key, value)
        if description:
            return f"{title}：{_trim_sentence(value_text)}。{description}"
        return f"{key}：{value_text}"
    title, description = _LABEL_EXPLANATIONS.get(signal, (signal, ""))
    return f"{title}：{description}" if description else signal


def _signal_explanation(key: str) -> tuple[str, str]:
    if key in _LABEL_EXPLANATIONS:
        return _LABEL_EXPLANATIONS[key]
    return _SIGNAL_EXPLANATIONS.get(key, (key, ""))


def _signal_value_text(key: str, value: str) -> str:
    if value in _VALUE_EXPLANATIONS:
        return _VALUE_EXPLANATIONS[value]
    if key in {"net_lines", "interactions", "episode_total"} and value.isdigit():
        return f"{_fmt(int(value))} 次" if key != "net_lines" else f"{_fmt(int(value))} 行"
    if value.isdigit():
        return f"{_fmt(int(value))} 次"
    return value


def _output_type_name(output_type: str) -> str:
    return _OUTPUT_TYPE_NAMES.get(output_type, output_type)


def _trim_sentence(value: str) -> str:
    return value.rstrip("。.")


def _consulting_routes(
    report: Report,
    diagnoses: list[Diagnosis],
    episodes: list[EpisodeSummary],
) -> list[dict[str, Any]]:
    """Generate diagnostic consulting entry points for downstream agents."""
    routes: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    def add_route(
        title: str,
        why: list[str],
        deliverable: str,
        source: str,
        priority: int,
    ) -> None:
        if title in seen_titles:
            return
        compact_why = [item for item in why if item][:3]
        if not compact_why:
            return
        seen_titles.add(title)
        routes.append({
            "title": title,
            "why_this_route": compact_why,
            "what_i_can_produce": deliverable,
            "consulting_output": _consulting_output_spec(title),
            "source": source,
            "priority": priority,
        })

    for diagnosis in diagnoses:
        title = diagnosis.title
        why = [f"diagnosis: {title}", *diagnosis.signals]
        if "顶层目标存在但工程闭环缺失" in title:
            add_route(
                "把项目目标转成可执行工程闭环",
                why,
                "项目启动/恢复 prompt、目标-约束-验收表、Definition of Done 清单",
                "diagnosis",
                10,
            )
        elif "任务入口目标质量偏弱" in title:
            add_route(
                "重写任务入口提示词和交付协议",
                why,
                "项目开始前提示词模板、弱口令替换清单、任务交付协议",
                "diagnosis",
                20,
            )
        elif "实现后验证/收束不足" in title:
            add_route(
                "建立验证与收束清单",
                why,
                "测试/构建/人工验收/交接模板，以及完成前自检清单",
                "diagnosis",
                30,
            )
        elif "数据生命周期" in title:
            add_route(
                "梳理数据生命周期和资产边界",
                why,
                "原始素材/中间产物/永久资产表，以及 AGENTS.md 约束片段",
                "diagnosis",
                40,
            )
        elif "高产但高纠缠" in title:
            add_route(
                "把高产开发拆成低纠缠任务流",
                why,
                "任务拆分、验收点、停损规则和 handoff 模板",
                "diagnosis",
                50,
            )
        elif "约束缺失" in title:
            add_route(
                "建立项目 AI 协作约束",
                why,
                "AGENTS.md/CLAUDE.md 初版、写入范围和禁止范围模板",
                "diagnosis",
                60,
            )
        else:
            add_route(
                f"处理诊断：{title}",
                why,
                "针对该诊断的根因分析、行动清单和交付模板",
                "diagnosis",
                90,
            )

    signal_counts = _episode_diagnostic_signal_counts(episodes)
    if signal_counts.get("top_level_goal_without_engineering_loop", 0) > 0:
        add_route(
            "恢复项目方向和控制",
            [
                "episode_signal: top_level_goal_without_engineering_loop="
                f"{signal_counts['top_level_goal_without_engineering_loop']}",
                f"developer_type: {report.developer_type}",
            ],
            "中途失控恢复计划、当前目标重建 prompt、下一步验收路线",
            "episode_signal",
            70,
        )
    weak_goal_count = signal_counts.get("weak_goal", 0) + signal_counts.get(
        "unusable_goal", 0
    )
    if weak_goal_count > 0:
        add_route(
            "改造任务入口提示词",
            [
                f"episode_signal: weak_or_unusable_goal={weak_goal_count}",
                f"developer_type: {report.developer_type}",
            ],
            "项目开始前提示词、目标质量检查表、上下文输入格式",
            "episode_signal",
            80,
        )
    verification_gap_count = signal_counts.get(
        "implementation_without_verification", 0
    ) + signal_counts.get("verified_but_unclosed", 0)
    if verification_gap_count > 0:
        add_route(
            "补齐验证和交付闭环",
            [
                f"episode_signal: verification_or_closure_gap={verification_gap_count}",
                f"developer_type: {report.developer_type}",
            ],
            "验证矩阵、完成定义、测试/构建/人工检查的收束协议",
            "episode_signal",
            85,
        )

    if report.label_count("degen-wrong-layer") > 0:
        add_route(
            "做任务前抽象层级判断",
            [
                f"label: degen-wrong-layer={report.label_count('degen-wrong-layer')}",
                f"developer_type: {report.developer_type}",
            ],
            "架构层级判断框架、前端/API/数据模型边界检查清单",
            "label_distribution",
            100,
        )
    if report.label_count("act-first-principle") > 0:
        add_route(
            "沉淀你的高效激活手法",
            [
                f"label: act-first-principle={report.label_count('act-first-principle')}",
                f"developer_type: {report.developer_type}",
            ],
            "可复用 SOP、任务前提问脚本、给 agent 的工程判断触发词",
            "label_distribution",
            110,
        )

    if not routes:
        add_route(
            "项目开始前建议",
            ["fallback: report has insufficient diagnostic signals"],
            "项目启动 prompt、目标/约束/验收模板、最小风险清单",
            "fallback",
            900,
        )
        add_route(
            "前端开发开始前建议",
            ["fallback: report has insufficient diagnostic signals"],
            "前端 preflight checklist、状态/交互/验收清单",
            "fallback",
            910,
        )
        add_route(
            "项目做到一半失去方向和控制",
            ["fallback: report has insufficient diagnostic signals"],
            "恢复计划、范围重切、下一轮 agent 任务包",
            "fallback",
            920,
        )

    return sorted(routes, key=lambda route: route["priority"])[:5]


def _consulting_output_spec(title: str) -> dict[str, Any]:
    specs: dict[str, dict[str, Any]] = {
        "把项目目标转成可执行工程闭环": {
            "output_type": "project_start_prompt",
            "sections": [
                "目标重写",
                "硬约束",
                "交付物",
                "验收标准",
                "停止条件",
            ],
            "starter_questions": [
                "这个项目当前最重要的用户结果是什么？",
                "哪些文件、接口、配置或行为不能被改动？",
                "什么证据能证明这一轮已经完成？",
            ],
            "completion_criteria": [
                "目标能被拆成 3-7 个可验收任务",
                "每个任务都有禁止范围和验证方式",
                "agent 在动手前能复述目标、约束和 Definition of Done",
            ],
        },
        "重写任务入口提示词和交付协议": {
            "output_type": "task_prompt_template",
            "sections": [
                "任务背景",
                "目标",
                "允许修改范围",
                "禁止范围",
                "验证命令",
                "交付格式",
            ],
            "starter_questions": [
                "这次任务是探索、设计、实现、修复还是验证？",
                "哪些上下文是事实，哪些只是你的猜测？",
                "你希望 agent 最后交付代码、报告、计划还是审查结论？",
            ],
            "completion_criteria": [
                "任务入口不依赖“继续”“按你理解”这类弱指令",
                "输出格式和验证方式在任务开始前明确",
                "agent 能判断何时需要先读代码而不是直接实现",
            ],
        },
        "建立验证与收束清单": {
            "output_type": "verification_closure_checklist",
            "sections": [
                "自动化测试",
                "类型/静态检查",
                "人工验收",
                "风险声明",
                "交接摘要",
            ],
            "starter_questions": [
                "哪些测试能覆盖这次修改的主要行为？",
                "哪些结果必须人工打开页面或文件确认？",
                "完成后需要向下一个 agent 交接哪些风险？",
            ],
            "completion_criteria": [
                "至少有一项自动化或可复现验证",
                "未验证事项被明确列出",
                "最终回复包含修改范围、风险和下一步",
            ],
        },
        "梳理数据生命周期和资产边界": {
            "output_type": "data_lifecycle_map",
            "sections": [
                "原始输入",
                "临时中间产物",
                "长期资产",
                "下游消费者",
                "清理/保留策略",
            ],
            "starter_questions": [
                "哪些数据只是本轮分析用，哪些会被长期复用？",
                "中间产物是否会因为方案变化而失效？",
                "下游真正需要的是原始数据、摘要还是结构化索引？",
            ],
            "completion_criteria": [
                "每类数据都有生命周期标签",
                "临时产物不会被误当成长期资产",
                "输出格式服务下游真实消费方式",
            ],
        },
        "把高产开发拆成低纠缠任务流": {
            "output_type": "task_flow_plan",
            "sections": [
                "任务切片",
                "依赖关系",
                "每片验收点",
                "停损规则",
                "handoff 摘要",
            ],
            "starter_questions": [
                "哪些任务可以独立完成并独立验证？",
                "哪一步失败会导致后续全部返工？",
                "每个 agent 接手时必须知道什么？",
            ],
            "completion_criteria": [
                "每个任务片不跨越太多模块边界",
                "失败时能在当前任务片停止",
                "handoff 足以让下一个 agent 不重读全部上下文",
            ],
        },
        "建立项目 AI 协作约束": {
            "output_type": "agent_instructions_snippet",
            "sections": [
                "默认工作方式",
                "写入范围",
                "禁止范围",
                "测试要求",
                "交付格式",
            ],
            "starter_questions": [
                "这个项目最容易被 agent 误改的边界是什么？",
                "哪些命令必须在完成前运行？",
                "哪些业务事实、价格、来源或资质不能编造？",
            ],
            "completion_criteria": [
                "约束能直接放入 AGENTS.md 或 CLAUDE.md",
                "写入范围和禁止范围可执行",
                "完成回复格式覆盖测试、风险、越界检查",
            ],
        },
        "恢复项目方向和控制": {
            "output_type": "mid_project_recovery_plan",
            "sections": [
                "当前事实",
                "失控信号",
                "重新定界",
                "下一步任务包",
                "验证/停损点",
            ],
            "starter_questions": [
                "现在已经确定的事实是什么？",
                "哪些工作只是动作堆叠但没有推进目标？",
                "下一步最小可验证前进是什么？",
            ],
            "completion_criteria": [
                "恢复计划区分事实、推断和待验证事项",
                "下一步任务包能在一轮内完成",
                "明确何时停止继续实现并回到设计判断",
            ],
        },
        "改造任务入口提示词": {
            "output_type": "prompt_rewrite",
            "sections": [
                "原始指令问题",
                "改写后指令",
                "必要上下文",
                "验收方式",
                "反模式替换",
            ],
            "starter_questions": [
                "原始指令里缺了目标、边界还是验收？",
                "哪些上下文必须给，哪些会干扰 agent？",
                "你希望 agent 先分析、先计划还是直接改？",
            ],
            "completion_criteria": [
                "改写后指令能独立启动任务",
                "不再依赖隐含聊天记忆",
                "明确 agent 何时该追问而不是猜",
            ],
        },
        "补齐验证和交付闭环": {
            "output_type": "delivery_closure_protocol",
            "sections": [
                "验证矩阵",
                "未验证事项",
                "风险点",
                "最终交付摘要",
                "下一步建议",
            ],
            "starter_questions": [
                "当前修改影响哪些用户可见行为？",
                "哪些验证命令最能发现回归？",
                "哪些风险需要在最终回复中明说？",
            ],
            "completion_criteria": [
                "验证覆盖主要行为和失败路径",
                "最终交付不只说完成，还说明证据",
                "未完成项和风险不会被隐藏",
            ],
        },
        "做任务前抽象层级判断": {
            "output_type": "architecture_level_review",
            "sections": [
                "问题层级",
                "证据层",
                "推理层",
                "实现层",
                "验证层",
            ],
            "starter_questions": [
                "这是 UI、数据、API、状态、架构还是流程问题？",
                "需要先收集什么证据才能判断？",
                "直接改代码会不会把高层问题低层硬解？",
            ],
            "completion_criteria": [
                "先给出问题层级判断再行动",
                "证据不足时不直接实现",
                "实现方案与问题层级一致",
            ],
        },
        "沉淀你的高效激活手法": {
            "output_type": "activation_sop",
            "sections": [
                "有效触发语",
                "适用场景",
                "反例",
                "复用模板",
                "验证方式",
            ],
            "starter_questions": [
                "哪些提问最能让 agent 做工程判断？",
                "哪些场景容易退回动作实现？",
                "这个触发语如何写进日常任务模板？",
            ],
            "completion_criteria": [
                "SOP 能复用到新项目",
                "包含触发工程判断的具体话术",
                "包含识别退化时的纠偏话术",
            ],
        },
        "项目开始前建议": {
            "output_type": "project_preflight",
            "sections": [
                "项目目标",
                "技术边界",
                "风险假设",
                "第一轮任务",
                "验收标准",
            ],
            "starter_questions": [
                "项目要服务谁，解决什么具体问题？",
                "第一轮必须证明的最小价值是什么？",
                "哪些技术或业务假设最容易错？",
            ],
            "completion_criteria": [
                "启动建议能转成第一轮任务包",
                "风险假设可验证",
                "验收标准在写代码前明确",
            ],
        },
        "前端开发开始前建议": {
            "output_type": "frontend_preflight",
            "sections": [
                "用户流程",
                "状态模型",
                "组件边界",
                "响应式要求",
                "验收场景",
            ],
            "starter_questions": [
                "首屏用户要完成什么动作？",
                "哪些状态会改变 UI？",
                "哪些断点和交互必须验收？",
            ],
            "completion_criteria": [
                "组件职责不混入复杂业务逻辑",
                "关键状态和空/错/加载态齐全",
                "桌面和移动验收场景明确",
            ],
        },
        "项目做到一半失去方向和控制": {
            "output_type": "scope_recovery",
            "sections": [
                "已完成事实",
                "偏离点",
                "保留/丢弃",
                "下一步最小任务",
                "验证点",
            ],
            "starter_questions": [
                "现在还能确定哪些成果是有效的？",
                "从哪一步开始目标变模糊？",
                "下一步最小恢复动作是什么？",
            ],
            "completion_criteria": [
                "恢复动作不继续扩大范围",
                "明确哪些已有工作暂时冻结",
                "下一轮任务有清晰验收点",
            ],
        },
    }
    if title.startswith("处理诊断："):
        return {
            "output_type": "diagnosis_action_plan",
            "sections": [
                "诊断复述",
                "根因",
                "行动清单",
                "验证方式",
                "风险",
            ],
            "starter_questions": [
                "这条诊断影响的是目标、架构、实现还是验证？",
                "哪些信号最能证明这个问题存在？",
                "下一步最小纠偏动作是什么？",
            ],
            "completion_criteria": [
                "行动清单直接对应诊断信号",
                "每个动作有验证方式",
                "风险和未完成项明确列出",
            ],
        }
    return specs.get(
        title,
        {
            "output_type": "consulting_action_plan",
            "sections": [
                "当前信号",
                "建议方向",
                "行动清单",
                "验证方式",
                "下一步",
            ],
            "starter_questions": [
                "这条路线要解决哪个最主要的诊断信号？",
                "用户当前最需要 prompt、清单、计划还是规范片段？",
                "什么结果可以证明咨询有用？",
            ],
            "completion_criteria": [
                "输出直接引用本次诊断信号",
                "建议能转成下一轮 agent 任务",
                "完成标准可验证",
            ],
        },
    )


def _episode_diagnostic_signal_counts(
    episodes: list[EpisodeSummary],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for episode in episodes:
        for signal in episode.diagnostic_signals:
            counts[signal] = counts.get(signal, 0) + 1
    return counts


def _episode_summary(episodes: list[EpisodeSummary]) -> dict[str, Any]:
    loop_counts: dict[str, int] = {}
    goal_quality_counts: dict[str, int] = {}
    goal_extraction_counts: dict[str, int] = {}
    diagnostic_signal_counts: dict[str, int] = {}
    project_counts: dict[str, int] = {}
    for ep in episodes:
        loop_counts[ep.loop_quality] = loop_counts.get(ep.loop_quality, 0) + 1
        goal_quality_counts[ep.goal_quality] = goal_quality_counts.get(ep.goal_quality, 0) + 1
        goal_extraction_counts[ep.goal_extraction_method] = (
            goal_extraction_counts.get(ep.goal_extraction_method, 0) + 1
        )
        for signal in ep.diagnostic_signals:
            diagnostic_signal_counts[signal] = diagnostic_signal_counts.get(signal, 0) + 1
        project_counts[ep.project] = project_counts.get(ep.project, 0) + 1
    return {
        "total": len(episodes),
        "loop_quality_counts": dict(sorted(loop_counts.items())),
        "goal_quality_counts": dict(sorted(goal_quality_counts.items())),
        "goal_extraction_counts": dict(sorted(goal_extraction_counts.items())),
        "diagnostic_signal_counts": dict(sorted(diagnostic_signal_counts.items())),
        "top_projects": [
            {"project": project, "episodes": count}
            for project, count in sorted(
                project_counts.items(), key=lambda item: item[1], reverse=True
            )[:10]
        ],
    }


def _goal_quality_rank(ep: EpisodeSummary) -> int:
    return {
        "task_like": 4,
        "contextual": 3,
        "weak": 2,
        "metadata": 1,
        "missing": 0,
    }.get(ep.goal_quality, 0)


def _effective_activation_signatures(report: Report) -> list[dict[str, Any]]:
    act_labels = [
        "act-first-principle",
        "act-scale-stress",
        "act-ab-falsify",
        "act-constraint-reason",
    ]
    signatures = []
    for lbl in act_labels:
        cnt = report.label_count(lbl)
        if cnt > 0:
            signatures.append({"activation": lbl, "count": cnt})
    return sorted(signatures, key=lambda x: -x["count"])
