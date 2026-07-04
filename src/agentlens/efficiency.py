"""Compatibility alias for :mod:`observer.efficiency`."""

import sys
from importlib import import_module

_module = import_module("observer.efficiency")
sys.modules[__name__] = _module
