"""Tests for raw-event to engineering-signal normalization."""

from __future__ import annotations

from observer.event_signals import (
    CODE_RAIL_PROFILE,
    GENERIC_PROFILE,
    detect_event_signals,
)
from observer.ir import IREvent, ToolCall


def _ev(
    *,
    text: str = "",
    role: str = "assistant",
    tool_calls: tuple[ToolCall, ...] = (),
) -> IREvent:
    return IREvent(
        ts="2026-07-09T00:00:00Z",
        source_agent="codex",
        cwd="/p/example",
        project="example",
        role=role,  # type: ignore[arg-type]
        text=text,
        tool_calls=tool_calls,
    )


def test_generic_profile_detects_patch_verify_and_git_persistence() -> None:
    patch = detect_event_signals(
        _ev(
            tool_calls=(
                ToolCall(
                    name="exec_command",
                    input={"cmd": "apply_patch <<'PATCH'\n*** Update File: app.py\nPATCH"},
                ),
            )
        ),
        profiles=(GENERIC_PROFILE,),
    )
    verify = detect_event_signals(
        _ev(tool_calls=(ToolCall(name="exec_command", input={"cmd": "uv run pytest"}),)),
        profiles=(GENERIC_PROFILE,),
    )
    commit = detect_event_signals(
        _ev(tool_calls=(ToolCall(name="exec_command", input={"cmd": "git add app.py && git commit -m fix"}),)),
        profiles=(GENERIC_PROFILE,),
    )

    assert patch.code_edit
    assert patch.implementation
    assert verify.verification
    assert not verify.implementation
    assert commit.persistence
    assert commit.closure


def test_design_doc_is_artifact_only_when_written_or_persisted() -> None:
    read_only = detect_event_signals(
        _ev(tool_calls=(ToolCall(name="exec_command", input={"cmd": "cat docs/DECISIONS.md"}),)),
        profiles=(GENERIC_PROFILE,),
    )
    written = detect_event_signals(
        _ev(
            tool_calls=(
                ToolCall(
                    name="exec_command",
                    input={"cmd": "python - <<'PY'\nfrom pathlib import Path\nPath('docs/DECISIONS.md').write_text('ADR')\nPY"},
                ),
            )
        ),
        profiles=(GENERIC_PROFILE,),
    )

    assert not read_only.design_artifact
    assert not read_only.implementation
    assert written.design_artifact
    assert written.implementation


def test_coderail_profile_adds_governance_dialect_without_core_special_case() -> None:
    event = _ev(
        tool_calls=(
            ToolCall(
                name="exec_command",
                input={"cmd": "python scripts/trace_event.py --task T-001 --kind verify"},
            ),
        )
    )

    generic = detect_event_signals(event, profiles=(GENERIC_PROFILE,))
    coderail = detect_event_signals(event, profiles=(GENERIC_PROFILE, CODE_RAIL_PROFILE))

    assert not generic.governance
    assert not generic.persistence
    assert coderail.governance
    assert coderail.persistence
    assert coderail.implementation
    assert "coderail" in coderail.matched_profiles


def test_coderail_profile_detects_explicit_closure_evidence() -> None:
    profiles = (GENERIC_PROFILE, CODE_RAIL_PROFILE)
    cases = [
        "Done Gate: passed",
        "python scripts/trace_event.py --task T-001 --kind verify",
        "task T-001 marked done in docs/TASKS.md",
        "git commit -m 'Close T-001'",
    ]

    for text in cases:
        signals = detect_event_signals(
            _ev(tool_calls=(ToolCall(name="exec_command", input={"cmd": text}),)),
            profiles=profiles,
        )
        assert signals.closure, text
