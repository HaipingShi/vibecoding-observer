"""Compatibility alias for :mod:`observer.message_classifier`."""

import sys
from importlib import import_module

_module = import_module("observer.message_classifier")
sys.modules[__name__] = _module
