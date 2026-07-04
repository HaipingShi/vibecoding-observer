"""Compatibility alias for :mod:`observer.adapters.base`."""

import sys
from importlib import import_module

_module = import_module("observer.adapters.base")
sys.modules[__name__] = _module
