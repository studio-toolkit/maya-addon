"""Lazy Maya imports.

Importing Maya modules outside Maya raises ImportError. Keep all access behind
helpers so pure Python modules and syntax checks remain usable in the repo.
"""


class MayaUnavailable(RuntimeError):
    """Raised when a Maya-only operation is called outside Maya."""


def cmds():
    try:
        import maya.cmds as maya_cmds
    except Exception as exc:  # pragma: no cover - only hit outside Maya
        raise MayaUnavailable("maya.cmds is only available inside Maya") from exc
    return maya_cmds


def om2():
    try:
        from maya.api import OpenMaya as open_maya
    except Exception as exc:  # pragma: no cover - only hit outside Maya
        raise MayaUnavailable("maya.api.OpenMaya is only available inside Maya") from exc
    return open_maya


def mel():
    try:
        import maya.mel as maya_mel
    except Exception as exc:  # pragma: no cover - only hit outside Maya
        raise MayaUnavailable("maya.mel is only available inside Maya") from exc
    return maya_mel


def qt():
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        import shiboken2
        from maya import OpenMayaUI as omui
    except Exception as exc:  # pragma: no cover - only hit outside Maya
        raise MayaUnavailable("Maya PySide2 UI modules are only available inside Maya") from exc
    return QtCore, QtGui, QtWidgets, shiboken2, omui

