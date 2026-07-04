"""Compatibility alias for :mod:`observer.adapters.codex`."""

import sys
from importlib import import_module

_module = import_module("observer.adapters.codex")
sys.modules[__name__] = _module
