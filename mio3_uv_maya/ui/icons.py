"""Icon lookup for the Maya UI."""

from __future__ import annotations

import os


def icon_path(name: str | None) -> str:
    if not name:
        return ""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "icons"))
    path = os.path.join(root, "{}.png".format(name))
    return path if os.path.exists(path) else ""

