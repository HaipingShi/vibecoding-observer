"""Compatibility alias for :mod:`observer.project_scanner`."""

import sys
from importlib import import_module

_module = import_module("observer.project_scanner")
sys.modules[__name__] = _module
