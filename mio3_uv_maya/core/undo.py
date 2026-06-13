"""Undo helpers."""

from __future__ import annotations

from contextlib import contextmanager

from .maya_api import cmds


@contextmanager
def undo_chunk(label: str = "Mio3 UV"):
    maya_cmds = cmds()
    maya_cmds.undoInfo(openChunk=True, chunkName=label)
    try:
        yield
    finally:
        maya_cmds.undoInfo(closeChunk=True)

