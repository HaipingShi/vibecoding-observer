"""Adapter base — the contract every data-source adapter implements.

An adapter's sole job: convert one agent's raw jsonl into a stream of
``IREvent`` objects. Nothing downstream should ever know which agent a
record came from beyond the ``source_agent`` field on the IR itself.

Streaming contract (``Iterator``, not ``list``):
    Codex session files can reach 187 MB. Adapters MUST yield events lazily,
    reading the jsonl line-by-line, never loading the whole file into memory.
    This keeps local diagnostics usable on large session histories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from observer.ir import IREvent

__all__ = ["Adapter"]


class Adapter(ABC):
    """Abstract base for a data-source adapter.

    Subclasses implement :meth:`parse`, transforming a ``.jsonl`` file into
    a lazy iterator of :class:`~observer.ir.IREvent`.
    """

    @property
    @abstractmethod
    def source_agent(self) -> str:
        """The ``source_agent`` value stamped on every emitted IREvent."""

    @abstractmethod
    def parse(self, jsonl_path: str | Path) -> Iterator[IREvent]:
        """Yield IREvents from a session jsonl file, lazily.

        Args:
            jsonl_path: Path to a single ``.jsonl`` session file.

        Yields:
            IREvent objects in chronological order.
        """
        raise NotImplementedError

    def parse_many(self, jsonl_paths: list[str | Path]) -> Iterator[IREvent]:
        """Convenience: chain multiple session files into one stream.

        Order is preserved across files as given. The Federator is
        responsible for true time-axis reordering; adapters just emit.
        """
        for path in jsonl_paths:
            yield from self.parse(path)
