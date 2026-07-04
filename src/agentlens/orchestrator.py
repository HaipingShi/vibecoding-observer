"""Compatibility alias for :mod:`observer.orchestrator`."""

import sys
from importlib import import_module

_module = import_module("observer.orchestrator")
sys.modules[__name__] = _module
