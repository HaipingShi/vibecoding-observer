"""Reporter — render the analysis report + profile.json for agent consumption.

Consumes the Aggregator's Report and the Anomaly Detector's Anomaly list.
The report is the *input* for the consuming agent — Section VI embeds actual
anomalous event fragments so the agent (which IS an LLM) reads them directly
and produces insights. No separate LLM analyzer module needed.
"""

from __future__ import annotations

import contextlib
import hashlib
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

__all__ = [
    "generate_html_report",
    "generate_profile",
    "generate_report",
    "generate_share_card_svg",
]


def generate_report(
    report: Report,
    anomalies: list[Anomaly],
    title_suffix: str = "",
    diagnoses: list[Diagnosis] | None = None,
    project: ProjectProfile | None = None,
    git: GitMetrics | None = None,
    report_language: str = "zh",
) -> str:
    language = _report_language(report_language)
    title = (
        "# 协作工程化效能分析报告"
        if language == "zh"
        else "# AI Coding Collaboration Diagnostics"
    )
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
        lines.append(f"**置信度**: {d.confidence}")
        lines.append(f"**根因**: {d.root_cause}")
        lines.append(f"**建议**: {d.recommendation}")
        if d.signals:
            lines.append(f"**信号**: {', '.join(d.signals)}")
        if d.uncertainty_reasons:
            lines.append(f"**不确定性**: {', '.join(d.uncertainty_reasons)}")
        lines.append("")

    return "\n".join(lines)


def generate_profile(
    report: Report,
    anomalies: list[Anomaly],
    diagnoses: list[Diagnosis] | None = None,
    episodes: list[EpisodeSummary] | None = None,
    signal_config: dict[str, Any] | None = None,
    report_language: str = "zh",
    language_detection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the machine-readable profile for Phase B consumption."""
    language = _report_language(report_language)
    profile: dict[str, Any] = {
        "version": "0.2.0",
        "report_language": language,
        "language_detection": language_detection or {"source": "default", "confidence": "low"},
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
        "effective_activations": _effective_activation_signatures(report, episodes or []),
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

    if signal_config:
        profile["signal_profile"] = signal_config

    if episodes is not None:
        emitted_episodes = sorted(
            episodes,
            key=lambda e: (_goal_quality_rank(e), e.event_count),
            reverse=True,
        )[:50]
        profile["episode_summary"] = _episode_summary(
            emitted_episodes,
            analyzed_total=len(episodes),
        )
        profile["episodes"] = [
            ep.to_dict()
            for ep in emitted_episodes
        ]

    if diagnoses:
        profile["diagnoses"] = [
            {
                "title": d.title,
                "severity": d.severity,
                "root_cause": d.root_cause,
                "recommendation": d.recommendation,
                "signals": d.signals,
                "confidence": d.confidence,
                "uncertainty_reasons": d.uncertainty_reasons,
            }
            for d in diagnoses
        ]

    profile["share_card"] = _share_card(
        report=report,
        episodes=episodes or [],
        language=language,
    )

    profile["consulting_routes"] = _consulting_routes(
        report=report,
        diagnoses=diagnoses or [],
        episodes=episodes or [],
    )

    return profile


def generate_html_report(profile: dict[str, Any]) -> str:
    """Generate a self-contained user-facing HTML report from the profile."""
    language = _report_language(str(profile.get("report_language", "zh")))
    ui = _html_ui(language)
    total_events = _as_int(profile.get("total_events"))
    total_projects = _as_int(profile.get("total_projects"))
    developer_type = str(profile.get("developer_type", "unknown"))
    diagnoses = _as_list(profile.get("diagnoses"))
    routes = _as_list(profile.get("consulting_routes"))
    share_card = _as_dict(profile.get("share_card"))
    episode_summary = _as_dict(profile.get("episode_summary"))
    loop_counts = _as_dict(episode_summary.get("loop_quality_counts"))
    goal_counts = _as_dict(episode_summary.get("goal_quality_counts"))
    signal_counts = _as_dict(episode_summary.get("diagnostic_signal_counts"))
    episode_total = _as_int(episode_summary.get("total"))
    analyzed_episode_total = _as_int(episode_summary.get("analyzed_total"))
    signal_profile = _as_dict(profile.get("signal_profile"))
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
    signal_profile_risk = _html_signal_profile_risk(signal_profile)
    closed_verified = (
        _as_int(loop_counts.get("closed_verified"))
        + _as_int(loop_counts.get("implementation_closed"))
        + _as_int(loop_counts.get("design_closed"))
    )
    goal_only = _as_int(loop_counts.get("goal_only"))
    closed_rate = (closed_verified / episode_total * 100) if episode_total else 0.0
    goal_only_rate = (goal_only / episode_total * 100) if episode_total else 0.0
    weak_goal = _as_int(signal_counts.get("weak_goal"))
    unusable_goal = _as_int(signal_counts.get("unusable_goal"))
    top_goal_gap = _as_int(signal_counts.get("top_level_goal_without_engineering_loop"))
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
    avatar_seed = f"{developer_type}:{total_events}:{total_projects}:{closed_rate:.1f}"
    avatar_mood = _avatar_mood(diagnoses, closed_rate)
    report_avatar = _pet_avatar_svg(
        avatar_seed,
        mood=avatar_mood,
        size=112,
        title="你的诊断宠物头像",
    )
    portrait_html = _html_delivery_portrait(
        developer_type=developer_type,
        closed_rate=closed_rate,
        verify_count=_as_int(label_counts.get("eng-verify")),
        total_events=total_events,
    )
    conclusion_html = _html_delivery_conclusion(
        label_counts=label_counts,
        signal_counts=signal_counts,
        closed_rate=closed_rate,
    )
    strengths_html = _html_delivery_strengths(
        label_counts=label_counts,
        closed_rate=closed_rate,
        closed_verified=closed_verified,
        episode_total=episode_total,
    )
    problem_cards = _html_delivery_problem_cards(
        label_counts=label_counts,
        signal_counts=signal_counts,
        loop_counts=loop_counts,
        closed_rate=closed_rate,
    )
    priority_actions = _html_priority_actions(signal_counts=signal_counts)
    share_card_html = _html_share_card(share_card, avatar_seed=avatar_seed)

    return f"""<!doctype html>
<html lang="{ui['html_lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{ui['page_title']}</title>
  <style>
    :root {{
      --bg:#f6f7f9; --panel:#fff; --ink:#17202a; --muted:#667085;
      --line:#d9dee7; --brand:#1f6feb; --good:#1f8a5b; --warn:#b7791f;
      --risk:#c2410c; --bad:#b42318; --cyan:#0e7490; --violet:#6f4fbf;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; overflow-x:hidden; background:var(--bg); color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.55; }}
    header {{ background:#111827; color:#fff; padding:30px 32px 26px; }}
    .hero {{ display:flex; gap:20px; align-items:center; max-width:1180px; }}
    .hero-copy {{ min-width:0; }}
    header h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,46px); line-height:1.08; letter-spacing:0; }}
    header p {{ margin:0; max-width:980px; color:#cbd5e1; }}
    .pet-avatar {{ flex:0 0 auto; width:112px; height:112px; filter:drop-shadow(6px 8px 0 rgba(0,0,0,.28)); }}
    .pet-avatar svg,.mini-pet svg {{ display:block; width:100%; height:100%; }}
    .mini-pet {{ float:right; width:54px; height:54px; margin:0 0 8px 10px; }}
    .share-wrap {{ display:grid; grid-template-columns:minmax(0,1fr) 320px; gap:18px; align-items:stretch; }}
    .share-card {{ position:relative; overflow:hidden; border:3px solid #17202a; background:#fffaf0; box-shadow:8px 8px 0 #17202a; padding:22px; }}
    .share-card::before {{ content:""; position:absolute; inset:0; background:linear-gradient(135deg,rgba(31,111,235,.12),transparent 45%,rgba(31,138,91,.14)); pointer-events:none; }}
    .share-card > * {{ position:relative; }}
    .share-eyebrow {{ display:inline-flex; border:2px solid #17202a; border-radius:999px; padding:4px 10px; background:#dcfce7; font-size:12px; font-weight:800; }}
    .share-title {{ margin:14px 0 8px; font-size:clamp(28px,4vw,48px); line-height:1; font-weight:900; letter-spacing:0; }}
    .share-score {{ display:flex; gap:12px; align-items:flex-end; margin:10px 0 14px; }}
    .share-score strong {{ font-size:60px; line-height:.88; }}
    .share-score span {{ max-width:260px; color:#344054; font-weight:700; line-height:1.25; }}
    .share-achievements {{ display:grid; gap:10px; margin-top:14px; }}
    .share-achievement {{ border:2px solid #17202a; border-radius:8px; background:#fff; padding:10px 12px; }}
    .share-achievement strong {{ display:block; font-size:15px; }}
    .share-achievement p {{ margin:4px 0 0; color:#475467; font-size:13px; }}
    .share-side {{ display:flex; flex-direction:column; justify-content:space-between; gap:14px; border:2px dashed #17202a; background:#f8fafc; padding:16px; }}
    .share-pet {{ width:150px; height:150px; align-self:center; filter:drop-shadow(5px 6px 0 rgba(0,0,0,.22)); }}
    .share-cta {{ border-top:1px dashed #98a2b3; padding-top:12px; color:#17202a; font-size:18px; font-weight:850; line-height:1.25; }}
    .share-note {{ color:var(--muted); font-size:12px; line-height:1.35; }}
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
    .plain-card {{ border-left:4px solid var(--brand); }}
    .plain-card p {{ margin:6px 0 0; }}
    .portrait {{ border:2px solid #17202a; background:#fffdf7; box-shadow:6px 6px 0 #17202a; }}
    .portrait p {{ margin:8px 0 0; font-size:16px; color:#344054; }}
    .conclusion {{ border-left:5px solid var(--brand); font-size:18px; }}
    .strength-card {{ border-left:4px solid var(--good); }}
    .problem-card {{ border-left:4px solid var(--risk); }}
    .problem-card h3 {{ font-size:18px; }}
    .problem-block {{ margin-top:12px; }}
    .problem-block strong {{ display:block; margin-bottom:4px; color:#17202a; }}
    .prompt-template {{ margin-top:10px; padding:12px; border:1px solid var(--line); border-radius:8px; background:#f8fafc; color:#17202a; white-space:pre-wrap; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }}
    .priority-list {{ display:grid; gap:12px; padding-left:0; list-style:none; }}
    .priority-list li {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .appendix {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; }}
    .appendix summary {{ cursor:pointer; font-weight:720; font-size:18px; }}
    .scenario-card h3 {{ margin-bottom:6px; }}
    .scenario-card p {{ margin:6px 0; color:#344054; }}
    .next-action {{ margin-top:10px; border-top:1px solid var(--line); padding-top:10px; font-weight:680; color:#17202a; }}
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
    @media (max-width:1100px) {{ .kpi,.routes,.three,.four {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .share-wrap {{ grid-template-columns:1fr; }} }}
    @media (max-width:760px) {{ header {{ padding:24px 18px; }} .hero {{ align-items:flex-start; }} .pet-avatar {{ width:76px; height:76px; }} nav {{ padding:8px 12px; }} nav a {{ font-size:13px; }} main {{ padding:22px 14px 36px; }} .panel {{ padding:14px; }} .share-card {{ box-shadow:4px 4px 0 #17202a; padding:16px; }} .share-score strong {{ font-size:46px; }} .share-pet {{ width:112px; height:112px; }} .persona-strip {{ box-shadow:4px 4px 0 #17202a; }} .persona-card {{ min-height:auto; }} .kpi,.two,.three,.four,.routes {{ grid-template-columns:1fr; }} .bar-row {{ grid-template-columns:1fr auto; gap:6px 10px; }} .bar-label {{ grid-column:1 / -1; }} .bar-track {{ grid-column:1; }} .bar-value {{ grid-column:2; }} .route-card {{ min-height:auto; }} .matrix th,.matrix td {{ padding:8px 6px; font-size:12px; }} }}
  </style>
</head>
<body>
  <header>
    <div class="hero">
      <div class="pet-avatar">{report_avatar}</div>
      <div class="hero-copy">
        <h1>{ui['page_title']}</h1>
        <p>{ui['hero_prefix']} {_fmt(total_projects)} {ui['project_unit']}、{_fmt(total_events)} {ui['event_unit']}。{ui['hero_pet']}</p>
      </div>
    </div>
  </header>
  <nav>
    <a href="#share-card">{ui['nav_share']}</a><a href="#portrait">{ui['nav_portrait']}</a><a href="#conclusion">{ui['nav_conclusion']}</a><a href="#strengths">{ui['nav_strengths']}</a><a href="#problems">{ui['nav_problems']}</a><a href="#actions">{ui['nav_actions']}</a><a href="#appendix">{ui['nav_appendix']}</a>
  </nav>
  <main>
    <section id="share-card">
      <h2>{ui['share_heading']}</h2>
      {share_card_html}
    </section>
    <section id="portrait">
      <h2>{ui['portrait_heading']}</h2>
      <div class="panel portrait">{portrait_html}</div>
    </section>
    <section id="conclusion">
      <h2>{ui['conclusion_heading']}</h2>
      <div class="panel conclusion">{conclusion_html}</div>
    </section>
    <section id="strengths">
      <h2>{ui['strengths_heading']}</h2>
      <div class="grid two">{strengths_html}</div>
    </section>
    <section id="problems">
      <h2>{ui['problems_heading']}</h2>
      <div class="grid three">{problem_cards}</div>
    </section>
    <section id="actions">
      <h2>{ui['actions_heading']}</h2>
      {priority_actions}
    </section>
    <section id="appendix">
      <details class="appendix">
        <summary>{ui['appendix_summary']}</summary>
        <div class="grid kpi">
          {_html_metric("分析项目", _fmt(total_projects), "多源融合后的项目数")}
          {_html_metric("交互事件", _fmt(total_events), "本地会话历史，无网络上传")}
          {_html_metric("任务片段", _fmt(episode_total), f"输出片段 / 全量 {_fmt(analyzed_episode_total or episode_total)}")}
          {_html_metric("交叉诊断", _fmt(len(diagnoses)), "诊断与建议数量")}
        </div>
        <div class="grid two">
          <div class="panel"><h3>Top 标签</h3>{_html_bar_list(label_rows, "bar-fill")}</div>
          <div class="panel"><h3>目标质量</h3>{_html_bar_list(_dict_rows(goal_counts), "warn-fill")}</div>
        </div>
        <div class="grid two">
          <div class="panel">
            <h3>工程闭环漏斗</h3>
            {_html_bar_list(_dict_rows(loop_counts), "cyan-fill")}
            <p class="subtle">closed/design/implementation: {closed_rate:.1f}%；goal_only: {goal_only_rate:.1f}%。</p>
          </div>
          <div class="panel">
            <h3>Episode diagnostic signals</h3>
            {_html_bar_list(_dict_rows(signal_counts)[:8], "risk-fill")}
          </div>
        </div>
        <div class="panel"><h3>AI 协作能力矩阵</h3>{_html_capability_table(capability_rows)}</div>
        <div class="grid two">
          <div class="panel"><h3>浪费最严重项目</h3>{_html_bar_list(waste_rows, "bad-fill")}</div>
          <div class="panel"><h3>退化最严重项目</h3>{_html_bar_list(degenerate_rows, "risk-fill")}</div>
        </div>
        <div class="grid two">
          <div class="panel">{diagnosis_items or '<p class="subtle">暂无诊断。</p>'}</div>
          <div class="panel">{signal_profile_risk}</div>
        </div>
        <div class="grid routes">{route_cards or '<div class="panel">暂无咨询路线。</div>'}</div>
      </details>
    </section>
    <section class="footer">
      <p>{ui['footer']}</p>
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


def _report_language(value: str) -> str:
    return "en" if str(value).lower().startswith("en") else "zh"


def _html_ui(language: str) -> dict[str, str]:
    if _report_language(language) == "en":
        return {
            "html_lang": "en",
            "page_title": "VibeCoding Observer Visual Report",
            "hero_prefix": "Generated from",
            "project_unit": "project(s)",
            "event_unit": "AI coding agent events",
            "hero_pet": "The pixel pet is generated by code and changes mood with the report.",
            "nav_share": "Share Card",
            "nav_portrait": "Profile",
            "nav_conclusion": "Bottom Line",
            "nav_strengths": "Strengths",
            "nav_problems": "Top 3 Frictions",
            "nav_actions": "Actions",
            "nav_appendix": "Developer Appendix",
            "share_heading": "Screenshot-Friendly Share Card",
            "portrait_heading": "Your Vibe Coding Collaboration Profile",
            "conclusion_heading": "Bottom Line",
            "strengths_heading": "What You Already Do Well",
            "problems_heading": "The 3 Things Slowing You Down",
            "actions_heading": "Priority Actions",
            "appendix_summary": "Developer Appendix: labels, confidence, and raw signals",
            "footer": (
                "This HTML is generated from `.analysis-profile.json`. Dynamic routes "
                "come from `consulting_routes`. It is self-contained and uses no "
                "external scripts, images, or network requests."
            ),
        }
    return {
        "html_lang": "zh-CN",
        "page_title": "VibeCoding Observer 可视化诊断报告",
        "hero_prefix": "基于",
        "project_unit": "个项目",
        "event_unit": "条 AI coding agent 交互事件生成",
        "hero_pet": "旁边这只代码生成的诊断宠物，会根据本次报告的状态换颜色和表情。",
        "nav_share": "夸夸卡",
        "nav_portrait": "协作画像",
        "nav_conclusion": "一句话结论",
        "nav_strengths": "做得好的地方",
        "nav_problems": "最拖慢你的 3 个问题",
        "nav_actions": "优先级行动",
        "nav_appendix": "开发者附录",
        "share_heading": "可截图分享的夸夸卡",
        "portrait_heading": "你的 vibe coding 协作画像",
        "conclusion_heading": "一句话结论",
        "strengths_heading": "你做得好的地方",
        "problems_heading": "最拖慢你的 3 个问题",
        "actions_heading": "优先级行动",
        "appendix_summary": "开发者附录：内部标签、置信度和原始信号",
        "footer": (
            "本 HTML 由 VibeCoding Observer 从 `.analysis-profile.json` 自动生成，"
            "动态路线来自 `consulting_routes`。它是用户侧静态交付物，不包含外部脚本、"
            "外部图片或网络请求。"
        ),
    }


def _share_card(
    report: Report,
    episodes: list[EpisodeSummary],
    *,
    language: str,
) -> dict[str, Any]:
    """Build a playful, screenshot-friendly card from positive signals."""
    language = _report_language(language)
    verify_count = report.label_count("eng-verify")
    decompose_count = report.label_count("eng-decompose")
    cross_verify_count = report.label_count("eng-cross-verify")
    first_principle_count = report.label_count("act-first-principle")
    constraint_count = report.label_count("act-constraint-reason")
    design_closed_count = sum(1 for ep in episodes if ep.loop_quality == "design_closed")
    closed_count = sum(
        1
        for ep in episodes
        if ep.loop_quality in {"closed_verified", "implementation_closed", "design_closed"}
    )
    episode_total = len(episodes)
    closed_rate = (closed_count / episode_total * 100) if episode_total else 0.0
    wrong_layer_count = report.label_count("degen-wrong-layer")
    passive_count = report.label_count("act-passive")
    weak_goal_count = sum(
        1
        for ep in episodes
        if "weak_goal" in ep.diagnostic_signals or "unusable_goal" in ep.diagnostic_signals
    )

    positive_points = (
        min(22, verify_count * 2)
        + min(12, decompose_count * 3)
        + min(12, cross_verify_count * 4)
        + min(12, first_principle_count * 2)
        + min(12, constraint_count * 2)
        + min(16, round(closed_rate / 6))
        + min(10, design_closed_count * 2)
    )
    friction_penalty = min(14, wrong_layer_count + passive_count // 2 + weak_goal_count)
    score_floor = 58 if report.total_events == 0 else 72
    score = max(score_floor, min(97, 70 + positive_points - friction_penalty))

    achievements = _share_card_achievements(
        verify_count=verify_count,
        decompose_count=decompose_count,
        cross_verify_count=cross_verify_count,
        first_principle_count=first_principle_count,
        constraint_count=constraint_count,
        wrong_layer_count=wrong_layer_count,
        closed_count=closed_count,
        episode_total=episode_total,
        design_closed_count=design_closed_count,
        language=language,
    )
    title = _share_card_title(achievements, language=language)
    if language == "en":
        headline = (
            f"You defeated {score}% of the ship-it-and-pray impulse"
            if report.total_events
            else "Your AI collaboration highlight reel is warming up"
        )
        subtitle = "Vibes leaderboard. For fun only."
        score_label = "Highlight Score"
        cta = "Find your AI pair persona"
        note = "Full report has the roast. This card is just for fun."
    else:
        headline = (
            f"你击败了 {score}% 的“能跑就行”冲动"
            if report.total_events
            else "你的 AI 协作高光正在加载"
        )
        subtitle = "气氛组排名，仅供开心。"
        score_label = "本次高光指数"
        cta = "测测你的 AI 搭子人格"
        note = "完整吐槽在报告正文，这张卡只负责让你开心一下。"
    return {
        "title": title,
        "language": language,
        "score": score,
        "score_label": score_label,
        "headline": headline,
        "subtitle": subtitle,
        "achievements": achievements,
        "title_pool": _share_title_pool(language),
        "llm_title_prompt": _share_title_rewrite_prompt(language),
        "cta": cta,
        "note": note,
    }


def _share_card_achievements(
    *,
    verify_count: int,
    decompose_count: int,
    cross_verify_count: int,
    first_principle_count: int,
    constraint_count: int,
    wrong_layer_count: int,
    closed_count: int,
    episode_total: int,
    design_closed_count: int,
    language: str,
) -> list[dict[str, str]]:
    if _report_language(language) == "en":
        candidates = [
            (
                verify_count,
                "Verification Addict",
                f"{_fmt(verify_count)} verification moves",
                "You make the agent prove it before you trust it.",
            ),
            (
                decompose_count,
                "Task Slicer",
                f"{_fmt(decompose_count)} decomposition signals",
                "Big messy work gets chopped before it gets shipped.",
            ),
            (
                cross_verify_count,
                "Cross-Check Enjoyer",
                f"{_fmt(cross_verify_count)} review signals",
                "You let evidence argue with itself.",
            ),
            (
                first_principle_count,
                "First-Principles Mode",
                f"{_fmt(first_principle_count)} root-cause prompts",
                "You pull the problem back to the mechanism.",
            ),
            (
                constraint_count,
                "Boundary Setter",
                f"{_fmt(constraint_count)} constraint signals",
                "You draw the lane before the agent floors it.",
            ),
            (
                closed_count,
                "Loop Closer",
                f"{_fmt(closed_count)} / {_fmt(episode_total)} episodes closed",
                "You turn chat motion into recoverable state.",
            ),
            (
                design_closed_count,
                "Design Closer",
                f"{_fmt(design_closed_count)} design/doc loops",
                "ADRs, traces, and docs count as real artifacts here.",
            ),
            (
                1 if wrong_layer_count == 0 else 0,
                "Architecture Radar",
                "0 detected wrong-layer slips",
                "This sample rarely dropped big problems into tiny fixes.",
            ),
        ]
    else:
        candidates = [
            (
                verify_count,
                "测试洁癖患者",
                f"{_fmt(verify_count)} 次主动验证",
                "从不裸奔交付，把“能跑”追问到“能交”。",
            ),
            (
                decompose_count,
                "任务切片师",
                f"{_fmt(decompose_count)} 次拆解信号",
                "复杂项目在你手里会先切片，再开火。",
            ),
            (
                cross_verify_count,
                "复核上瘾玩家",
                f"{_fmt(cross_verify_count)} 次复核信号",
                "你不迷信单一路径，知道让证据互相打架。",
            ),
            (
                first_principle_count,
                "第一性原理信徒",
                f"{_fmt(first_principle_count)} 次本质追问",
                "你会把问题拆回底层机制，不只追着表象跑。",
            ),
            (
                constraint_count,
                "边界感很强",
                f"{_fmt(constraint_count)} 次约束反推",
                "你知道先画边界，AI 才不容易越跑越远。",
            ),
            (
                closed_count,
                "闭环收纳王",
                f"{_fmt(closed_count)} / {_fmt(episode_total)} 个任务片段可识别收束",
                "你不只让 AI 做事，也会把状态收回可恢复的位置。",
            ),
            (
                design_closed_count,
                "设计闭环玩家",
                f"{_fmt(design_closed_count)} 个设计/文档闭环",
                "架构、ADR、trace 这类非代码产物也被你当成正式成果。",
            ),
            (
                1 if wrong_layer_count == 0 else 0,
                "架构显微镜",
                "0 次可识别抽象层级误判",
                "本次样本里，你很少把高层问题低层硬解。",
            ),
        ]
    selected = [
        {"title": title, "evidence": evidence, "quip": quip}
        for score, title, evidence, quip in sorted(candidates, key=lambda item: item[0], reverse=True)
        if score > 0 and evidence
    ][:3]
    if len(selected) >= 3:
        return selected
    fallback = (
        [
            {
                "title": "Local-First Player",
                "evidence": "Logs stayed local",
                "quip": "Good taste starts with context boundaries.",
            },
            {
                "title": "Retro Launcher",
                "evidence": "Structured collaboration report generated",
                "quip": "Turning vibes into evidence is already a power move.",
            },
            {
                "title": "Next Run Buffed",
                "evidence": "Reusable prompt templates are ready",
                "quip": "The next session starts with better stats.",
            },
        ]
        if _report_language(language) == "en"
        else [
            {
                "title": "本地优先玩家",
                "evidence": "日志留在本机",
                "quip": "高级玩家先保护上下文。",
            },
            {
                "title": "复盘启动器",
                "evidence": "已生成结构化协作报告",
                "quip": "能把模糊体感变成证据，本身就是工程优势。",
            },
            {
                "title": "下一轮更强",
                "evidence": "报告已给出可复制 prompt 模板",
                "quip": "下次不是重新开始，是带着诊断继续升级。",
            },
        ]
    )
    return [*selected, *fallback][:3]


def _share_card_title(achievements: list[dict[str, str]], *, language: str) -> str:
    if not achievements:
        return "Local-First Retro Player" if _report_language(language) == "en" else "本地优先复盘玩家"
    primary = achievements[0].get("title", "AI 协作玩家")
    if _report_language(language) == "en":
        if primary in {"Verification Addict", "Cross-Check Enjoyer"}:
            return "Proof-First Vibe Coder"
        if primary in {"First-Principles Mode", "Architecture Radar"}:
            return "Systems-Brain Vibe Coder"
        if primary in {"Task Slicer", "Loop Closer"}:
            return "Loop-Closing Vibe Coder"
        if primary == "Design Closer":
            return "Design-Finisher Vibe Coder"
        return "Local-First Retro Player"
    if primary in {"测试洁癖患者", "复核上瘾玩家"}:
        return "验证洁癖型 Vibe Coder"
    if primary in {"第一性原理信徒", "架构显微镜"}:
        return "工程思想派 Vibe Coder"
    if primary in {"任务切片师", "闭环收纳王"}:
        return "闭环推进型 Vibe Coder"
    if primary == "设计闭环玩家":
        return "设计收束型 Vibe Coder"
    return "本地优先复盘玩家"


def _share_title_pool(language: str) -> list[str]:
    if _report_language(language) == "en":
        return [
            "Proof-First Vibe Coder",
            "Systems-Brain Vibe Coder",
            "Loop-Closing Vibe Coder",
            "Prompt DJ",
            "Context Bodyguard",
            "Bug Reproduction Enjoyer",
            "Ship-It Impulse Slayer",
            "Design-Finisher Vibe Coder",
        ]
    return [
        "验证洁癖型 Vibe Coder",
        "工程思想派 Vibe Coder",
        "闭环推进型 Vibe Coder",
        "Prompt 玄学家",
        "上下文保镖",
        "复现狂热玩家",
        "能跑就行克星",
        "设计收束型 Vibe Coder",
    ]


def _share_title_rewrite_prompt(language: str) -> str:
    if _report_language(language) == "en":
        return (
            "Rewrite the share-card title in the developer's voice. Keep it short, "
            "playful, screenshot-friendly, and based only on the listed achievements. "
            "Do not add private facts or pretend this is a real global ranking."
        )
    return (
        "请按开发者自己的语言风格重写夸夸卡称号。要求短、好玩、适合截图，"
        "只基于 achievements 里的高光，不要添加私密事实，也不要把气氛组排名说成真实排名。"
    )


def _html_share_card(card: dict[str, Any], *, avatar_seed: str) -> str:
    language = _report_language(str(card.get("language", "zh")))
    eyebrow = "VibeCoding Observer Share Card" if language == "en" else "VibeCoding Observer 夸夸卡"
    aria = "screenshot-friendly share card" if language == "en" else "可截图分享的夸夸卡"
    pet_title = "share-card pixel pet" if language == "en" else "夸夸卡像素宠物"
    achievements = [
        item for item in _as_list(card.get("achievements"))
        if isinstance(item, dict)
    ][:3]
    pet = _pet_avatar_svg(
        f"share:{avatar_seed}:{card.get('title', '')}",
        mood="happy",
        size=150,
        title=pet_title,
    )
    achievement_html = "".join(
        '<div class="share-achievement">'
        f"<strong>{escape(str(item.get('title', '高光成就')))}</strong>"
        f"<p>{escape(str(item.get('evidence', '本地报告识别到正向信号')))}</p>"
        f"<p>{escape(str(item.get('quip', '这是一条值得保留的协作习惯。')))}</p>"
        "</div>"
        for item in achievements
    )
    return (
        '<div class="share-wrap">'
        f'<div class="share-card" aria-label="{escape(aria)}">'
        f'<span class="share-eyebrow">{escape(eyebrow)}</span>'
        f'<div class="share-title">{escape(str(card.get("title", "AI 协作高光玩家")))}</div>'
        '<div class="share-score">'
        f'<strong>{_fmt(_as_int(card.get("score")))}</strong>'
        f'<span>{escape(str(card.get("score_label", "本次高光指数")))}<br>{escape(str(card.get("headline", "")))}</span>'
        "</div>"
        f'<p>{escape(str(card.get("subtitle", "")))}</p>'
        f'<div class="share-achievements">{achievement_html}</div>'
        "</div>"
        '<div class="share-side">'
        f'<div class="share-pet">{pet}</div>'
        f'<div class="share-cta">{escape(str(card.get("cta", "")))}</div>'
        f'<div class="share-note">{escape(str(card.get("note", "")))}</div>'
        "</div>"
        "</div>"
    )


def generate_share_card_svg(profile: dict[str, Any], *, width: int = 1200, height: int = 630) -> str:
    """Render the share-card copy as a standalone, self-contained SVG."""
    card = _as_dict(profile.get("share_card"))
    language = _report_language(str(card.get("language", profile.get("report_language", "zh"))))
    eyebrow = "VibeCoding Observer Share Card" if language == "en" else "VibeCoding Observer 夸夸卡"
    aria = "VibeCoding Observer share card" if language == "en" else "VibeCoding Observer 夸夸卡"
    pet_title = "share-card pixel pet" if language == "en" else "夸夸卡像素宠物"
    achievements = [
        item for item in _as_list(card.get("achievements"))
        if isinstance(item, dict)
    ][:3]
    seed = (
        f"{profile.get('developer_type', 'unknown')}:"
        f"{profile.get('total_events', 0)}:"
        f"{profile.get('total_projects', 0)}:"
        f"{card.get('title', '')}"
    )
    achievement_blocks = []
    for idx, item in enumerate(achievements):
        top = 356 + idx * 74
        achievement_blocks.append(
            f'<rect x="64" y="{top}" width="748" height="64" rx="12" '
            'fill="#ffffff" stroke="#17202a" stroke-width="3"/>'
            f'<text x="88" y="{top + 26}" class="achievement-title">'
            f'{escape(str(item.get("title", "高光成就")))}</text>'
            f'{_svg_text_lines(str(item.get("evidence", "")), x=88, y=top + 50, max_chars=56, line_height=20, class_name="achievement-copy", max_lines=1)}'
        )
    pet = _svg_pet_avatar(
        f"share-svg:{seed}",
        mood="happy",
        x=886,
        y=96,
        size=210,
        title=pet_title,
    )
    score = _fmt(_as_int(card.get("score")))
    headline = str(card.get("headline", "你的 AI 协作高光正在加载"))
    subtitle = str(card.get("subtitle", "气氛组排名，仅供开心。"))
    title = str(card.get("title", "AI 协作高光玩家"))
    cta = str(card.get("cta", "测测你的 AI 搭子人格"))
    note = str(card.get("note", "完整吐槽在报告正文，这张卡只负责让你开心一下。"))
    title_svg = _svg_share_title(title)
    cta_svg = (
        '<text x="876" y="396" class="cta">测测你的</text>'
        '<text x="876" y="428" class="cta">AI 搭子人格</text>'
        if cta == "测测你的 AI 搭子人格"
        else (
            '<text x="876" y="396" class="cta">Find your</text>'
            '<text x="876" y="428" class="cta">AI pair persona</text>'
            if cta == "Find your AI pair persona"
            else _svg_text_lines(
                cta,
                x=876,
                y=396,
                max_chars=11,
                line_height=32,
                class_name="cta",
                max_lines=2,
            )
        )
    )
    note_svg = (
            '<text x="876" y="462" class="note">完整吐槽在报告正文</text>'
            '<text x="876" y="480" class="note">这张卡只负责让你开心一下</text>'
            if note == "完整吐槽在报告正文，这张卡只负责让你开心一下。"
            else (
            '<text x="876" y="462" class="note">Full report has the roast.</text>'
            '<text x="876" y="480" class="note">This card is just for fun.</text>'
            if note == "Full report has the roast. This card is just for fun."
            else _svg_text_lines(
                note,
                x=876,
                y=462,
                max_chars=15,
                line_height=22,
                class_name="note",
                max_lines=2,
            )
        )
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 1200 630" role="img" aria-label="{escape(aria)}">
  <title>{escape(title)}</title>
  <style>
    .eyebrow {{ font: 800 24px system-ui, -apple-system, Segoe UI, sans-serif; fill:#17202a; }}
    .title {{ font: 900 52px system-ui, -apple-system, Segoe UI, sans-serif; fill:#17202a; }}
    .score {{ font: 900 112px system-ui, -apple-system, Segoe UI, sans-serif; fill:#17202a; }}
    .score-label {{ font: 800 28px system-ui, -apple-system, Segoe UI, sans-serif; fill:#344054; }}
    .copy {{ font: 600 24px system-ui, -apple-system, Segoe UI, sans-serif; fill:#344054; }}
    .achievement-title {{ font: 800 24px system-ui, -apple-system, Segoe UI, sans-serif; fill:#17202a; }}
    .achievement-copy {{ font: 500 18px system-ui, -apple-system, Segoe UI, sans-serif; fill:#475467; }}
    .cta {{ font: 800 26px system-ui, -apple-system, Segoe UI, sans-serif; fill:#17202a; }}
    .note {{ font: 500 17px system-ui, -apple-system, Segoe UI, sans-serif; fill:#667085; }}
  </style>
  <rect width="1200" height="630" rx="0" fill="#f6f7f9"/>
  <rect x="34" y="34" width="1132" height="562" rx="24" fill="#17202a"/>
  <rect x="24" y="24" width="1132" height="562" rx="24" fill="#fffaf0" stroke="#17202a" stroke-width="6"/>
  <path d="M24 24H1156V586H24Z" fill="url(#glow)"/>
  <defs>
    <linearGradient id="glow" x1="24" y1="24" x2="1156" y2="586" gradientUnits="userSpaceOnUse">
      <stop stop-color="#dbeafe" stop-opacity="0.95"/>
      <stop offset="0.52" stop-color="#fffaf0" stop-opacity="0.25"/>
      <stop offset="1" stop-color="#dcfce7" stop-opacity="0.95"/>
    </linearGradient>
  </defs>
  <rect x="64" y="62" width="{420 if language == "en" else 360}" height="46" rx="23" fill="#dcfce7" stroke="#17202a" stroke-width="3"/>
  <text x="84" y="94" class="eyebrow">{escape(eyebrow)}</text>
  {title_svg}
  <text x="64" y="300" class="score">{escape(score)}</text>
  <text x="260" y="252" class="score-label">{escape(str(card.get("score_label", "本次高光指数")))}</text>
  {_svg_text_lines(headline, x=260, y=290, max_chars=31, line_height=30, class_name="copy", max_lines=2)}
  {_svg_text_lines(subtitle, x=64, y=334, max_chars=34, line_height=28, class_name="copy", max_lines=1)}
  {"".join(achievement_blocks)}
  <rect x="850" y="70" width="282" height="264" rx="20" fill="#f8fafc" stroke="#17202a" stroke-width="4" stroke-dasharray="12 8"/>
  {pet}
  <rect x="850" y="356" width="282" height="132" rx="16" fill="#ffffff" stroke="#17202a" stroke-width="3"/>
  {cta_svg}
  {note_svg}
</svg>
"""


def _svg_text_lines(
    text: str,
    *,
    x: int,
    y: int,
    max_chars: int,
    line_height: int,
    class_name: str,
    max_lines: int,
) -> str:
    lines = _wrap_svg_text(text, max_chars=max_chars, max_lines=max_lines)
    return "".join(
        f'<text x="{x}" y="{y + idx * line_height}" class="{class_name}">{escape(line)}</text>'
        for idx, line in enumerate(lines)
    )


def _svg_share_title(title: str) -> str:
    """Render the share-card title with stable line breaks for social cards."""
    if title.endswith(" Vibe Coder"):
        prefix = title.removesuffix(" Vibe Coder").strip()
        return (
            f'<text x="64" y="158" class="title">{escape(prefix)}</text>'
            '<text x="64" y="214" class="title">Vibe Coder</text>'
        )
    return _svg_text_lines(
        title,
        x=64,
        y=158,
        max_chars=12,
        line_height=54,
        class_name="title",
        max_lines=2,
    )


def _wrap_svg_text(text: str, *, max_chars: int, max_lines: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if " " in normalized:
        return _wrap_svg_words(normalized, max_chars=max_chars, max_lines=max_lines)
    lines: list[str] = []
    current = ""
    for char in normalized:
        if len(current) >= max_chars and char != " ":
            lines.append(current.rstrip())
            current = ""
            if len(lines) >= max_lines:
                break
        current += char
    if current and len(lines) < max_lines:
        lines.append(current.rstrip())
    if len(lines) == max_lines and len("".join(lines)) < len(normalized):
        lines[-1] = lines[-1].rstrip("，。,. ") + "..."
    return lines


def _wrap_svg_words(text: str, *, max_chars: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = word
        else:
            lines.append(word[:max_chars].rstrip())
            current = word[max_chars:].lstrip()
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and " ".join(lines) != text:
        lines[-1] = lines[-1].rstrip("，。,. ") + "..."
    return lines


def _svg_pet_avatar(
    seed: str,
    *,
    mood: str,
    x: int,
    y: int,
    size: int,
    title: str,
) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    palette = [
        ("#7dd3fc", "#0e7490", "#fef3c7", "#ecfeff"),
        ("#86efac", "#166534", "#dcfce7", "#f0fdf4"),
        ("#f9a8d4", "#9d174d", "#ffe4e6", "#fff1f2"),
        ("#c4b5fd", "#5b21b6", "#ede9fe", "#faf5ff"),
        ("#fdba74", "#9a3412", "#ffedd5", "#fff7ed"),
    ]
    body, ink, accent, background = palette[digest[0] % len(palette)]
    cells = _pixel_pet_cells(digest=digest, mood=mood)
    pixels = _pixel_cells_svg(cells, body=body, ink=ink, accent=accent)
    scale = size / 104
    return (
        f'<g transform="translate({x} {y}) scale({scale:.4f})">'
        f"<title>{escape(title)}</title>"
        f'<rect x="8" y="8" width="88" height="88" rx="10" fill="{background}" '
        'stroke="#17202a" stroke-width="4"/>'
        '<g shape-rendering="crispEdges">'
        f"{pixels}"
        "</g>"
        "</g>"
    )


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
    "act-design-closure": ("设计闭环", "架构、ADR、规范、trace 或文档型任务形成可恢复收束。"),
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
    "implementation_closed": ("实现已收束", "代码、测试或 runner 修改后有验证和收束证据。"),
    "design_closed": ("设计已收束", "文档、ADR、trace 或任务状态更新已持久化并收束。"),
    "verification_only": ("仅验证", "只执行检查或诊断，没有看到持久化修改。"),
    "blocked_or_handoff": ("阻塞/交接", "有明确阻塞、handoff、resume anchor 或下一步。"),
    "verified_unclosed": ("验证未收束", "有验证证据，但没有明确交付或关闭。"),
    "implemented_verified_unclosed": ("实现验证未收束", "已有实现和验证，但缺少交付/closeout 证据。"),
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


def _html_delivery_portrait(
    *,
    developer_type: str,
    closed_rate: float,
    verify_count: int,
    total_events: int,
) -> str:
    return (
        "<h3>你是强目标驱动的 AI 协作者"
        f"（{escape(developer_type)}）</h3>"
        "<p>你不是单纯让 AI 代写代码，而是在用 AI 推进复杂项目：会要求验证，"
        "也会用架构、文档和任务状态来收束工作。</p>"
        f"<p>这份报告读取了 {_fmt(total_events)} 条本地协作事件。"
        f"其中 {_fmt(verify_count)} 个验证信号说明你已经有工程验收意识；"
        f"{closed_rate:.1f}% 的输出任务带有收束证据，说明你的问题不是“不会用 AI”，"
        "而是某些任务入口和工作流还会制造额外拉扯。</p>"
    )


def _html_delivery_conclusion(
    *,
    label_counts: dict[str, Any],
    signal_counts: dict[str, Any],
    closed_rate: float,
) -> str:
    weak = _as_int(signal_counts.get("weak_goal")) + _as_int(signal_counts.get("unusable_goal"))
    wrong_layer = _as_int(label_counts.get("degen-wrong-layer"))
    if weak >= wrong_layer:
        friction = "任务入口太省字，目标、边界和验收没有在第一轮说清楚"
        symptom = "AI 需要猜你的真实意图，后面再靠你纠偏"
    else:
        friction = "抽象层级没有先对齐，你聊的是方向，AI 却急着进入局部实现"
        symptom = "对话中途才发现方向错了"
    return (
        "你已经能让 AI 产出代码，但主要损耗发生在 "
        f"<strong>{escape(friction)}</strong>，所以经常出现 "
        f"<strong>{escape(symptom)}</strong>。"
        f"当前可识别的任务收束率约 {closed_rate:.1f}%，这个数字表示："
        "不少任务最后能收住，但收住之前的沟通成本还可以继续降。"
    )


def _html_delivery_strengths(
    *,
    label_counts: dict[str, Any],
    closed_rate: float,
    closed_verified: int,
    episode_total: int,
) -> str:
    verify_count = _as_int(label_counts.get("eng-verify"))
    constraint_count = _as_int(label_counts.get("act-constraint-reason"))
    cards = [
        (
            "你会要求 AI 验证结果",
            f"报告看到 {_fmt(verify_count)} 个验证信号。这个数字的意思是：你不是只看 AI 说“完成了”，而是会让它跑测试、检查或给出验收证据。",
            "这是优势，因为验证习惯会把“看起来能跑”变成“我知道它为什么能交付”。",
        ),
        (
            "你有把任务拉回工程边界的意识",
            f"报告看到 {_fmt(constraint_count)} 个约束反推信号；另有 {_fmt(closed_verified)} / {_fmt(episode_total)} 个输出片段带有可识别收束证据。",
            "这是优势，因为你已经在用边界、验收和收束来管理 AI，而不是完全把判断权交给它。",
        ),
    ]
    return "".join(
        '<div class="panel strength-card">'
        f"<h3>{escape(title)}</h3>"
        f"<p><strong>行为：</strong>{escape(behavior)}</p>"
        f"<p><strong>为什么是优势：</strong>{escape(why)}</p>"
        f'<p class="subtle">任务收束率约 {closed_rate:.1f}%，口径是已验证/设计/实现闭环任务占输出任务的比例。</p>'
        "</div>"
        for title, behavior, why in cards
    )


def _html_delivery_problem_cards(
    *,
    label_counts: dict[str, Any],
    signal_counts: dict[str, Any],
    loop_counts: dict[str, Any],
    closed_rate: float,
) -> str:
    weak_count = _as_int(signal_counts.get("weak_goal")) + _as_int(signal_counts.get("unusable_goal"))
    wrong_layer = _as_int(label_counts.get("degen-wrong-layer"))
    passive = _as_int(label_counts.get("act-passive"))
    direction = _as_int(label_counts.get("waste-direction"))
    unverified = _as_int(signal_counts.get("implementation_without_verification"))
    unclosed = _as_int(signal_counts.get("verified_but_unclosed"))
    goal_only = _as_int(loop_counts.get("goal_only"))
    candidates = [
        (
            weak_count,
            "问题 1：任务入口太省字",
            "你可能只说“继续”“按你的理解推进”，或者贴一段上下文就让 AI 开始做。",
            f"报告看到 {_fmt(weak_count)} 个弱目标或不可用目标信号。它意味着：AI 收到任务时，目标、边界或验收方式不够完整。",
            "你为了省第一轮说明，把判断压力转移给了 AI；AI 会用自己的默认路径补全缺失信息。",
            "方向猜错后，后续代码、文档或验证都会跟着偏，最后靠你多轮纠正把它拉回来。",
            "请先复述我的目标，再开始做。\n目标：...\n允许范围：...\n禁止范围：...\n验收方式：...\n交付格式：先列计划，再改文件，最后报告验证结果。",
        ),
        (
            wrong_layer + direction,
            "问题 2：你聊的是方向，AI 有时急着动手",
            "你想讨论架构、判断标准或策略，AI 却直接开始改代码或给局部方案。",
            f"报告看到 {_fmt(wrong_layer)} 个抽象层级误判信号、{_fmt(direction)} 个方向纠偏信号。它意味着：对话里存在“先走错层，再纠正”的成本。",
            "AI 默认喜欢把模糊问题降级成可执行动作；如果你没先要求它判断层级，它会过早进入实现。",
            "这会造成返工、方案反复，以及本来应该先定原则的问题被写成局部补丁。",
            "先不要改文件。\n请先回答：这是设计层、实现层、验证层还是交接层的问题？\n给出 2 个可选路径、各自风险、推荐路径。\n我确认后再执行。",
        ),
        (
            passive,
            "问题 3：你有时把决策权交给 AI",
            "你可能会说“按你的建议做”“你看着办”。这能快速推进，但也让 AI 继承了太多隐含决策。",
            f"报告看到 {_fmt(passive)} 个被动放手信号。它意味着：某些关键约束没有由你明确声明。",
            "AI 会把“没有说清楚”理解成“可以自由选择”，而它的选择未必符合你的项目边界。",
            "短期看更快，长期会增加返工和方向偏移，尤其在架构、规范和数据边界任务里。",
            "你可以提方案，但不要直接执行。\n我的不可变约束是：...\n你必须列出：推荐方案、替代方案、为什么不选替代方案。\n等我确认后再改。",
        ),
        (
            unverified + unclosed + goal_only,
            "问题 4：部分任务没有形成可恢复收尾",
            "任务做了很多动作，但最后没有清楚留下“改了什么、怎么验证、下一步是什么”。",
            f"报告看到 {_fmt(unverified + unclosed)} 个验证/收束缺口信号；当前任务收束率约 {closed_rate:.1f}%。",
            "当完成定义没有提前写出来，AI 容易把“我做过了”当成“可以交付了”。",
            "下次恢复任务时，你需要重新判断状态；多人或多 agent 协作时尤其容易丢上下文。",
            "完成前必须输出 closeout：\n1. 改了什么\n2. 运行了什么验证命令\n3. 结果是什么\n4. 还没做什么\n5. 下一步接手人应该从哪里继续",
        ),
    ]
    selected = sorted(candidates, key=lambda item: item[0], reverse=True)[:3]
    return "".join(
        '<div class="panel problem-card">'
        f"<h3>{escape(title)}</h3>"
        f'<div class="problem-block"><strong>你可能遇到的场景：</strong><p>{escape(scene)}</p></div>'
        f'<div class="problem-block"><strong>报告看到的证据：</strong><p>{escape(evidence)}</p></div>'
        f'<div class="problem-block"><strong>为什么会这样：</strong><p>{escape(reason)}</p></div>'
        f'<div class="problem-block"><strong>它造成的损耗：</strong><p>{escape(loss)}</p></div>'
        f'<div class="problem-block"><strong>下次这样改：</strong><pre class="prompt-template">{escape(prompt)}</pre></div>'
        "</div>"
        for _, title, scene, evidence, reason, loss, prompt in selected
    )


def _html_priority_actions(*, signal_counts: dict[str, Any]) -> str:
    weak_count = _as_int(signal_counts.get("weak_goal")) + _as_int(signal_counts.get("unusable_goal"))
    return (
        '<ol class="priority-list">'
        "<li><strong>下一次对话就改：</strong>不要再只说“继续”。直接使用“目标 / 允许范围 / 禁止范围 / 验收方式 / 交付格式”五行模板。"
        f"这条建议绑定到 {_fmt(weak_count)} 个弱目标或不可用目标信号。</li>"
        "<li><strong>本周固定成流程：</strong>每个任务开始前先让 AI 判断层级：设计、实现、验证还是交接；确认后再允许它改文件。</li>"
        "<li><strong>之后沉淀成项目规范：</strong>把 closeout 模板写进 AGENTS.md 或 observer.yaml，让每次交付都留下验证命令、结果、未完成项和下一步。</li>"
        "</ol>"
    )


def _html_plain_language_summary(
    *,
    total_events: int,
    weak_goal: int,
    closed_rate: float,
    verify_count: int,
    top_label: str,
) -> str:
    top_title = _LABEL_EXPLANATIONS.get(top_label, (top_label or "暂无高频标签", ""))[0]
    cards = [
        (
            "这份报告在说什么",
            f"它看了 {_fmt(total_events)} 条本地 AI 编程对话，不评价你写得好不好，只找协作里反复出现的卡点。",
        ),
        (
            "你已经做得不错的地方",
            f"你经常让 AI 跑测试或检查，这是好习惯。本次识别到 {_fmt(verify_count)} 个验证信号，任务验证收束率约 {closed_rate:.1f}%。",
        ),
        (
            "最值得先看的问题",
            f"高频信号是“{top_title}”。如果你只改一件事，先把“继续”改成“目标 + 边界 + 验收”；弱目标信号有 {_fmt(weak_goal)} 次。",
        ),
    ]
    return "".join(
        '<div class="panel plain-card">'
        f"<h3>{escape(title)}</h3>"
        f"<p>{escape(body)}</p>"
        "</div>"
        for title, body in cards
    )


def _html_scenario_cards(
    *,
    label_counts: dict[str, Any],
    signal_counts: dict[str, Any],
    closed_rate: float,
) -> str:
    candidates = [
        (
            _as_int(label_counts.get("act-passive")),
            "你把决策权交给 AI",
            "你可能经常说“按你的建议做”或“你看着办”。这很快，但 AI 会把缺失的边界自己补上。",
            "下次可以这样改：先写一句不可变约束，再让 AI 给方案。",
        ),
        (
            _as_int(label_counts.get("degen-wrong-layer")),
            "你聊的是架构，AI 却开始改代码",
            "你想讨论方向、抽象或判断标准，AI 却把它当成局部实现任务处理，导致你后来纠偏。",
            "下次可以这样改：先要求它回答“这是设计层、实现层还是验证层”。",
        ),
        (
            _as_int(label_counts.get("waste-direction")),
            "聊了几轮才发现方向错了",
            "对话里出现方向级纠偏，说明 agent 很早就走偏，但直到中途才暴露。",
            "下次可以这样改：前 2 轮只做目标复述和方案对比，不急着改文件。",
        ),
        (
            _as_int(label_counts.get("eng-verify")),
            "你有验证习惯，这是优势",
            f"报告看到你会让 AI 做测试、构建或检查。当前验证收束率约 {closed_rate:.1f}%。",
            "下次可以这样改：把验证命令写进任务开头，而不是做到最后再补。",
        ),
        (
            _as_int(signal_counts.get("weak_goal")) + _as_int(signal_counts.get("unusable_goal")),
            "任务入口太省字",
            "“继续”“按你的理解推进”这类入口很省力，但会让 AI 猜目标、猜边界、猜验收。",
            "下次可以这样改：每次开头写目标、允许范围、禁止范围、验收命令。",
        ),
    ]
    selected = sorted(candidates, key=lambda item: item[0], reverse=True)[:3]
    if not any(count > 0 for count, *_ in selected):
        selected = candidates[2:5]
    return "".join(
        '<div class="panel scenario-card">'
        f"<h3>{escape(title)}</h3>"
        f"<p>{escape(body)}</p>"
        f'<div class="subtle">识别次数：{_fmt(count)}</div>'
        f'<div class="next-action">{escape(action)}</div>'
        "</div>"
        for count, title, body, action in selected
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


def _avatar_mood(diagnoses: list[Any], closed_rate: float) -> str:
    severities = {
        str(item.get("severity", ""))
        for item in diagnoses
        if isinstance(item, dict)
    }
    if "critical" in severities:
        return "alert"
    if "warning" in severities:
        return "focused"
    if closed_rate >= 75:
        return "happy"
    return "curious"


def _pet_avatar_svg(seed: str, *, mood: str, size: int, title: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    palette = [
        ("#7dd3fc", "#0e7490", "#fef3c7", "#ecfeff"),
        ("#86efac", "#166534", "#dcfce7", "#f0fdf4"),
        ("#f9a8d4", "#9d174d", "#ffe4e6", "#fff1f2"),
        ("#c4b5fd", "#5b21b6", "#ede9fe", "#faf5ff"),
        ("#fdba74", "#9a3412", "#ffedd5", "#fff7ed"),
    ]
    body, ink, accent, background = palette[digest[0] % len(palette)]
    cells = _pixel_pet_cells(digest=digest, mood=mood)
    pixels = _pixel_cells_svg(cells, body=body, ink=ink, accent=accent)
    return (
        f'<svg class="pet-svg" viewBox="0 0 104 104" width="{size}" height="{size}" '
        'role="img" aria-label="代码生成的诊断宠物头像">'
        f"<title>{escape(title)}</title>"
        f'<rect x="8" y="8" width="88" height="88" rx="10" fill="{background}" stroke="#17202a" stroke-width="4"/>'
        '<g shape-rendering="crispEdges">'
        f"{pixels}"
        "</g>"
        "</svg>"
    )


def _pixel_pet_cells(*, digest: bytes, mood: str) -> dict[tuple[int, int], str]:
    cells: dict[tuple[int, int], str] = {}

    def add(points: set[tuple[int, int]], token: str) -> None:
        for point in points:
            cells[point] = token

    body = {
        (x, y)
        for y, row in enumerate(
            [
                "00111100",
                "01111110",
                "11111111",
                "11111111",
                "11111111",
                "01111110",
                "00111100",
                "00011000",
            ],
            start=2,
        )
        for x, value in enumerate(row, start=2)
        if value == "1"
    }
    add(body, "body")

    ear_variant = digest[1] % 3
    if ear_variant == 0:
        add({(3, 1), (4, 1), (9, 1), (10, 1), (2, 2), (11, 2)}, "body")
    elif ear_variant == 1:
        add({(2, 2), (3, 1), (4, 2), (9, 2), (10, 1), (11, 2)}, "accent")
    else:
        add({(2, 3), (2, 2), (3, 2), (11, 3), (11, 2), (10, 2)}, "body")

    add({(3, 2), (4, 2), (9, 2), (10, 2)}, "outline")
    add(_pixel_eye_cells(mood), "ink")
    add(_pixel_mouth_cells(mood), "ink")

    spot_column = 4 + digest[2] % 6
    spot_row = 3 + digest[3] % 3
    add({(spot_column, spot_row), (spot_column + 1, spot_row)}, "accent")
    add(_pixel_badge_cells(mood), "accent")
    add(_pixel_badge_mark_cells(mood), "ink")
    return cells


def _pixel_eye_cells(mood: str) -> set[tuple[int, int]]:
    if mood == "alert":
        return {(4, 5), (5, 6), (8, 6), (9, 5)}
    if mood == "happy":
        return {(4, 5), (5, 5), (8, 5), (9, 5), (5, 4), (8, 4)}
    if mood == "focused":
        return {(4, 5), (5, 5), (8, 5), (9, 5), (4, 6), (5, 6), (8, 6), (9, 6)}
    return {(4, 5), (5, 5), (8, 5), (9, 5)}


def _pixel_mouth_cells(mood: str) -> set[tuple[int, int]]:
    if mood == "alert":
        return {(6, 8), (7, 8), (5, 9), (8, 9)}
    if mood == "focused":
        return {(5, 8), (6, 8), (7, 8), (8, 8)}
    if mood == "happy":
        return {(5, 8), (8, 8), (6, 9), (7, 9)}
    return {(6, 8), (7, 8), (7, 9)}


def _pixel_badge_cells(mood: str) -> set[tuple[int, int]]:
    if mood == "alert":
        return {(10, 9), (11, 9), (10, 10), (11, 10)}
    if mood == "focused":
        return {(9, 9), (10, 9), (11, 9), (10, 10), (11, 10)}
    if mood == "happy":
        return {(9, 9), (10, 9), (11, 9), (9, 10), (10, 10), (11, 10)}
    return {(10, 9), (11, 9), (11, 10)}


def _pixel_badge_mark_cells(mood: str) -> set[tuple[int, int]]:
    if mood == "alert":
        return {(11, 9), (11, 10)}
    if mood == "focused":
        return {(10, 10), (11, 9)}
    if mood == "happy":
        return {(10, 9), (10, 10), (9, 10), (11, 10)}
    return {(11, 9)}


def _pixel_cells_svg(
    cells: dict[tuple[int, int], str],
    *,
    body: str,
    ink: str,
    accent: str,
) -> str:
    colors = {
        "body": body,
        "ink": ink,
        "accent": accent,
        "outline": "#17202a",
    }
    cell_size = 6
    offset = 10
    parts = []
    for (x, y), token in sorted(cells.items(), key=lambda item: (item[0][1], item[0][0])):
        parts.append(
            f'<rect x="{offset + x * cell_size}" y="{offset + y * cell_size}" '
            f'width="{cell_size}" height="{cell_size}" fill="{colors[token]}"/>'
        )
    return "".join(parts)


def _html_diagnosis_item(item: dict[str, Any]) -> str:
    signals = [str(signal) for signal in _as_list(item.get("signals"))[:3]]
    uncertainty = [
        str(reason) for reason in _as_list(item.get("uncertainty_reasons"))[:3]
    ]
    confidence = str(item.get("confidence", "medium"))
    scenario, issue, next_action = _diagnosis_plain_language(item)
    mini_pet = _pet_avatar_svg(
        f"diagnosis:{item.get('title', '')}:{item.get('severity', '')}",
        mood=_severity_mood(str(item.get("severity", "warning"))),
        size=54,
        title="诊断项的 agent 宠物",
    )
    return (
        '<div class="diagnosis">'
        f'<div class="mini-pet">{mini_pet}</div>'
        f"<strong>{escape(str(item.get('title', '未命名诊断')))}</strong>"
        f'<div class="subtle">置信度：{escape(confidence)}</div>'
        f"<p><strong>场景：</strong>{escape(scenario)}</p>"
        f"<p><strong>问题：</strong>{escape(issue)}</p>"
        f'<div class="next-action">下次可以这样改：{escape(next_action)}</div>'
        f"{_html_signal_list(signals)}"
        f"{_html_signal_list(uncertainty)}"
        f"{_html_raw_signals(signals)}"
        "</div>"
    )


def _severity_mood(severity: str) -> str:
    if severity == "critical":
        return "alert"
    if severity == "warning":
        return "focused"
    if severity == "info":
        return "happy"
    return "curious"


def _diagnosis_plain_language(item: dict[str, Any]) -> tuple[str, str, str]:
    title = str(item.get("title", ""))
    root = str(item.get("root_cause", ""))
    recommendation = str(item.get("recommendation", ""))
    if "任务入口目标质量偏弱" in title:
        return (
            "你可能只是说“继续”“开做”或贴了一段上下文，AI 需要自己猜这次到底要交付什么。",
            "目标太短时，AI 会补全隐含需求；补错以后，后面的实现和验证都会跟着偏。",
            "把入口写成：目标 / 允许范围 / 禁止范围 / 验收命令 / 交付格式。",
        )
    if "顶层目标存在但工程闭环缺失" in title:
        return (
            "你提出了一个大方向，对话也推进了很久，但没有稳定落到可验证产物。",
            "这类 episode 看起来很忙，但缺少可恢复的实现、验证或关闭证据。",
            "超过 50 个事件还没产物时，停下来拆成 1 个可验证子任务。",
        )
    if "实现后验证/收束不足" in title:
        return (
            "AI 已经做了改动，但收尾时缺少测试、构建、人工检查或 handoff。",
            "没有收束证据时，你下次回来很难判断任务到底是完成、半成品还是需要重跑。",
            "把 Definition of Done 写进任务：必须运行哪些命令，报告哪些结果。",
        )
    if "高产但高纠缠" in title:
        return (
            "你确实产出了很多代码，但每个产出背后需要大量来回解释、纠偏和补救。",
            "这通常不是能力不足，而是任务切分、边界和验收点没有足够早地固定。",
            "把一个大任务拆成 30-60 分钟可关闭的小任务，每个任务只允许一个主目标。",
        )
    if "数据生命周期" in title:
        return (
            "AI 可能把原始素材、临时中间产物和长期资产混在一起处理。",
            "数据角色不清会导致重复生成、误覆盖和后续无法复现。",
            "先列三类数据：只读素材、可重建中间产物、必须版本化的永久资产。",
        )
    return (
        root or "这个诊断来自多个结构化信号的交叉判断。",
        "它提示某类协作成本正在反复出现，需要把隐含习惯改成显式流程。",
        recommendation or "选一条咨询路线，把它转成下一轮任务模板。",
    )


def _html_signal_profile_risk(signal_profile: dict[str, Any]) -> str:
    profile_names = [str(item) for item in _as_list(signal_profile.get("profile_names"))]
    auto_detected = [
        str(item) for item in _as_list(signal_profile.get("auto_detected_profiles"))
    ]
    unknown_keys = [str(item) for item in _as_list(signal_profile.get("unrecognized_keys"))]
    confidence = str(signal_profile.get("confidence_hint", "low"))
    source_path = signal_profile.get("source_path")
    risk_note = (
        "当前项目有明确 profile 配置，规范识别风险较低。"
        if source_path
        else "未发现显式 observer 配置；若项目使用自定义规范，未识别规则可能导致闭环低估。"
    )
    if unknown_keys:
        risk_note = "配置中存在当前版本未识别的键，部分规范信号可能被忽略。"

    rows = [
        ("诊断置信度", confidence),
        ("active profiles", ", ".join(profile_names) if profile_names else "generic"),
        ("auto detected", ", ".join(auto_detected) if auto_detected else "none"),
        ("unrecognized keys", ", ".join(unknown_keys) if unknown_keys else "none"),
    ]
    items = "".join(
        f"<li><strong>{escape(label)}:</strong> {escape(value)}</li>"
        for label, value in rows
    )
    return (
        "<h3>诊断置信度与未识别规范风险</h3>"
        f"<p>{escape(risk_note)}</p>"
        f'<ul class="signal-list">{items}</ul>'
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


def _episode_summary(
    episodes: list[EpisodeSummary],
    analyzed_total: int | None = None,
) -> dict[str, Any]:
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
        "analyzed_total": analyzed_total if analyzed_total is not None else len(episodes),
        "emitted_total": len(episodes),
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


def _effective_activation_signatures(
    report: Report,
    episodes: list[EpisodeSummary] | None = None,
) -> list[dict[str, Any]]:
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
    design_closed = sum(1 for ep in episodes or [] if ep.loop_quality == "design_closed")
    if design_closed:
        signatures.append({
            "activation": "act-design-closure",
            "count": design_closed,
            "source": "episode_loop_quality",
        })
    return sorted(signatures, key=lambda x: -x["count"])
