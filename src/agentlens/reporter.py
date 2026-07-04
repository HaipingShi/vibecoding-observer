"""Compatibility alias for :mod:`observer.reporter`."""

import sys
from importlib import import_module

_module = import_module("observer.reporter")
sys.modules[__name__] = _module
