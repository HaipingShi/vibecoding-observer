"""DiagnosticEngine — the "四诊交叉" brain of the diagnostic framework.

Takes all four diagnostic signals and applies cross-rules to produce
structured diagnoses with actionable recommendations. This is where the
"望闻问切" framework produces its insights — not in isolation, but by
combining signals.

Inputs:
  - ProjectProfile (望): project type, constraint maturity, structure
  - GitMetrics (切): code output, efficiency, reversal ratio
  - Report (闻+问): label distribution, developer type, waste patterns

Output:
  - list[Diagnosis]: each has a finding, severity, root cause, and
    actionable recommendation.

Rules are deliberately simple threshold-based cross-checks, not ML.
Each rule states which signals it combines and what it concludes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from observer.aggregator import Report
from observer.efficiency import classify_efficiency
from observer.episode import EpisodeSummary
from observer.git_analyzer import GitMetrics
from observer.project_scanner import ProjectProfile
from observer.taxonomy import Efficiency as EffEnum

__all__ = ["Diagnosis", "DiagnosticEngine", "diagnose"]


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """A single cross-dimensional diagnosis finding."""

    title: str
    """Short title for the finding."""

    severity: str
    """info | warning | critical."""

    root_cause: str
    """What's actually causing the observed pattern."""

    recommendation: str
    """Specific actionable next step."""

    signals: list[str] = field(default_factory=list)
    """Which diagnostic signals triggered this finding."""

    confidence: str = "medium"
    """low | medium | high confidence in this diagnosis under current profiles."""

    uncertainty_reasons: list[str] = field(default_factory=list)
    """Why this diagnosis may be incomplete or profile-dependent."""


class DiagnosticEngine:
    """Apply cross-diagnostic rules to produce findings.

    The engine is stateless; call :meth:`diagnose` with all four signals.
    """

    def diagnose(
        self,
        project: ProjectProfile | None,
        git: GitMetrics | None,
        report: Report | None,
        episodes: list[EpisodeSummary] | None = None,
    ) -> list[Diagnosis]:
        """Run all cross-rules and return matching diagnoses.

        Args:
            project: Project profile (望). None if not available.
            git: Git metrics (切). None if not a git repo.
            report: Aggregator report (闻+问). None if no conversation data.
            episodes: Task-level episode summaries. None if not available.

        Returns:
            List of Diagnosis findings, ordered by severity (critical first).
        """
        findings: list[Diagnosis] = []

        if project:
            findings.extend(self._check_constraint_gap(project, report))
            findings.extend(self._check_structure_health(project, report))

        if git and report:
            findings.extend(self._check_efficiency(git, project, report))
            findings.extend(self._check_reversal_churn(git, report))

        if report:
            findings.extend(self._check_layer_confusion(project, report))
            findings.extend(self._check_doc_lifecycle(project, report))

        if episodes:
            findings.extend(self._check_episode_goal_loop(episodes))
            findings.extend(self._check_episode_verification_gap(episodes))
            findings.extend(self._check_episode_goal_quality(episodes))

        # Sort: critical > warning > info.
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda d: severity_order.get(d.severity, 9))
        return findings

    # ----------------------------------------------------------------- #
    # Cross-rules
    # ----------------------------------------------------------------- #

    def _check_constraint_gap(
        self, project: ProjectProfile, report: Report | None
    ) -> list[Diagnosis]:
        """望 × 问: missing constraint files + high degen rate → root cause."""
        if project.has_ai_constraint and project.strata_completeness > 0.5:
            return []

        degen_rate = 0.0
        if report and report.total_events > 0:
            degen_events = sum(
                1 for ps in report.project_summaries for _ in range(ps.degenerate_count)
            )
            degen_rate = min(1.0, degen_events / report.total_events) if report.total_events > 0 else 0

        if degen_rate < 0.05 and project.constraint_maturity > 0.3:
            return []

        missing = []
        if not project.has_ai_constraint:
            missing.append("AI coding 约束文件 (CLAUDE.md/AGENTS.md)")
        if project.strata_completeness < 0.4:
            missing.append("StraTA 文档 (STRATEGY/TASKS/HANDOFF)")

        return [Diagnosis(
            title="约束缺失导致冷启动退化",
            severity="warning" if degen_rate < 0.1 else "critical",
            root_cause=(
                f"项目缺少{' 和 '.join(missing)}，每次会话从零开始推理，"
                "模型无法继承上下文和架构约束，导致重复犯同类错误。"
            ),
            recommendation=(
                "添加 CLAUDE.md 或 AGENTS.md，定义项目架构分层、数据模型约束、"
                "允许/禁止的操作。对于复杂项目，启用 StraTA 最小模式（STRATEGY + "
                "TASKS + HANDOFF）。"
            ),
            signals=[f"constraint_maturity={project.constraint_maturity}", f"degen_rate={degen_rate:.1%}"],
            confidence="high" if project.total_files > 0 else "medium",
        )]

    def _check_structure_health(
        self, project: ProjectProfile, report: Report | None
    ) -> list[Diagnosis]:
        """望: project type mismatch or structural issues."""
        if project.project_type == "doc-vault" and not project.has_ai_constraint:
            return [Diagnosis(
                title="文档知识库缺少数据生命周期定义",
                severity="info",
                root_cause="doc-vault 项目没有 AI 约束文件，模型不区分原始素材/中间产物/永久资产。",
                recommendation="在 AGENTS.md 中定义三层数据模型：原始素材表 / 中间产物表 / 永久资产表。",
                signals=["project_type=doc-vault", f"has_constraint={project.has_ai_constraint}"],
                confidence="high",
            )]
        return []

    def _check_efficiency(
        self, git: GitMetrics, project: ProjectProfile | None, report: Report
    ) -> list[Diagnosis]:
        """切 × 问: efficiency classification → recommendation."""
        eff = classify_efficiency(git, project)
        if eff == EffEnum.EFF_HIGH_LEVERAGE:
            return [Diagnosis(
                title="高杠杆协作模式",
                severity="info",
                root_cause="少量交互产出大量代码，说明委托策略有效、约束清晰。",
                recommendation="当前模式可持续。建议将有效激活手法沉淀为 SOP 或 CLAUDE.md 片段。",
                signals=[f"efficiency={eff.value}", f"net_lines={git.net_lines}", f"interactions={git.interaction_count}"],
                confidence="high",
            )]
        if eff == EffEnum.EFF_IDLE:
            return [Diagnosis(
                title="空转型开发",
                severity="warning",
                root_cause="交互很多但代码产出少。可能在探索/设计阶段，也可能卡在某个问题上。",
                recommendation="检查是否有 degen-wrong-layer 或 fixation 集中的会话段。如果是探索阶段则正常；如果是卡住，考虑切换策略或引入新约束。",
                signals=[f"efficiency={eff.value}", f"net_lines={git.net_lines}", f"interactions={git.interaction_count}"],
                confidence="medium",
            )]
        if eff == EffEnum.EFF_GRINDY:
            return [Diagnosis(
                title="高产但高纠缠",
                severity="warning",
                root_cause="代码量可观但交互次数也多，反复拉扯才产出。",
                recommendation="识别纠缠热点：哪个模块/任务消耗最多轮次？针对性优化（拆分任务、添加约束、或引入 A/B 验证减少试错）。",
                signals=[f"efficiency={eff.value}", f"net_lines={git.net_lines}", f"interactions={git.interaction_count}"],
                confidence="medium",
            )]
        return []

    def _check_reversal_churn(
        self, git: GitMetrics, report: Report
    ) -> list[Diagnosis]:
        """切 × 问: high deletion ratio + waste-reversal → churn."""
        if git.deletion_ratio < 0.3:
            return []
        reversal_count = report.label_count("waste-reversal")
        if reversal_count < 5:
            return []
        return [Diagnosis(
            title="高废弃率——反复改写同一区域",
            severity="warning",
            root_cause=f"git 删除率 {git.deletion_ratio:.0%}，且检测到 {reversal_count} 次 reversal action。",
            recommendation="检查是否在同一文件/模块上来回改。考虑先写 spec/acceptance 再实现，减少试错式修改。",
            signals=[f"deletion_ratio={git.deletion_ratio:.1%}", f"waste-reversal={reversal_count}"],
            confidence="high",
        )]

    def _check_layer_confusion(
        self, project: ProjectProfile | None, report: Report
    ) -> list[Diagnosis]:
        """问: degen-wrong-layer dominance → layer confusion pattern."""
        wrong_layer = report.label_count("degen-wrong-layer")
        if wrong_layer < 10:
            return []
        total_degen = sum(
            ps.degenerate_count for ps in report.project_summaries
        )
        if total_degen == 0:
            return []
        ratio = wrong_layer / total_degen if total_degen > 0 else 0
        if ratio < 0.2:
            return []

        proj_hint = ""
        if project and project.project_type == "complex-app":
            proj_hint = "复杂项目的层级误判部分源于结构复杂度，但"
        return [Diagnosis(
            title="层级误判是头号退化模式",
            severity="warning" if ratio < 0.4 else "critical",
            root_cause=(
                f"{proj_hint}模型反复把高层语义问题（推理/叙事/设计）降级为"
                "低层实现问题（匹配/数据结构/格式），导致用户频繁纠偏。"
            ),
            recommendation=(
                "每次任务开始前强制执行层级判断：'这是匹配/推理/视觉/语义哪一层？'"
                "在 CLAUDE.md 中定义项目的架构分层，让模型从结构推断正确的抽象层。"
            ),
            signals=[f"degen-wrong-layer={wrong_layer}", f"ratio={ratio:.0%}"],
            confidence="medium",
        )]

    def _check_doc_lifecycle(
        self, project: ProjectProfile | None, report: Report
    ) -> list[Diagnosis]:
        """问: degen-ignore-lifecycle in doc projects."""
        lifecycle = report.label_count("degen-ignore-lifecycle")
        if lifecycle < 10:
            return []
        is_doc = project and project.project_type == "doc-vault"
        return [Diagnosis(
            title="数据生命周期混淆" + ("（文档项目高频）" if is_doc else ""),
            severity="warning",
            root_cause="模型不区分原始素材、中间产物、永久资产，把所有数据当同质输入。",
            recommendation=(
                "在项目约束文件中明确定义数据三层："
                "①原始素材（只读引用）②中间产物（可重建）③永久资产（版本化）。"
            ),
            signals=[f"degen-ignore-lifecycle={lifecycle}", f"project_type={project.project_type if project else 'unknown'}"],
            confidence="medium",
        )]

    def _check_episode_goal_loop(self, episodes: list[EpisodeSummary]) -> list[Diagnosis]:
        """问: task-like goals with long interaction but no engineering loop."""
        total = len(episodes)
        if total == 0:
            return []
        top_level_gap = _count_signal(episodes, "top_level_goal_without_engineering_loop")
        long_goal_only = _count_signal(episodes, "long_goal_only_episode")
        if top_level_gap < 10:
            return []
        ratio = top_level_gap / total
        if ratio < 0.1:
            return []
        confidence = _episode_diagnosis_confidence(
            episodes,
            "top_level_goal_without_engineering_loop",
        )
        return [Diagnosis(
            title="顶层目标存在但工程闭环缺失",
            severity="warning" if ratio < 0.25 else "critical",
            root_cause=(
                "在当前 signal profile 下，多个任务片段能识别出明确目标，"
                "但未识别到 implementation / verification / closure 这类工程闭环信号。"
            ),
            recommendation=(
                "在每个任务开始时要求 agent 输出：目标、约束、验收方式、完成定义。"
                "如果一个 episode 超过 50 个事件仍未进入实现/验证，强制暂停并重新分解任务；"
                "如果项目使用自定义规范，补充 observer.yaml 的 artifact/verify/closure 规则。"
            ),
            signals=[
                f"top_level_goal_without_engineering_loop={top_level_gap}",
                f"long_goal_only_episode={long_goal_only}",
                f"episode_total={total}",
                f"ratio={ratio:.0%}",
            ],
            confidence=confidence,
            uncertainty_reasons=_episode_uncertainty_reasons(confidence),
        )]

    def _check_episode_verification_gap(self, episodes: list[EpisodeSummary]) -> list[Diagnosis]:
        """问: implementation happened but verification/closure is weak."""
        total = len(episodes)
        if total == 0:
            return []
        unverified = _count_signal(episodes, "implementation_without_verification")
        unclosed = _count_signal(episodes, "verified_but_unclosed")
        gap = unverified + unclosed
        if gap < 10:
            return []
        ratio = gap / total
        if ratio < 0.05:
            return []
        confidence = _episode_diagnosis_confidence(
            episodes,
            "implementation_without_verification",
            "verified_but_unclosed",
        )
        return [Diagnosis(
            title="实现后验证/收束不足",
            severity="warning",
            root_cause=(
                "在当前 signal profile 下，部分 episode 已进入代码修改或验证动作，"
                "但没有形成稳定的验证-收束闭环，"
                "容易让任务停在“做过了”而不是“可交付”。"
            ),
            recommendation=(
                "把每个任务的 Definition of Done 写成可执行检查：测试命令、构建命令、"
                "人工验收点和最终交接摘要。完成前不允许只报告实现步骤。"
            ),
            signals=[
                f"implementation_without_verification={unverified}",
                f"verified_but_unclosed={unclosed}",
                f"episode_total={total}",
                f"ratio={ratio:.0%}",
            ],
            confidence=confidence,
            uncertainty_reasons=_episode_uncertainty_reasons(confidence),
        )]

    def _check_episode_goal_quality(self, episodes: list[EpisodeSummary]) -> list[Diagnosis]:
        """问: weak or unusable goals indicate poor task framing."""
        total = len(episodes)
        if total == 0:
            return []
        weak = _count_signal(episodes, "weak_goal")
        metadata = _count_signal(episodes, "metadata_goal")
        unusable = _count_signal(episodes, "unusable_goal")
        noisy = weak + metadata
        if noisy < 20:
            return []
        ratio = noisy / total
        if ratio < 0.1:
            return []
        return [Diagnosis(
            title="任务入口目标质量偏弱",
            severity="warning",
            root_cause=(
                "大量 episode 的起点是弱口令、运行时元数据或不可消费目标，"
                "模型需要从隐含上下文中猜任务，容易退化为动作执行。"
            ),
            recommendation=(
                "减少“继续/开做/go”式入口；改为一句话写清目标、边界和验收。"
                "对于从 IDE/选区发起的任务，保留选区上下文，但必须补一句真实请求。"
            ),
            signals=[
                f"weak_goal={weak}",
                f"metadata_goal={metadata}",
                f"unusable_goal={unusable}",
                f"episode_total={total}",
                f"ratio={ratio:.0%}",
            ],
            confidence="high",
        )]


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def diagnose(
    project: ProjectProfile | None = None,
    git: GitMetrics | None = None,
    report: Report | None = None,
    episodes: list[EpisodeSummary] | None = None,
) -> list[Diagnosis]:
    """One-shot cross-diagnosis without instantiating."""
    return DiagnosticEngine().diagnose(project, git, report, episodes)


def _count_signal(episodes: list[EpisodeSummary], signal: str) -> int:
    return sum(1 for ep in episodes if signal in ep.diagnostic_signals)


def _episode_diagnosis_confidence(
    episodes: list[EpisodeSummary],
    *signals: str,
) -> str:
    matched = [ep for ep in episodes if any(signal in ep.diagnostic_signals for signal in signals)]
    if not matched:
        return "low"
    high = sum(1 for ep in matched if ep.confidence == "high")
    low = sum(1 for ep in matched if ep.confidence == "low")
    if low / len(matched) > 0.2:
        return "low"
    if high / len(matched) >= 0.8:
        return "high"
    return "medium"


def _episode_uncertainty_reasons(confidence: str) -> list[str]:
    if confidence == "high":
        return []
    reasons = [
        "possible_unconfigured_project_profile",
        "possible_unrecognized_tool_event",
        "possible_docs_or_governance_only_task",
    ]
    if confidence == "low":
        reasons.append("low_episode_loop_confidence")
    return reasons
