"""Efficiency classifier — the code-vs-interaction diagnostic.

Combines GitMetrics (code output) with interaction count to classify a
project's collaboration efficiency into one of 5 patterns:

    high-leverage:  lots of code, few interactions → strong control
    grindy:         lots of code, lots of interactions → productive but entangled
    idle:           little code, lots of interactions → spinning
    scaffold:       little code, few interactions → quick one-shot
    maintenance:    high existing code, low new code, high interaction → debugging

The thresholds are tunable; they default to empirical values calibrated
against real project data (82 projects, 165K events).
"""

from __future__ import annotations

from typing import ClassVar

from observer.git_analyzer import GitMetrics
from observer.project_scanner import ProjectProfile
from observer.taxonomy import Efficiency

__all__ = ["EfficiencyProfile", "classify_efficiency"]


# Tunable thresholds (calibrated against real data).
# "High" code = more than this many net lines added.
_HIGH_CODE_THRESHOLD = 500
# "High" interaction = more than this many events.
_HIGH_INTERACTION_THRESHOLD = 1000


def classify_efficiency(
    git: GitMetrics,
    project: ProjectProfile | None = None,
) -> Efficiency:
    """Classify a project's collaboration efficiency.

    Args:
        git: Git metrics (must include interaction_count set externally).
        project: Optional project profile (used for maintenance detection).

    Returns:
        One of the 5 Efficiency enum values.
    """
    interactions = git.interaction_count
    net_code = git.net_lines

    high_code = net_code >= _HIGH_CODE_THRESHOLD
    high_interaction = interactions >= _HIGH_INTERACTION_THRESHOLD

    # Maintenance: lots of existing code (total_files proxy), low new code,
    # high interaction → debugging/refactoring existing codebase.
    if (
        project
        and project.total_files > 100
        and net_code < _HIGH_CODE_THRESHOLD * 0.5
        and high_interaction
    ):
        return Efficiency.EFF_MAINTENANCE

    if high_code and not high_interaction:
        return Efficiency.EFF_HIGH_LEVERAGE

    if high_code and high_interaction:
        return Efficiency.EFF_GRINDY

    if not high_code and high_interaction:
        return Efficiency.EFF_IDLE

    # Low code + low interaction.
    return Efficiency.EFF_SCAFFOLD


class EfficiencyProfile:
    """Human-readable interpretation of an efficiency classification."""

    DESCRIPTIONS: ClassVar[dict[str, str]] = {
        Efficiency.EFF_HIGH_LEVERAGE: (
            "长程控制力强——用少量交互产出了大量代码。当前协作模式高效可持续，"
            "值得沉淀为可复用 SOP。"
        ),
        Efficiency.EFF_GRINDY: (
            "高产出但高纠缠——代码量可观，但交互次数也很多，说明反复拉扯才产出。"
            "建议识别纠缠热点（哪个模块/任务消耗最多轮次），针对性优化。"
        ),
        Efficiency.EFF_IDLE: (
            "空转——交互很多但代码产出少。可能是探索/设计阶段，也可能是卡在某个"
            "问题上反复纠缠。建议检查是否有 degen-wrong-layer 或 fixation 集中的"
            "会话段。"
        ),
        Efficiency.EFF_SCAFFOLD: (
            "一次性高效——少量交互产出少量代码，典型的脚手架/原型场景。"
        ),
        Efficiency.EFF_MAINTENANCE: (
            "维护型——在已有代码库上做增量修改，交互多但新增代码少是正常的。"
            "重点看 reversal_ratio 和 degen-fixation 是否偏高。"
        ),
    }

    def __init__(self, efficiency: Efficiency) -> None:
        self.efficiency = efficiency

    @property
    def description(self) -> str:
        return self.DESCRIPTIONS.get(self.efficiency, "")

    @property
    def label(self) -> str:
        return self.efficiency.value
