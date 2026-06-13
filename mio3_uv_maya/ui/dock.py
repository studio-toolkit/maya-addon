"""workspaceControl integration."""

from __future__ import annotations

from ..constants import DISPLAY_NAME, WORKSPACE_CONTROL
from ..core.maya_api import cmds, qt


def _delete_existing():
    maya_cmds = cmds()
    if maya_cmds.workspaceControl(WORKSPACE_CONTROL, exists=True):
        maya_cmds.deleteUI(WORKSPACE_CONTROL, control=True)


def _maya_main_window():
    QtCore, QtGui, QtWidgets, shiboken2, omui = qt()
    ptr = omui.MQtUtil.mainWindow()
    return shiboken2.wrapInstance(int(ptr), QtWidgets.QWidget)


def _workspace_control_widget():
    QtCore, QtGui, QtWidgets, shiboken2, omui = qt()
    ptr = omui.MQtUtil.findControl(WORKSPACE_CONTROL)
    if ptr is None:
        return None
    return shiboken2.wrapInstance(int(ptr), QtWidgets.QWidget)


def build_ui():
    from .panel import Mio3UVPanel

    QtCore, QtGui, QtWidgets, _shiboken2, _omui = qt()
    parent = _workspace_control_widget()
    if parent is None:
        parent = _maya_main_window()
    layout = parent.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
    for child in parent.findChildren(QtWidgets.QWidget, "Mio3UVMayaPanel"):
        child.setParent(None)
        child.deleteLater()
    panel = Mio3UVPanel(parent)
    layout.addWidget(panel)
    return panel


def show():
    maya_cmds = cmds()
    if maya_cmds.workspaceControl(WORKSPACE_CONTROL, exists=True):
        maya_cmds.workspaceControl(WORKSPACE_CONTROL, edit=True, restore=True, visible=True)
        return build_ui()

    ui_script = "import mio3_uv_maya.ui.dock as dock; dock.build_ui()"
    maya_cmds.workspaceControl(
        WORKSPACE_CONTROL,
        label=DISPLAY_NAME,
        retain=False,
        floating=False,
        dockToMainWindow=("right", True),
        initialWidth=340,
        minimumWidth=280,
        uiScript=ui_script,
        loadImmediately=True,
    )
    return build_ui()


def close():
    _delete_existing()

