"""Compatibility alias for :mod:`observer.diagnostic_engine`."""

import sys
from importlib import import_module

_module = import_module("observer.diagnostic_engine")
sys.modules[__name__] = _module
