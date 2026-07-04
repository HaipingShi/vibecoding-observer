"""Compatibility alias for :mod:`observer`.

Prefer importing ``observer`` in new code. ``agentlens`` remains available
for existing users during the package migration.
"""

from observer import IREvent, Role, SourceAgent, ToolCall, __version__

__all__ = [
    "IREvent",
    "Role",
    "SourceAgent",
    "ToolCall",
    "__version__",
]
