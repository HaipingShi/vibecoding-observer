"""Compatibility alias for :mod:`observer.git_analyzer`."""

import sys
from importlib import import_module

_module = import_module("observer.git_analyzer")
sys.modules[__name__] = _module
