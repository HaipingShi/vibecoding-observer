"""VibeCoding Observer canonical internal package.

The public distribution package is ``vibecoding-observer`` and the canonical
Python import package is ``observer``. It measures the divergence between LLM
default thinking paths and the engineering fast-lane, then distills
interaction patterns that activate engineering-grade decomposition.
"""

from observer.ir import IREvent, Role, SourceAgent, ToolCall

__version__ = "0.2.0"

__all__ = [
    "IREvent",
    "Role",
    "SourceAgent",
    "ToolCall",
    "__version__",
]
