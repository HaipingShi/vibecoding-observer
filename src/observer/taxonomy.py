"""Taxonomy — the closed label vocabulary (the skill's core asset).

Three orthogonal dimensions, each a closed enumeration. Labels are the only
output the Event Extractor attaches; downstream (Aggregator/Reporter) groups
by them. Because they are closed and discrete, clustering degrades to
group-by — no vectors, no heavy ML.

  Dim 1 — ResponsePattern: what the LLM did (engineering vs degenerate)
  Dim 2 — Activation:      what the user did to steer it (effective vs passive)
  Dim 3 — Waste:           where the fast-lane diverged (cost localization)

Every label here traces to a specific failure mode observed in representative
AI coding sessions. The taxonomy is closed (LLM/extractor choose from this
list) but extensible via the ``semantic_fingerprint`` escape hatch for the
long tail.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "ALL_LABELS",
    "Activation",
    "Label",
    "ResponsePattern",
    "Waste",
]


class ResponsePattern(StrEnum):
    """Dimension 1 — the LLM's response mode (engineering vs degenerate)."""

    ENG_DECOMPOSE = "eng-decompose"
    """Good baseline: listed sub-problems / approaches / tradeoffs before acting."""

    ENG_VERIFY = "eng-verify"
    """Good baseline: ran tests/harness before claiming completion."""

    ENG_CROSS_VERIFY = "eng-cross-verify"
    """Good baseline: deliberately switched agents to cross-check results
    (intentional verification, NOT firefighting). Distinguished from
    waste-handoff by the absence of correction signals after the switch."""

    DEGEN_INTUITION = "degen-intuition"
    """Defect 1: selection by name/prior/marketing, not by hard constraints."""

    DEGEN_STOPS_AT_WORKS = "degen-stops-at-works"
    """Defect 2: declared "done" then got corrected or had to rework."""

    DEGEN_KNOWLEDGE_AS_ABILITY = "degen-knowledge-as-ability"
    """Defect 3: assumed telling the model X means it can do X."""

    DEGEN_WRONG_LAYER = "degen-wrong-layer"
    """Defect 4: solved at the wrong abstraction layer (e.g. matching vs reasoning)."""

    DEGEN_IGNORE_LIFECYCLE = "degen-ignore-lifecycle"
    """Defect 5: treated all data as homogeneous input, ignoring lifecycle."""

    DEGEN_TOOL_FAIL = "degen-tool-fail"
    """A tool invocation failed (error result), a hard stall signal."""

    DEGEN_INSTANT_GRATIFICATION = "degen-instant-gratification"
    """Defect 6 (ICSE 2026, 19.3%): accepted the first working solution without
    evaluating long-term cost, scalability, or alternatives. Broader than
    stops-at-works: includes accepting suggestions without verification."""

    DEGEN_SUGGESTER_PREFERENCE = "degen-suggester-preference"
    """Defect 7 (ICSE 2026, 12.6%: blindly trusted LLM suggestions without
    critical evaluation. Detected when user accepts assistant output verbatim
    then later corrects it."""

    DEGEN_FIXATION = "degen-fixation"
    """Defect 8 (ICSE 2026, 43.4% rework): anchored on an initial approach
    and kept patching it instead of considering alternatives. Detected when
    the same file/area is edited N+ times with direction corrections."""


class Activation(StrEnum):
    """Dimension 2 — how the user steered the interaction."""

    ACT_FIRST_PRINCIPLE = "act-first-principle"
    """Mode A: first-principles analogy ("how does a human do X")."""

    ACT_SCALE_STRESS = "act-scale-stress"
    """Mode B: extreme-scale stress ("what about N=1000 / 3.2GB")."""

    ACT_AB_FALSIFY = "act-ab-falsify"
    """Mode C: empirical falsification (A/B test, comparison group)."""

    ACT_CONSTRAINT_REASON = "act-constraint-reason"
    """Mode D: constraint-based reasoning ("what type of problem is this")."""

    ACT_PASSIVE = "act-passive"
    """Inhibiting: vague instruction, no constraints given."""


class Waste(StrEnum):
    """Dimension 3 — fast-lane divergence (cost localization)."""

    WASTE_RESTATE = "waste-restate"
    """User restated the requirement within the same intent cluster."""

    WASTE_REWORK = "waste-rework"
    """Rework rounds after a premature "done"."""

    WASTE_BLIND_EDIT = "waste-blind-edit"
    """Edited a file without reading it first."""

    WASTE_DIRECTION = "waste-direction"
    """Direction correction ("not X, it's Y") triggering a big rewrite."""

    WASTE_HANDOFF = "waste-handoff"
    """Cross-agent switch followed by correction — the user switched because
    the previous agent stalled or went wrong (firefighting). Only tagged when
    a degen-* signal appears within N events after the handoff."""

    WASTE_REVERSAL = "waste-reversal"
    """An action was undone or rewritten — the same file area was edited,
    then corrected/reverted within a short window (ICSE 2026 reversal action).
    Broader than rework: includes back-and-forth edits that aren't preceded
    by a done-claim."""


class Efficiency(StrEnum):
    """Dimension 4 — collaboration efficiency (code output vs interaction cost).

    Derived from git metrics + interaction count. Not attached to individual
    events; computed at the project level by the DiagnosticEngine.
    """

    EFF_HIGH_LEVERAGE = "eff-high-leverage"
    """High code output + low interaction = strong long-range control.
    The user delegates effectively and the agent produces substantial code
    per interaction."""

    EFF_GRINDY = "eff-grindy"
    """High code output + high interaction = productive but entangled.
    Lots of code got written, but it took a lot of back-and-forth."""

    EFF_IDLE = "eff-idle"
    """Low code output + high interaction = spinning without progress.
    Many conversation turns, little actual code change."""

    EFF_SCAFFOLD = "eff-scaffold"
    """Low code output + low interaction = quick one-shot generation.
    Small project or initial scaffolding, efficiently done."""

    EFF_MAINTENANCE = "eff-maintenance"
    """High existing code + low new code + high interaction = debugging/maintaining.
    Working on existing codebase, changes are incremental."""


# Union type for any label across dimensions.
Label = ResponsePattern | Activation | Waste | Efficiency


ALL_LABELS: tuple[str, ...] = tuple(
    member.value
    for enum_cls in (ResponsePattern, Activation, Waste, Efficiency)
    for member in enum_cls
)
"""Flat tuple of every label value, for validation/iteration."""
