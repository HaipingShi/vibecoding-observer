"""Compatibility alias for :mod:`observer.aggregator`."""

import sys
from importlib import import_module

_module = import_module("observer.aggregator")
sys.modules[__name__] = _module
