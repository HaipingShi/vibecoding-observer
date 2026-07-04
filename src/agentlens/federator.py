"""Compatibility alias for :mod:`observer.federator`."""

import sys
from importlib import import_module

_module = import_module("observer.federator")
sys.modules[__name__] = _module
