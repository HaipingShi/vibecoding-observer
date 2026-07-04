"""Compatibility alias for :mod:`observer.extractor`."""

import sys
from importlib import import_module

_module = import_module("observer.extractor")
sys.modules[__name__] = _module
