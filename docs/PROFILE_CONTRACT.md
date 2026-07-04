# Analysis Profile Contract

> `.analysis-profile.json` is the machine-readable handoff from VibeCoding Observer
> Phase A to downstream agents and future Phase B workflows.

## Contract Principles

- The profile is append-only for compatible changes: new optional fields may be
  added, but existing field meanings should not drift.
- Runtime extraction remains local and deterministic. The profile does not
  require network calls, embeddings, or an LLM inside the pipeline.
- Human-readable `report.md` is for diagnosis presentation; `report.html` is
  the user-facing visual artifact; this profile is for downstream agent
  consumption.
- Route-specific consulting fields are advisory contracts for the consuming
  agent. They should be specific enough to produce an artifact without guessing
  a new structure.

## Audience Split

The skill serves two audiences at the same time:

- **AI agent runtime**: needs state, trace, and guide. This profile provides
  state through aggregate fields and diagnoses, trace through signals and
  anomaly references, and guide through `consulting_routes` and
  `consulting_output`.
- **User delivery**: needs readable, understandable, actionable results.
  `report.html` provides the static visual report. The consuming agent should
  translate this profile into conversational diagnosis, route recommendations,
  and executable artifacts such as prompts, checklists, recovery plans, or
  AGENTS.md snippets.

The profile is not the final user deliverable by itself. It is the
agent-facing substrate used to produce a user-facing deliverable.

## Terminology

- Use `.analysis-profile.json` for the file name in user-facing docs.
- Use `profile` only as a generic shorthand for the loaded JSON object.
- Use `consulting_routes` for the machine-readable field name.
- Use `consulting route` for one user-facing route item.
- Use `consulting_output` for the route-specific artifact contract.

## Top-Level Fields

Required core fields:

| Field | Type | Meaning |
|---|---|---|
| `version` | string | Profile contract version emitted by the reporter. |
| `total_events` | number | Total analyzed IR events. |
| `total_projects` | number | Total analyzed projects. |
| `developer_type` | string | Aggregated collaboration type. |
| `label_distribution` | object | Global label counts keyed by label. |
| `label_by_agent` | object | Label counts grouped by source agent. |
| `top_waste_projects` | array | Projects with highest waste counts. |
| `top_degenerate_projects` | array | Projects with highest degeneration counts. |
| `effective_activations` | array | Activation labels sorted by count. |
| `anomalies` | array | Selected anomaly summaries. |
| `checklist` | array | Structured engineering-thinking checklist. |
| `consulting_routes` | array | Dynamic consulting entry points generated from current evidence. |

Conditionally present fields:

| Field | Type | Present when |
|---|---|---|
| `diagnoses` | array | Cross-diagnostic findings are available. |
| `episode_summary` | object | Episode summaries were computed. |
| `episodes` | array | Episode summaries were computed; capped and sorted for consumption. |

## Consulting Routes

`consulting_routes` is the product-facing bridge from diagnosis to AI-assisted
development consulting. It must contain 3-5 routes when enough evidence exists;
when evidence is sparse, fallback routes are allowed and must use
`source: "fallback"`.

Each route object must contain:

| Field | Type | Meaning |
|---|---|---|
| `title` | string | User-facing consulting path. |
| `why_this_route` | array[string] | 1-3 concrete signals from this run. |
| `what_i_can_produce` | string | Concrete artifact the agent can produce. |
| `consulting_output` | object | Output contract for the selected route. |
| `source` | string | Evidence source, such as `diagnosis`, `episode_signal`, `label_distribution`, or `fallback`. |
| `priority` | number | Stable sort key; lower comes first. |

Route ordering is evidence-first:

1. Section VII diagnoses and their signals.
2. Episode diagnostic signals.
3. Label distribution signals.
4. Fallback routes only when no stronger evidence exists.

## Consulting Output

`consulting_output` tells the consuming agent how to expand a selected route
into an actionable consulting artifact.

See `docs/CONSULTING_OUTPUT_EXAMPLES.md` for stable response examples after a
user selects a route.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `output_type` | string | Artifact type to produce, for example `project_start_prompt` or `task_flow_plan`. |
| `sections` | array[string] | Required output sections for the artifact. |
| `starter_questions` | array[string] | Optional clarifying questions. Ask only when answers materially change the artifact. |
| `completion_criteria` | array[string] | Conditions for judging the consulting artifact complete. |

Minimum constraints:

- `sections` must be non-empty.
- `starter_questions` must be non-empty.
- `completion_criteria` must be non-empty.
- The consuming agent should cite the selected route's `why_this_route` signals
  when generating the artifact.
- The consuming agent should not present fixed menus when dynamic routes are
  available.

Known output types:

- `project_start_prompt`
- `task_prompt_template`
- `verification_closure_checklist`
- `data_lifecycle_map`
- `task_flow_plan`
- `agent_instructions_snippet`
- `mid_project_recovery_plan`
- `prompt_rewrite`
- `delivery_closure_protocol`
- `architecture_level_review`
- `activation_sop`
- `project_preflight`
- `frontend_preflight`
- `scope_recovery`
- `diagnosis_action_plan`
- `consulting_action_plan`

## Episode Summary

When present, `episode_summary` contains aggregate task-loop signals:

| Field | Type | Meaning |
|---|---|---|
| `total` | number | Total segmented episodes. |
| `loop_quality_counts` | object | Counts by loop quality. |
| `goal_quality_counts` | object | Counts by goal quality. |
| `goal_extraction_counts` | object | Counts by goal extraction method. |
| `diagnostic_signal_counts` | object | Counts by derived episode diagnostic signal. |
| `top_projects` | array | Projects with most episodes. |

`episodes` preserves capped per-episode detail for deep inspection. It should
retain both original `goal` and decoded `normalized_goal`.
