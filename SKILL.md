---
name: vibecoding-observer
description: "Analyze vibe-coding and AI coding agent collaboration history to reveal why LLM doesn't think engineering-grade, and what interaction patterns activate it. Reads Claude Code / Codex session logs locally."
risk: unknown
source: community
date_added: "2026-06-30"
---

# VibeCoding Observer

> Measure the divergence between LLM default thinking and the engineering fast-lane.

## When to Trigger

Trigger when the user says any of:
- "分析我的开发对话/协作历史"
- "为什么 LLM 不工程化思考"
- "分析我的交互模式/卡点"
- "analyze my agent collaboration history"
- "why doesn't the LLM think engineering-grade"
- "what interaction patterns work best with AI agents"

**Do NOT trigger for**: code review, bug fixing, writing code, debugging.

## Execution Protocol

Follow these steps **in order**. Do not skip steps.

### Delivery model: agent state vs user deliverable

This skill has two audiences:
- **AI agent runtime** — needs state / trace / guide. Use `report.md` and
  `.analysis-profile.json` as structured state, evidence trace, and follow-up
  guide.
- **User delivery** — needs readable, understandable, actionable results. Do
  not only hand back file paths. Use `report.html` as the static visual report,
  present the diagnosis in conversation, explain why each route is recommended,
  and produce executable artifacts when the user chooses a route.

Treat `.analysis-profile.json` as agent-facing machinery. Treat `report.html`,
the final conversation response, and any generated prompt/checklist/recovery
plan as the user-facing deliverables.

### Step 1: Check if VibeCoding Observer is installed

```bash
which vibecoding-observer 2>/dev/null || python -c "import observer" 2>/dev/null
```

If not found, install it from the project repository. Do not install the PyPI
package named `agentlens`; it is not this project.

```bash
git clone https://github.com/HaipingShi/vibecoding-observer.git /tmp/vibecoding-observer
cd /tmp/vibecoding-observer && uv sync --extra dev
```

### Step 2: Choose scan scope

Before running the pipeline, ask the user which scope they want:

1. Current project only (recommended default)
2. A specific project path
3. All AI coding history on this machine

Do not silently scan all history. If the user does not answer and the execution
environment is non-interactive, use current project only.

### Step 3: Run the pipeline

Current project:

```bash
vibecoding-observer --current-project --source all --output /tmp/vibecoding_observer_report
```

Specific project:

```bash
vibecoding-observer --project /path/to/project --source all --output /tmp/vibecoding_observer_report
```

All history:

```bash
vibecoding-observer --all-history --source all --output /tmp/vibecoding_observer_report
```

This is fully local — no network calls. It reads `~/.claude/projects/` and `~/.codex/sessions/`.

If the user's sessions are in custom locations:

```bash
vibecoding-observer --current-project --source all --claude-dir /custom/claude/projects --codex-dir /custom/codex/sessions --output /tmp/vibecoding_observer_report
```

If no sessions are found, VibeCoding Observer prints which directories it checked. Ask the user for the correct paths and retry with `--claude-dir` / `--codex-dir`.

### Step 4: Read the report

```bash
cat /tmp/vibecoding_observer_report/report.md
```

The output directory also contains `/tmp/vibecoding_observer_report/report.html`, a
self-contained visual report for the user. Read `report.md` and
`.analysis-profile.json` for analysis; give the user the HTML report path when
presenting the result.

The Markdown report has Section 〇 plus Sections I-VII. **You (the agent) are
the analyzer** — the pipeline does statistics, you do the insight.

### Step 5: Analyze and present to user

Present results in this structure:

1. **四诊概览** — Read Section 〇. Summarize project structure (望), interaction signals (闻+问), git pulse (切), and cross-diagnosis count.
2. **全景** — How many projects, events, handoffs. What agents are used.
3. **退化诊断** — Read Section II. Which defects dominate? Give specific examples from Section VI fragments.
4. **激活手法** — Read Section III. Which activation mode is most used? Distill the top one into a reusable SOP for the user.
5. **偏差定位** — Read Section IV. Which waste type costs the most? Name the worst project and explain why.
6. **异常片段分析** — Read Section VI carefully. For each anomaly: explain WHAT went wrong, WHY (root cause), and HOW to avoid it next time.
7. **诊断建议** — Read Section VII. Present the highest-severity diagnoses and recommendations.
8. **检查清单** — Extract the checklist from Section V. Offer it as a pre-task ritual the user can run before delegating to any agent.

**Language**: Match the user's language. If they speak Chinese, present in Chinese. If English, present in English.

### Step 6: Generate diagnostic consulting routes

After presenting the diagnosis, do **not** stop at a static report and do
**not** show a fixed menu as the default. Generate 3-5 consulting routes from
the diagnosis that was just produced.

If `/tmp/vibecoding_observer_report/.analysis-profile.json` contains
`consulting_routes`, present those routes first. They are generated by the
pipeline from the current run's diagnostic evidence. If a route contains
`consulting_output`, use it as the output contract for the follow-up:
- `output_type` tells you what artifact to produce.
- `sections` tells you the required structure.
- `starter_questions` gives optional clarification questions; ask at most 1-3
  only if the answer materially changes the artifact.
- `completion_criteria` tells you how to judge whether the consulting output is
  complete.

If `consulting_routes` is missing (older compatibility version or sparse output),
build the routes from the strongest available signals:
- Section VII diagnoses and their `signals`
- project type / constraint maturity / efficiency profile from Section 〇
- top degenerate labels from Section II
- top waste labels and projects from Section IV
- anomaly themes from Section VI
- `episode_summary` fields in `.analysis-profile.json`, especially
  `goal_quality_counts`, `goal_extraction_counts`, and
  `diagnostic_signal_counts`

Each route must include:
- **Title** — a user-facing consulting path generated from this diagnosis.
- **Why this route** — cite 1-3 concrete signals from this run.
- **What I can produce** — name a concrete deliverable, such as a project-start
  prompt, frontend preflight checklist, recovery plan, architecture review
  frame, API/data-model review checklist, or AGENTS.md/CLAUDE.md snippet.
- **Consulting output** — when present, follow its output type, sections,
  starter questions, and completion criteria.

Use this structure:

```markdown
基于这次诊断，我建议你优先看这几个方向：

1. <动态生成的咨询方向>
   为什么推荐：<引用本次诊断信号>
   我可以产出：<具体可交付物>

2. <动态生成的咨询方向>
   为什么推荐：<引用本次诊断信号>
   我可以产出：<具体可交付物>

3. <动态生成的咨询方向>
   为什么推荐：<引用本次诊断信号>
   我可以产出：<具体可交付物>
```

Only if the report is too sparse to support dynamic routes, use fallback
examples like these:

```markdown
- 项目开始前建议
- 前端开发开始前建议
- 项目做到一半失去方向和控制
- 后端 / API / 数据模型建议
- AI 协作规范生成
- 深挖某个项目或异常片段
- 换数据范围重跑
```

If the user chooses a path:
- Tailor the advice to the diagnosis just produced. Mention the relevant
  signals, such as top degenerate labels, Section VII diagnoses, project type,
  efficiency profile, episode goal quality, or verification gaps.
- If the selected route has `consulting_output`, produce that artifact type and
  follow the listed sections.
- Use the stable examples in `docs/CONSULTING_OUTPUT_EXAMPLES.md` when this
  repository is available; otherwise follow the same shape from
  `consulting_output`.
- Ask at most 1-3 clarifying questions only when needed.
- Produce actionable consulting output: checklist, project-start prompt,
  architecture review frame, recovery plan, or AGENTS.md/CLAUDE.md snippet.
- Do not present the advice as personal to the skill author. It is for the
  current user running VibeCoding Observer.

## Understanding the Output

### Labels (28 total, closed vocabulary)

**ResponsePattern** — What the LLM did:
- `eng-decompose`: listed sub-problems before acting (good)
- `eng-verify`: ran tests before claiming done (good)
- `eng-cross-verify`: deliberately switched agents to cross-check (good)
- `degen-intuition`: selected by name/prior, not constraints (defect 1)
- `degen-stops-at-works`: declared "done" then got corrected (defect 2)
- `degen-knowledge-as-ability`: assumed prompt injection = capability (defect 3)
- `degen-wrong-layer`: solved at wrong abstraction layer (defect 4)
- `degen-ignore-lifecycle`: didn't distinguish data lifecycle stages (defect 5)
- `degen-tool-fail`: tool invocation errored
- `degen-instant-gratification`: accepted the first working solution without evaluating long-term cost
- `degen-suggester-preference`: trusted the LLM suggestion without critical evaluation
- `degen-fixation`: anchored on an initial approach and repeatedly patched it

**Activation** — How the user steered:
- `act-first-principle`: "how does a human do X" / first principles
- `act-scale-stress`: "what if N=1000" / extreme scale
- `act-ab-falsify`: A/B test / comparison / falsification
- `act-constraint-reason`: "what type of problem is this" / constraints
- `act-passive`: vague instruction, no constraints (inhibiting)

**Waste** — Where the fast-lane diverged:
- `waste-restate`: user restated the requirement
- `waste-rework`: rework after premature "done"
- `waste-blind-edit`: edited without reading first
- `waste-direction`: direction correction triggering rewrite
- `waste-handoff`: firefighting agent switch (NOT cross-verify)
- `waste-reversal`: action was undone or rewritten after correction

**Efficiency** — Project-level code output vs interaction cost:
- `eff-high-leverage`: lots of code, few interactions
- `eff-grindy`: lots of code, lots of interactions
- `eff-idle`: little code, many interactions
- `eff-scaffold`: small one-shot scaffold/prototype
- `eff-maintenance`: existing-code maintenance with incremental changes

### Handoff Classification

Cross-agent switches are NOT all negative:
- `waste-handoff`: switch + correction follows = firefighting (bad)
- `eng-cross-verify`: switch + verification intent = intentional cross-check (good)
- No label: switch + neither = normative handoff (neutral, e.g. StraTA template)

## Privacy

Fully local. Zero network calls. No data leaves the machine.

## Known Limitations

- `result_ok` resolves on a forward pass only, so malformed tool result order
  can reduce confidence
- Keyword dictionaries cover Chinese + English; other languages need calibration
- Pre-alpha: pipeline stable, keywords need tuning per workflow
