"""Checklist — the LLM engineering-thinking pre-flight checklist.

This is a human-readable checklist that a developer can run *before*
delegating a task to an AI coding agent, to avoid recurring degenerate
patterns.

In Phase A it's embedded in the report (section 5). In Phase B it becomes
a real-time pre-check. The checklist is intentionally static and small —
it maps 1:1 to the five defects in the taxonomy.
"""

from __future__ import annotations

__all__ = ["CHECKLIST", "CHECKLIST_ITEMS", "render_checklist"]


CHECKLIST_ITEMS: list[tuple[str, str, str]] = [
    (
        "问题分层",
        "这是匹配/推理/视觉/语义哪一层？",
        "degen-wrong-layer",
    ),
    (
        "约束反推",
        "硬约束是什么？选型满足吗？",
        "degen-intuition",
    ),
    (
        "知识 vs 能力",
        "缺的是知识(prompt可注)还是能力(需换方案)？",
        "degen-knowledge-as-ability",
    ),
    (
        "尺度假设",
        "N=1000 时还成立吗？",
        "degen-stops-at-works",
    ),
    (
        "数据生命周期",
        "哪些是永久资产/中间产物？",
        "degen-ignore-lifecycle",
    ),
]
"""(title, question, prevents_label) tuples — one per defect."""

CHECKLIST = """\
## LLM 工程化思考检查清单 (动手前自检)

{items}
""".strip()


def render_checklist() -> str:
    """Render the checklist as markdown (for embedding in reports)."""
    lines = []
    for title, question, prevents in CHECKLIST_ITEMS:
        lines.append(f"- [ ] **{title}**: {question} (防 `{prevents}`)")
    return CHECKLIST.format(items="\n".join(lines))
