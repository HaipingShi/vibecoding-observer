"""Compatibility alias for :mod:`observer.adapters.claude`."""

import sys
from importlib import import_module

_module = import_module("observer.adapters.claude")
sys.modules[__name__] = _module
