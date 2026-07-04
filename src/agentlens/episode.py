"""Compatibility alias for :mod:`observer.episode`."""

import sys
from importlib import import_module

_module = import_module("observer.episode")
sys.modules[__name__] = _module
