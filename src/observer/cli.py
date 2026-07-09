"""CLI entry point for VibeCoding Observer.

Usage:
    vibecoding-observer [--source claude|codex|all] [--output DIR]
                         [--project PATH | --current-project | --all-history]
                         [--claude-dir PATH] [--codex-dir PATH]
                         [--export-share-card | --share-card-svg [PATH]]
                         [--report-language auto|zh|en]
                         [--version]

Fully local. The report embeds anomalous event fragments for the consuming
agent (which IS an LLM) to read and analyze directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
            "  vibecoding-observer --current-project --source all --output /tmp/report\n"
            "  vibecoding-observer --project /path/to/project --source claude --output ./my-analysis\n"
            "  vibecoding-observer --all-history --source all --output /tmp/all-history\n"
            "  vibecoding-observer --claude-dir /custom/path --codex-dir /custom/path\n"
            "  vibecoding-observer --current-project --output ./my-report --export-share-card\n"
            "  vibecoding-observer --current-project --share-card-svg ./share-card.svg\n"
            "  vibecoding-observer --current-project --report-language zh\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--project",
        type=str,
        default=None,
        help=(
            "Analyze only sessions whose cwd is this project path or a child "
            "directory."
        ),
    )
    scope.add_argument(
        "--current-project",
        action="store_true",
        help="Analyze only sessions for the current project directory.",
    )
    scope.add_argument(
        "--all-history",
        action="store_true",
        help="Analyze all discovered Claude/Codex session history.",
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
    share = parser.add_mutually_exclusive_group()
    share.add_argument(
        "--export-share-card",
        action="store_true",
        help=(
            "Write a standalone share-card SVG next to the report outputs "
            "(default path: OUTPUT/share-card.svg, or ./share-card.svg without --output)."
        ),
    )
    share.add_argument(
        "--share-card-svg",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help=(
            "Write a standalone share-card SVG. Optionally pass PATH; without "
            "PATH it uses OUTPUT/share-card.svg, or ./share-card.svg without --output."
        ),
    )
    parser.add_argument(
        "--report-language",
        choices=["auto", "zh", "en"],
        default="auto",
        help=(
            "Language for the user-facing report delivery layer "
            "(default: auto-detect from local session text)."
        ),
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
    project_path = _resolve_project_path(args)
    share_card_svg_path = _resolve_share_card_svg_path(args)
    if project_path is None:
        print("Scan scope: all AI coding history on this machine", file=sys.stderr)
    else:
        print(f"Scan scope: project {project_path}", file=sys.stderr)

    orchestrator = Orchestrator(
        source=args.source,
        output_dir=args.output,
        claude_dir=args.claude_dir,
        codex_dirs=args.codex_dir,
        project_path=project_path,
        share_card_svg_path=share_card_svg_path,
        report_language=args.report_language,
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
        if result.share_card_svg_path:
            print(f"Share card SVG written to {result.share_card_svg_path}")
    else:
        print("\n--- Report ---\n")
        print(result.report_md)
        if result.share_card_svg_path:
            print(f"Share card SVG written to {result.share_card_svg_path}")

    return 0


def _resolve_project_path(args: argparse.Namespace) -> Path | None:
    """Resolve CLI scan scope into an optional project path filter."""
    if args.all_history:
        return None
    if args.project:
        return Path(args.project).expanduser().resolve()
    if args.current_project:
        return _current_project_root()
    if sys.stdin.isatty() and sys.stdout.isatty():
        return _prompt_scan_scope()
    return _current_project_root()


def _current_project_root() -> Path:
    """Prefer the enclosing git root; fall back to cwd."""
    path = Path.cwd().resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return path


def _prompt_scan_scope() -> Path | None:
    current = _current_project_root()
    print(
        "\nChoose VibeCoding Observer scan scope:\n"
        f"  1. Current project only: {current}\n"
        "  2. Specific project path\n"
        "  3. All AI coding history on this machine\n"
        "Default: 1\n",
        file=sys.stderr,
    )
    choice = input("Scan scope [1/2/3]: ").strip()
    if choice == "3":
        return None
    if choice == "2":
        project = input("Project path: ").strip()
        if project:
            return Path(project).expanduser().resolve()
    return current


def _resolve_share_card_svg_path(args: argparse.Namespace) -> Path | None:
    """Resolve share-card export flags into a concrete output path."""
    if not args.export_share_card and args.share_card_svg is None:
        return None
    if args.share_card_svg:
        return Path(args.share_card_svg).expanduser()
    if args.output:
        return Path(args.output).expanduser() / "share-card.svg"
    return Path("share-card.svg")
