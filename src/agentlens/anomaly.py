"""Compatibility alias for :mod:`observer.anomaly`."""

import sys
from importlib import import_module

_module = import_module("observer.anomaly")
sys.modules[__name__] = _module
