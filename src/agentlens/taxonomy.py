"""Compatibility alias for :mod:`observer.taxonomy`."""

import sys
from importlib import import_module

_module = import_module("observer.taxonomy")
sys.modules[__name__] = _module
