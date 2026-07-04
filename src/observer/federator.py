"""Federator — fuse multi-source IREvents into project-level timelines.

The same project is often touched by several agents (Claude AND Codex); each
agent's sessions are a fragment of the real interaction line. The Federator
merges them into a single chronological sequence per project so downstream
analysis sees the *complete* collaboration, not a truncated slice.

Cross-agent handoff detection:
    A handoff is a strong degradation signal — the user switched agents,
    usually because the previous one stalled or went the wrong direction.
    We mark an event as a handoff when, within the same project, the
    ``source_agent`` changes relative to the previous event AND the time
    gap is within ``handoff_max_gap_seconds``. The marked event is the
    *first* event of the new agent's run (i.e. the resumption point),
    which is where the context-rebuild cost lands.

Output:
    A mapping ``project -> list[IREvent]``, each list sorted by ``ts``
    ascending. Events are immutable copies; handoff flags are applied via
    ``IREvent.with_handoff()`` so the originals are never mutated.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from observer.ir import IREvent

__all__ = ["FederatedProject", "Federator", "federate"]

# Default: if the user resumes in a *different* agent within 4 hours of the
# last event in the same project, treat it as a handoff. Beyond 4h it's more
# likely a fresh session than a switch. Tunable.
_DEFAULT_HANDOFF_GAP_SECONDS = 4 * 60 * 60


class FederatedProject:
    """A single project's fused, time-ordered interaction line."""

    __slots__ = ("cwd", "events", "project")

    def __init__(self, project: str, cwd: str, events: list[IREvent]) -> None:
        self.project = project
        self.cwd = cwd
        self.events = events

    def __repr__(self) -> str:
        return (
            f"FederatedProject(project={self.project!r}, "
            f"cwd={self.cwd!r}, events={len(self.events)})"
        )

    @property
    def handoff_count(self) -> int:
        return sum(1 for ev in self.events if ev.is_handoff)


class Federator:
    """Fuse multi-source IREvents into per-project timelines.

    Args:
        handoff_max_gap_seconds: Max seconds between the last event of one
            agent and the first event of another in the same project for
            the switch to count as a handoff.
    """

    def __init__(
        self, handoff_max_gap_seconds: int = _DEFAULT_HANDOFF_GAP_SECONDS
    ) -> None:
        self.handoff_max_gap_seconds = handoff_max_gap_seconds

    def federate(self, events: Iterable[IREvent]) -> list[FederatedProject]:
        """Fuse events into project timelines, marking cross-agent handoffs.

        Args:
            events: Any iterable of IREvents (from one or many adapters).

        Returns:
            List of FederatedProject, one per distinct project, sorted by
            project name. Each project's events are sorted by ts ascending
            with handoff flags applied.
        """
        # Group by project.
        by_project: dict[str, list[IREvent]] = {}
        for ev in events:
            by_project.setdefault(ev.project, []).append(ev)

        projects: list[FederatedProject] = []
        for project in sorted(by_project):
            evs = self._sort_and_mark(by_project[project])
            cwd = evs[0].cwd if evs else ""
            projects.append(FederatedProject(project=project, cwd=cwd, events=evs))
        return projects

    def _sort_and_mark(self, events: list[IREvent]) -> list[IREvent]:
        """Sort by timestamp and apply cross-agent handoff flags."""
        # Stable sort by parsed timestamp. Unparseable timestamps (None) sort
        # last while preserving their relative order — use a tuple key so
        # None never compares against datetime directly.
        ordered = sorted(events, key=_sort_key)

        result: list[IREvent] = []
        prev_agent: str | None = None
        prev_ts: datetime | None = None

        for ev in ordered:
            ev_ts = _parse_ts(ev.ts)
            is_handoff = False
            if (
                prev_agent is not None
                and prev_ts is not None
                and ev.source_agent != prev_agent
                and ev_ts is not None
            ):
                gap = (ev_ts - prev_ts).total_seconds()
                if 0 <= gap <= self.handoff_max_gap_seconds:
                    is_handoff = True

            result.append(ev.with_handoff(is_handoff))
            # Track the most recent event to compare against the next.
            prev_agent = ev.source_agent
            if ev_ts is not None:
                prev_ts = ev_ts

        return result


def federate(
    events: Iterable[IREvent],
    handoff_max_gap_seconds: int = _DEFAULT_HANDOFF_GAP_SECONDS,
) -> list[FederatedProject]:
    """Convenience function: one-shot federate without instantiating."""
    return Federator(handoff_max_gap_seconds=handoff_max_gap_seconds).federate(events)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _parse_ts(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime.

    Returns None if parsing fails; callers treat None as "unorderable"
    (Python's sort is stable, so unparseable timestamps keep their place).
    """
    # Normalize trailing Z to +00:00 for fromisoformat.
    cleaned = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _sort_key(ev: IREvent) -> tuple[int, datetime]:
    """Sort key that pushes unparseable timestamps to the end.

    Returns ``(1, epoch_min)`` for None so it always sorts after any real
    datetime (which returns ``(0, dt)``). This avoids comparing None against
    datetime, which raises TypeError.
    """
    dt = _parse_ts(ev.ts)
    if dt is None:
        # Minimal sentinel datetime — sorts after all real ones via index 1.
        return (1, datetime.min.replace(tzinfo=UTC))
    return (0, dt)
