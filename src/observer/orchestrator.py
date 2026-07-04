"""Orchestrator — wire the full pipeline end-to-end.

Chains every component:

    Adapter → Federator → Extractor → Aggregator → AnomalyDetector
            → Reporter → (report.md + report.html + .analysis-profile.json)

No LLM call happens inside the pipeline. The report's Section VI embeds
anomalous event fragments for the consuming agent (which IS an LLM) to
read and analyze directly.
"""

from __future__ import annotations

import contextlib
import glob
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from observer.adapters.base import Adapter
from observer.adapters.claude import ClaudeAdapter
from observer.adapters.codex import CodexAdapter
from observer.aggregator import Report, aggregate
from observer.anomaly import Anomaly
from observer.anomaly import detect as detect_anomalies
from observer.episode import EpisodeSummary, segment_episodes
from observer.extractor import LabeledEvent
from observer.extractor import extract as extract_labels
from observer.federator import FederatedProject, federate
from observer.ir import IREvent
from observer.reporter import generate_html_report, generate_profile, generate_report

__all__ = ["DiscoveryResult", "OrchestrationResult", "Orchestrator", "discover_sessions"]

_DEFAULT_CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
_DEFAULT_CODEX_DIRS = [
    os.path.expanduser("~/.codex/sessions"),
    os.path.expanduser("~/.codex/archived_sessions"),
]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """What was found during session discovery, for diagnostics."""

    claude_paths: list[str]
    codex_paths: list[str]
    claude_dir_checked: str
    codex_dirs_checked: list[str]

    @property
    def total(self) -> int:
        return len(self.claude_paths) + len(self.codex_paths)

    @property
    def is_empty(self) -> bool:
        return self.total == 0


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """The complete output of a pipeline run."""

    report_md: str
    report_html: str
    profile: dict
    federated_projects: list[FederatedProject]
    anomalies: list[Anomaly]
    aggregator_report: Report
    episodes: list[EpisodeSummary]


class Orchestrator:
    """Run the full observer analysis pipeline.

    Args:
        source: Which agent sources to include ("claude", "codex", "all").
        output_dir: Where to write report.md, report.html, and .analysis-profile.json.
        claude_dir: Custom Claude projects directory (default ~/.claude/projects).
        codex_dirs: Custom Codex session directories.
    """

    def __init__(
        self,
        source: str = "all",
        output_dir: str | Path | None = None,
        claude_dir: str | None = None,
        codex_dirs: list[str] | None = None,
    ) -> None:
        self.source = source
        self.output_dir = Path(output_dir) if output_dir else None
        self.claude_dir = claude_dir or _DEFAULT_CLAUDE_DIR
        self.codex_dirs = codex_dirs or _DEFAULT_CODEX_DIRS
        self._discovery: DiscoveryResult | None = None

    @property
    def discovery(self) -> DiscoveryResult | None:
        """Session discovery diagnostics (available after run())."""
        return self._discovery

    def run(self) -> OrchestrationResult:
        from observer.diagnostic_engine import Diagnosis, DiagnosticEngine
        from observer.git_analyzer import analyze_git
        from observer.project_scanner import scan_project

        events = list(self._collect_events())
        projects = federate(events)
        episodes = [
            episode
            for project in projects
            for episode in segment_episodes(project.events)
        ]
        labeled_by_project: list[tuple[str, list[LabeledEvent]]] = [
            (p.project, extract_labels(p.events)) for p in projects
        ]
        agg_report = aggregate(labeled_by_project)
        anomalies = detect_anomalies(labeled_by_project)

        # 四诊: scan top project (most events) for 望 + 切.
        # Use the largest project as representative for the overview.
        top_project = max(projects, key=lambda p: len(p.events)) if projects else None
        proj_profile = None
        git_metrics = None

        if top_project and top_project.cwd:
            with contextlib.suppress(Exception):
                proj_profile = scan_project(top_project.cwd)
            with contextlib.suppress(Exception):
                git_metrics = analyze_git(
                    top_project.cwd, interaction_count=len(top_project.events)
                )

        # Run diagnostic engine once with representative project + git + global report.
        engine = DiagnosticEngine()
        diagnoses = engine.diagnose(proj_profile, git_metrics, agg_report, episodes)

        # De-duplicate by title (global rules may fire once; no per-project loop).
        seen_titles: set[str] = set()
        unique_diagnoses: list[Diagnosis] = []
        for d in diagnoses:
            if d.title not in seen_titles:
                seen_titles.add(d.title)
                unique_diagnoses.append(d)

        report_md = generate_report(
            agg_report, anomalies,
            diagnoses=unique_diagnoses or None,
            project=proj_profile,
            git=git_metrics,
        )
        profile = generate_profile(
            agg_report, anomalies,
            diagnoses=unique_diagnoses or None,
            episodes=episodes,
        )
        report_html = generate_html_report(profile)
        if self.output_dir:
            self._write_outputs(report_md, report_html, profile)
        return OrchestrationResult(
            report_md=report_md,
            report_html=report_html,
            profile=profile,
            federated_projects=projects,
            anomalies=anomalies,
            aggregator_report=agg_report,
            episodes=episodes,
        )

    def _collect_events(self) -> list[IREvent]:
        discovery = discover_sessions(
            source=self.source,
            claude_dir=self.claude_dir,
            codex_dirs=self.codex_dirs,
        )
        self._discovery = discovery

        if discovery.is_empty:
            self._print_empty_help(discovery)
            return []

        events: list[IREvent] = []
        for adapter, session_paths in self._select_adapters(discovery):
            for path in session_paths:
                events.extend(adapter.parse(path))
        return events

    def _select_adapters(
        self, discovery: DiscoveryResult
    ) -> list[tuple[Adapter, list[str]]]:
        result: list[tuple[Adapter, list[str]]] = []
        if self.source in ("claude", "all") and discovery.claude_paths:
            result.append((ClaudeAdapter(), discovery.claude_paths))
        if self.source in ("codex", "all") and discovery.codex_paths:
            result.append((CodexAdapter(), discovery.codex_paths))
        return result

    @staticmethod
    def _print_empty_help(d: DiscoveryResult) -> None:
        """Print a helpful message when no sessions are found."""
        print(
            "No session files found. VibeCoding Observer looked in:\n"
            f"  Claude: {d.claude_dir_checked}\n"
            f"  Codex:  {', '.join(d.codex_dirs_checked)}\n\n"
            "If your sessions are elsewhere, use --claude-dir / --codex-dir:\n"
            "  vibecoding-observer --claude-dir /path/to/claude/projects --output /tmp/report",
            file=sys.stderr,
        )

    def _write_outputs(
        self, report_md: str, report_html: str, profile: dict
    ) -> None:
        assert self.output_dir is not None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "report.md").write_text(report_md, encoding="utf-8")
        (self.output_dir / "report.html").write_text(report_html, encoding="utf-8")
        (self.output_dir / ".analysis-profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def discover_sessions(
    source: str = "all",
    claude_dir: str | None = None,
    codex_dirs: list[str] | None = None,
) -> DiscoveryResult:
    """Find session .jsonl files for given sources.

    Args:
        source: "claude", "codex", or "all".
        claude_dir: Override the default Claude projects directory.
        codex_dirs: Override the default Codex session directories.

    Returns:
        DiscoveryResult with found paths and directories checked (for diagnostics).
    """
    c_dir = claude_dir or _DEFAULT_CLAUDE_DIR
    c_dirs = codex_dirs or _DEFAULT_CODEX_DIRS

    claude_paths: list[str] = []
    codex_paths: list[str] = []

    if source in ("claude", "all") and os.path.isdir(c_dir):
        claude_paths.extend(glob.glob(os.path.join(c_dir, "*", "*.jsonl")))

    if source in ("codex", "all"):
        for d in c_dirs:
            if os.path.isdir(d):
                codex_paths.extend(
                    glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True)
                )

    return DiscoveryResult(
        claude_paths=sorted(claude_paths),
        codex_paths=sorted(codex_paths),
        claude_dir_checked=c_dir,
        codex_dirs_checked=c_dirs,
    )
