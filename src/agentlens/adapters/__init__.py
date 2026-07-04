"""Compatibility alias for :mod:`observer.adapters`."""

import sys
from importlib import import_module

_module = import_module("observer.adapters")
sys.modules[__name__] = _module
