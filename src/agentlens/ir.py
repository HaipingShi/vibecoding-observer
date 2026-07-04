"""Compatibility alias for :mod:`observer.ir`."""

import sys
from importlib import import_module

_module = import_module("observer.ir")
sys.modules[__name__] = _module
