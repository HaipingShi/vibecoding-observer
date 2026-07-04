"""Compatibility alias for :mod:`observer.checklist`."""

import sys
from importlib import import_module

_module = import_module("observer.checklist")
sys.modules[__name__] = _module
