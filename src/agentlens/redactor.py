"""Compatibility alias for :mod:`observer.redactor`."""

import sys
from importlib import import_module

_module = import_module("observer.redactor")
sys.modules[__name__] = _module
