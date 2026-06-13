"""Operator base helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.maya_api import cmds
from ..core.undo import undo_chunk, undo_disabled


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    tooltip: str
    callback: Callable
    icon: str | None = None

    def run(self, *args, **kwargs):
        with undo_chunk(self.label):
            result = self.callback(*args, **kwargs)
        if result is not False:
            try:
                with undo_disabled():
                    cmds().inViewMessage(amg="Mio3 UV: {}".format(self.label), pos="midCenter", fade=True)
            except Exception:
                pass
        return result


def warn(message: str) -> None:
    try:
        cmds().warning("Mio3 UV: {}".format(message))
    except MayaUnavailable:
        print("Mio3 UV: {}".format(message))
