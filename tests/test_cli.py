"""Tests for the Orchestrator and CLI.

Validates the pipeline wires correctly end-to-end and the CLI accepts
expected arguments. Fully local, no LLM/network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observer.cli import _resolve_project_path, build_parser
from observer.cli import main as cli_main
from observer.ir import IREvent, ToolCall
from observer.orchestrator import DiscoveryResult, Orchestrator, discover_sessions


class TestOrchestrator:
    def test_run_with_no_sessions(self) -> None:
        orch = Orchestrator(source="claude")
        orch._collect_events = lambda: []  # type: ignore[method-assign]
        result = orch.run()
        assert result.aggregator_report.total_events == 0

    def test_run_writes_outputs(self, tmp_path: Path) -> None:
        orch = Orchestrator(source="claude", output_dir=tmp_path)
        orch._collect_events = lambda: []  # type: ignore[method-assign]
        orch.run()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "report.html").exists()
        assert (tmp_path / ".analysis-profile.json").exists()
        html = (tmp_path / "report.html").read_text()
        assert "VibeCoding Observer 可视化诊断报告" in html
        assert ".analysis-profile.json" in html
        assert "consulting_routes" in html
        profile = json.loads((tmp_path / ".analysis-profile.json").read_text())
        assert profile["version"] == "0.1.0"

    def test_report_md_has_sections(self) -> None:
        orch = Orchestrator(source="claude")
        orch._collect_events = lambda: []  # type: ignore[method-assign]
        result = orch.run()
        assert "## 一、全景" in result.report_md
        assert "## 六、异常点详解" in result.report_md

    def test_run_profile_includes_episodes(self) -> None:
        orch = Orchestrator(source="claude")
        orch._collect_events = lambda: [  # type: ignore[method-assign]
            IREvent(
                ts="2026-06-28T13:00:00Z",
                source_agent="claude",
                cwd="/p/example",
                project="example",
                role="user",
                text="请实现导出功能，必须有 pytest",
            ),
            IREvent(
                ts="2026-06-28T13:01:00Z",
                source_agent="claude",
                cwd="/p/example",
                project="example",
                role="assistant",
                tool_calls=(ToolCall(name="Edit", input={"file_path": "x.py"}),),
            ),
        ]
        result = orch.run()
        assert result.episodes
        assert result.profile["episode_summary"]["total"] == 1
        assert result.profile["episode_summary"]["goal_quality_counts"] == {"task_like": 1}
        assert result.profile["episode_summary"]["goal_extraction_counts"] == {"raw_goal": 1}
        assert result.profile["episode_summary"]["diagnostic_signal_counts"] == {
            "implementation_without_verification": 1,
        }
        assert result.profile["episodes"][0]["goal"] == "请实现导出功能，必须有 pytest"
        assert result.profile["episodes"][0]["goal_quality"] == "task_like"
        assert result.profile["episodes"][0]["normalized_goal"] == "请实现导出功能，必须有 pytest"
        assert result.profile["episodes"][0]["goal_extraction_method"] == "raw_goal"
        assert result.profile["episodes"][0]["diagnostic_signals"] == [
            "implementation_without_verification"
        ]
        assert any(
            route["title"] == "补齐验证和交付闭环"
            for route in result.profile["consulting_routes"]
        )
        assert "工程闭环漏斗" in result.report_html
        assert "补齐验证和交付闭环" in result.report_html

    def test_run_report_includes_episode_diagnoses(self) -> None:
        events: list[IREvent] = []
        for idx in range(20):
            events.append(
                IREvent(
                    ts=f"2026-06-28T13:{idx:02d}:00Z",
                    source_agent="claude",
                    cwd="/p/example",
                    project="example",
                    role="user",
                    text=f"请分析 API contract 漂移风险 {idx}",
                )
            )
            events.extend(
                IREvent(
                    ts=f"2026-06-28T13:{idx:02d}:01Z",
                    source_agent="claude",
                    cwd="/p/example",
                    project="example",
                    role="assistant",
                    text="继续分析",
                )
                for _ in range(50)
            )
        orch = Orchestrator(source="claude")
        orch._collect_events = lambda: events  # type: ignore[method-assign]

        result = orch.run()

        assert "顶层目标存在但工程闭环缺失" in result.report_md
        assert any(
            d["title"] == "顶层目标存在但工程闭环缺失"
            for d in result.profile["diagnoses"]
        )

    def test_custom_claude_dir(self, tmp_path: Path) -> None:
        """Custom claude_dir is respected when discovering."""
        orch = Orchestrator(source="claude", claude_dir=str(tmp_path))
        # tmp_path has no .jsonl → empty discovery
        events = orch._collect_events()
        assert events == []
        assert orch.discovery is not None
        assert orch.discovery.claude_dir_checked == str(tmp_path)

    def test_project_path_filters_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Project scope keeps only events whose cwd is inside that project."""
        project = tmp_path / "target"
        other = tmp_path / "other"
        project.mkdir()
        other.mkdir()
        events = [
            IREvent(
                ts="2026-06-28T13:00:00Z",
                source_agent="codex",
                cwd=str(project),
                project="target",
                role="user",
                text="target root",
            ),
            IREvent(
                ts="2026-06-28T13:01:00Z",
                source_agent="codex",
                cwd=str(project / "subdir"),
                project="target",
                role="assistant",
                text="target child",
            ),
            IREvent(
                ts="2026-06-28T13:02:00Z",
                source_agent="codex",
                cwd=str(other),
                project="other",
                role="user",
                text="other project",
            ),
        ]

        class FakeAdapter:
            def parse(self, path: str) -> list[IREvent]:
                assert path == "fake.jsonl"
                return events

        monkeypatch.setattr(
            "observer.orchestrator.discover_sessions",
            lambda **_kw: DiscoveryResult(
                claude_paths=[],
                codex_paths=["fake.jsonl"],
                claude_dir_checked="",
                codex_dirs_checked=[],
            ),
        )
        orch = Orchestrator(source="codex", project_path=project)
        orch._select_adapters = lambda _d: [(FakeAdapter(), ["fake.jsonl"])]  # type: ignore[method-assign]

        collected = orch._collect_events()

        assert [ev.text for ev in collected] == ["target root", "target child"]


class TestDiscoverSessions:
    def test_claude_returns_list(self) -> None:
        result = discover_sessions("claude")
        assert isinstance(result.claude_paths, list)
        assert all(p.endswith(".jsonl") for p in result.claude_paths)

    def test_all_returns_both(self) -> None:
        result = discover_sessions("all")
        assert isinstance(result.claude_paths, list)
        assert isinstance(result.codex_paths, list)

    def test_unknown_source_empty(self) -> None:
        result = discover_sessions("nonexistent")
        assert result.is_empty

    def test_custom_dir_override(self, tmp_path: Path) -> None:
        result = discover_sessions("claude", claude_dir=str(tmp_path))
        assert result.claude_dir_checked == str(tmp_path)
        assert result.claude_paths == []


class TestCLI:
    def test_parser_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.source == "all"
        assert args.output is None
        assert args.claude_dir is None
        assert args.codex_dir is None
        assert args.project is None
        assert args.current_project is False
        assert args.all_history is False

    def test_parser_source_choice(self) -> None:
        args = build_parser().parse_args(["--source", "codex"])
        assert args.source == "codex"

    def test_parser_output(self) -> None:
        args = build_parser().parse_args(["--output", "/tmp/r"])
        assert args.output == "/tmp/r"

    def test_parser_claude_dir(self) -> None:
        args = build_parser().parse_args(["--claude-dir", "/custom/claude"])
        assert args.claude_dir == "/custom/claude"

    def test_parser_codex_dir(self) -> None:
        args = build_parser().parse_args(["--codex-dir", "/custom/codex"])
        assert args.codex_dir == ["/custom/codex"]

    def test_parser_project_scope(self) -> None:
        args = build_parser().parse_args(["--project", "/tmp/project"])
        assert args.project == "/tmp/project"

    def test_parser_current_project_scope(self) -> None:
        args = build_parser().parse_args(["--current-project"])
        assert args.current_project is True

    def test_parser_all_history_scope(self) -> None:
        args = build_parser().parse_args(["--all-history"])
        assert args.all_history is True

    def test_parser_scope_options_are_exclusive(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--current-project", "--all-history"])

    def test_parser_invalid_source(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--source", "invalid"])

    def test_noninteractive_default_is_current_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        args = build_parser().parse_args([])

        assert _resolve_project_path(args) == tmp_path.resolve()

    def test_all_history_resolves_to_no_project_filter(self) -> None:
        args = build_parser().parse_args(["--all-history"])
        assert _resolve_project_path(args) is None

    def test_interactive_prompt_can_choose_all_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "3")
        args = build_parser().parse_args([])

        assert _resolve_project_path(args) is None

    def test_cli_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "observer.orchestrator.discover_sessions",
            lambda *a, **kw: type("R", (), {
                "claude_paths": [], "codex_paths": [],
                "claude_dir_checked": "", "codex_dirs_checked": [],
                "total": 0, "is_empty": True,
            })(),
        )
        code = cli_main(["--source", "claude", "--output", str(tmp_path)])
        assert code == 0
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "report.html").exists()

    def test_cli_prints_report(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "observer.orchestrator.discover_sessions",
            lambda *a, **kw: type("R", (), {
                "claude_paths": [], "codex_paths": [],
                "claude_dir_checked": "", "codex_dirs_checked": [],
                "total": 0, "is_empty": True,
            })(),
        )
        code = cli_main(["--source", "claude"])
        assert code == 0
        assert "## 一、全景" in capsys.readouterr().out
