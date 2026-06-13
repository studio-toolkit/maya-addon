"""Development reload helpers."""

from __future__ import annotations

import importlib
import sys


def reload_mio3_uv_maya():
    prefix = "mio3_uv_maya"
    modules = [name for name in sys.modules if name == prefix or name.startswith(prefix + ".")]
    for name in sorted(modules, key=len, reverse=True):
        importlib.reload(sys.modules[name])
    return True

