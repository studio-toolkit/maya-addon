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


@contextmanager
def undo_disabled():
    maya_cmds = cmds()
    previous_state = True
    try:
        previous_state = bool(maya_cmds.undoInfo(query=True, state=True))
    except Exception:
        previous_state = True

    if previous_state:
        maya_cmds.undoInfo(stateWithoutFlush=False)
    try:
        yield
    finally:
        if previous_state:
            maya_cmds.undoInfo(stateWithoutFlush=True)
