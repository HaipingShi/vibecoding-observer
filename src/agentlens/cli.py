"""Compatibility alias for :mod:`observer.cli`."""

import sys
from importlib import import_module

_module = import_module("observer.cli")
sys.modules[__name__] = _module
