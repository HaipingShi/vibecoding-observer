"""Scan-scope tests using real Claude/Codex JSONL shapes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observer.ir import IREvent
from observer.orchestrator import DiscoveryResult, Orchestrator


def test_project_scope_filters_real_agent_fixtures(
    fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _collect_events(
        monkeypatch,
        claude_paths=[fixtures_dir / "claude_scope_edges.jsonl"],
        codex_paths=[fixtures_dir / "codex_scope_edges.jsonl"],
        project_path=Path("/tmp/vibecoding-observer-scope/target"),
    )

    assert [event.text for event in events] == [
        "claude target root",
        "claude target child",
        "codex target root",
        "codex target child",
    ]
    assert not any("missing cwd" in event.text for event in events)
    assert not any("other project" in event.text for event in events)


def test_project_scope_resolves_symlinked_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    child = target / "child"
    child.mkdir(parents=True)
    link = tmp_path / "linked-target"
    link.symlink_to(target, target_is_directory=True)

    claude_path = tmp_path / "claude_symlink.jsonl"
    codex_path = tmp_path / "codex_symlink.jsonl"
    symlink_child = link / "child"
    _write_jsonl(
        claude_path,
        [
            {
                "type": "user",
                "cwd": str(symlink_child),
                "timestamp": "2026-07-04T10:02:00Z",
                "uuid": "u-symlink",
                "parentUuid": None,
                "message": {
                    "role": "user",
                    "content": "claude symlink child",
                },
            },
        ],
    )
    _write_jsonl(
        codex_path,
        [
            {
                "timestamp": "2026-07-04T10:03:00Z",
                "type": "session_meta",
                "payload": {"id": "s-symlink", "cwd": str(symlink_child)},
            },
            {
                "timestamp": "2026-07-04T10:03:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "codex symlink child",
                        }
                    ],
                },
            },
        ],
    )

    events = _collect_events(
        monkeypatch,
        claude_paths=[claude_path],
        codex_paths=[codex_path],
        project_path=target,
    )

    assert [event.text for event in events] == [
        "claude symlink child",
        "codex symlink child",
    ]
    assert {event.cwd for event in events} == {str(symlink_child)}


def _collect_events(
    monkeypatch: pytest.MonkeyPatch,
    *,
    claude_paths: list[Path],
    codex_paths: list[Path],
    project_path: Path,
) -> list[IREvent]:
    monkeypatch.setattr(
        "observer.orchestrator.discover_sessions",
        lambda **_kw: DiscoveryResult(
            claude_paths=[str(path) for path in claude_paths],
            codex_paths=[str(path) for path in codex_paths],
            claude_dir_checked="",
            codex_dirs_checked=[],
        ),
    )
    return Orchestrator(source="all", project_path=project_path)._collect_events()


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
