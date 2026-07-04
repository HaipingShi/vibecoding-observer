"""CLI entry point for VibeCoding Observer.

Usage:
    vibecoding-observer [--source claude|codex|all] [--output DIR]
                         [--claude-dir PATH] [--codex-dir PATH] [--version]

Fully local. The report embeds anomalous event fragments for the consuming
agent (which IS an LLM) to read and analyze directly.
"""

from __future__ import annotations

import argparse
import sys

from observer import __version__
from observer.orchestrator import Orchestrator

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibecoding-observer",
        description=(
            "Analyze vibe-coding and AI coding agent collaboration history — "
            "measure the divergence between LLM default thinking "
            "and the engineering fast-lane.\n\n"
            "Examples:\n"
            "  vibecoding-observer --source all --output /tmp/report\n"
            "  vibecoding-observer --source claude --output ./my-analysis\n"
            "  vibecoding-observer --claude-dir /custom/path --codex-dir /custom/path\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["claude", "codex", "all"],
        default="all",
        help="Which agent sources to include (default: all).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output directory for report.md, report.html, and .analysis-profile.json.",
    )
    parser.add_argument(
        "--claude-dir",
        type=str,
        default=None,
        help="Custom Claude projects directory (default: ~/.claude/projects).",
    )
    parser.add_argument(
        "--codex-dir",
        type=str,
        action="append",
        default=None,
        help="Custom Codex sessions directory (can repeat; default: ~/.codex/sessions).",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"vibecoding-observer {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    orchestrator = Orchestrator(
        source=args.source,
        output_dir=args.output,
        claude_dir=args.claude_dir,
        codex_dirs=args.codex_dir,
    )

    try:
        result = orchestrator.run()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(
        f"Analyzed {result.aggregator_report.total_projects} project(s), "
        f"{result.aggregator_report.total_events} events."
    )
    print(f"Found {len(result.anomalies)} anomaly slices with event context.")
    if args.output:
        print(f"Report written to {args.output}/report.md")
        print(f"HTML report written to {args.output}/report.html")
        print(f"Profile written to {args.output}/.analysis-profile.json")
    else:
        print("\n--- Report ---\n")
        print(result.report_md)

    return 0
