"""Tests for project-local signal profile configuration."""

from __future__ import annotations

from pathlib import Path

from observer.episode import segment_episodes
from observer.event_signals import detect_event_signals
from observer.ir import IREvent, ToolCall
from observer.signal_config import load_signal_config

FIXTURES = Path(__file__).parent / "fixtures"


def _ev(cmd: str) -> IREvent:
    return IREvent(
        ts="2026-07-09T00:00:00Z",
        source_agent="codex",
        cwd="/p/example",
        project="example",
        role="assistant",
        tool_calls=(ToolCall(name="exec_command", input={"cmd": cmd}),),
    )


def test_observer_yaml_fixture_adds_non_coderail_custom_closure_dialect(
    tmp_path: Path,
) -> None:
    fixture = FIXTURES / "observer_custom_closure.yaml"
    (tmp_path / "observer.yaml").write_text(fixture.read_text(), encoding="utf-8")

    config = load_signal_config(tmp_path)

    assert config.source_path == str(tmp_path / "observer.yaml")
    assert "project_config" in config.profile_names
    assert "coderail" not in config.profile_names
    assert config.confidence_hint == "high"
    assert detect_event_signals(
        _ev(
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "Path('planning/accepted-design.md').write_text('x')\n"
            "PY"
        ),
        profiles=config.profiles,
    ).design_artifact
    assert detect_event_signals(
        _ev("make evidence-check"),
        profiles=config.profiles,
    ).verification
    assert detect_event_signals(_ev("RFC accepted"), profiles=config.profiles).closure
    assert detect_event_signals(_ev("changelog updated"), profiles=config.profiles).persistence


def test_observer_yaml_fixture_closes_design_episode_without_coderail(
    tmp_path: Path,
) -> None:
    fixture = FIXTURES / "observer_custom_closure.yaml"
    (tmp_path / "observer.yaml").write_text(fixture.read_text(), encoding="utf-8")
    config = load_signal_config(tmp_path)

    episodes = segment_episodes(
        [
            IREvent(
                ts="2026-07-09T00:00:00Z",
                source_agent="codex",
                cwd=str(tmp_path),
                project="custom",
                role="user",
                text="请完成研究设计 RFC，并按团队规范关闭",
            ),
            _ev(
                "python - <<'PY'\n"
                "from pathlib import Path\n"
                "Path('planning/accepted-design.md').write_text('RFC-7')\n"
                "PY"
            ),
            _ev("make evidence-check"),
            _ev("RFC accepted"),
        ],
        profiles=config.profiles,
    )

    assert episodes[0].loop_quality == "design_closed"


def test_observer_yaml_ignore_patterns_do_not_count_generated_artifacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "observer.yaml").write_text(
        """
observer:
  generated_ignore:
    - data/evaluation/**
""",
        encoding="utf-8",
    )

    config = load_signal_config(tmp_path)
    signals = detect_event_signals(
        _ev("apply_patch <<'PATCH'\n*** Update File: data/evaluation/run.json\nPATCH"),
        profiles=config.profiles,
    )

    assert not signals.code_edit
    assert not signals.implementation


def test_coderail_profile_can_be_declared_or_auto_detected(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "done_gate.py").write_text("# gate", encoding="utf-8")

    auto = load_signal_config(tmp_path)
    assert "coderail" in auto.profile_names
    assert auto.auto_detected_profiles == ("coderail",)
    assert auto.confidence_hint == "medium"

    explicit_root = tmp_path / "explicit"
    explicit_root.mkdir()
    (explicit_root / "observer.yaml").write_text(
        "observer:\n  governance_profile: coderail\n",
        encoding="utf-8",
    )
    explicit = load_signal_config(explicit_root)
    assert "coderail" in explicit.profile_names
    assert explicit.auto_detected_profiles == ()
