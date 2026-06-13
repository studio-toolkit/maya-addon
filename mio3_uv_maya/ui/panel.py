"""Dockable Mio3 UV panel."""

from __future__ import annotations

from ..core.maya_api import qt
from ..core.settings import Settings
from ..operators import align, arrange, selection, texel, unwrap, utility
from .icons import icon_path


QtCore, QtGui, QtWidgets, _shiboken2, _omui = qt()


class Mio3UVPanel(QtWidgets.QWidget):
    """Main Maya panel mirroring the Blender add-on panel families."""

    def __init__(self, parent=None):
        super(Mio3UVPanel, self).__init__(parent)
        self.settings = Settings.load()
        self.setObjectName("Mio3UVMayaPanel")
        self.setWindowTitle("Mio3 UV")
        self._build()

    def _build(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget()
        outer.addWidget(self.tabs)

        self.tabs.addTab(self._main_tab(), "Main")
        self.tabs.addTab(self._actions_tab("Align", align.ACTIONS), "Align")
        self.tabs.addTab(self._actions_tab("Arrange", arrange.ACTIONS), "Arrange")
        self.tabs.addTab(self._actions_tab("Symmetry", [a for a in selection.ACTIONS if a.id in ("symmetrize", "symmetry_snap")]), "Symmetry")
        self.tabs.addTab(self._actions_tab("Select", [a for a in selection.ACTIONS if a.id not in ("symmetrize", "symmetry_snap")]), "Select")
        self.tabs.addTab(self._utility_tab(), "Utility")
        self.tabs.addTab(self._options_tab(), "Options")

    def _main_tab(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        layout.addWidget(self._button_grid([
            unwrap.ACTIONS[0],
            unwrap.ACTIONS[1],
            align.ACTIONS[0],
            unwrap.ACTIONS[2],
            unwrap.ACTIONS[3],
            unwrap.ACTIONS[4],
        ], columns=2))
        layout.addStretch()
        return widget

    def _utility_tab(self):
        actions = utility.ACTIONS + texel.ACTIONS
        return self._actions_tab("Utility", actions)

    def _options_tab(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.checker_size = QtWidgets.QComboBox()
        self.checker_size.addItems(["512", "1024", "2048", "4096", "8192"])
        self.checker_size.setCurrentText(self.settings.checker_map_size)
        self.checker_size.currentTextChanged.connect(self._save_checker_size)
        layout.addRow("Checker Size", self.checker_size)

        self.texel_density = QtWidgets.QDoubleSpinBox()
        self.texel_density.setRange(0.01, 100000.0)
        self.texel_density.setDecimals(4)
        self.texel_density.setValue(float(self.settings.texel_density))
        self.texel_density.valueChanged.connect(self._save_texel_density)
        layout.addRow("Texel Density", self.texel_density)

        gridify_box = QtWidgets.QGroupBox("Gridify")
        gridify_layout = QtWidgets.QFormLayout(gridify_box)
        gridify_layout.setContentsMargins(8, 8, 8, 8)

        self.gridify_ratio = QtWidgets.QDoubleSpinBox()
        self.gridify_ratio.setRange(0.0, 1.0)
        self.gridify_ratio.setDecimals(3)
        self.gridify_ratio.setSingleStep(0.05)
        self.gridify_ratio.setValue(float(self.settings.gridify_ratio_influence))
        self.gridify_ratio.valueChanged.connect(self._save_gridify_ratio)
        gridify_layout.addRow("Geometry Ratio", self.gridify_ratio)

        self.gridify_evenness = QtWidgets.QDoubleSpinBox()
        self.gridify_evenness.setRange(0.0, 1.0)
        self.gridify_evenness.setDecimals(3)
        self.gridify_evenness.setSingleStep(0.05)
        self.gridify_evenness.setValue(float(self.settings.gridify_shape_blend))
        self.gridify_evenness.valueChanged.connect(self._save_gridify_evenness)
        gridify_layout.addRow("Evenness", self.gridify_evenness)

        self.gridify_normalize = QtWidgets.QCheckBox()
        self.gridify_normalize.setChecked(bool(self.settings.gridify_normalize))
        self.gridify_normalize.toggled.connect(self._save_gridify_normalize)
        gridify_layout.addRow("Normalize", self.gridify_normalize)

        self.gridify_keep_aspect = QtWidgets.QCheckBox()
        self.gridify_keep_aspect.setChecked(bool(self.settings.gridify_keep_aspect))
        self.gridify_keep_aspect.setEnabled(bool(self.settings.gridify_normalize))
        self.gridify_keep_aspect.toggled.connect(self._save_gridify_keep_aspect)
        gridify_layout.addRow("Keep Aspect Ratio", self.gridify_keep_aspect)

        layout.addRow(gridify_box)

        rectify_box = QtWidgets.QGroupBox("Rectify")
        rectify_layout = QtWidgets.QFormLayout(rectify_box)
        rectify_layout.setContentsMargins(8, 8, 8, 8)

        self.rectify_bbox_type = QtWidgets.QComboBox()
        self.rectify_bbox_type.addItem("Average", "AVERAGE")
        self.rectify_bbox_type.addItem("Max", "BBOX")
        self.rectify_bbox_type.setCurrentIndex(max(0, self.rectify_bbox_type.findData(self.settings.rectify_bbox_type)))
        self.rectify_bbox_type.currentIndexChanged.connect(self._save_rectify_bbox_type)
        rectify_layout.addRow("Scale", self.rectify_bbox_type)

        self.rectify_distribute = QtWidgets.QComboBox()
        self.rectify_distribute.addItem("Geometry", "GEOMETRY")
        self.rectify_distribute.addItem("Even", "EVEN")
        self.rectify_distribute.addItem("None", "NONE")
        self.rectify_distribute.setCurrentIndex(max(0, self.rectify_distribute.findData(self.settings.rectify_distribute)))
        self.rectify_distribute.currentIndexChanged.connect(self._save_rectify_distribute)
        rectify_layout.addRow("Align UVs", self.rectify_distribute)

        self.rectify_unwrap_method = QtWidgets.QComboBox()
        self.rectify_unwrap_method.addItem("Angle Based", "ANGLE_BASED")
        self.rectify_unwrap_method.addItem("Conformal", "CONFORMAL")
        self.rectify_unwrap_method.addItem("Minimum Stretch", "MINIMUM_STRETCH")
        self.rectify_unwrap_method.setCurrentIndex(max(0, self.rectify_unwrap_method.findData(self.settings.rectify_unwrap_method)))
        self.rectify_unwrap_method.currentIndexChanged.connect(self._save_rectify_unwrap_method)
        rectify_layout.addRow("Unwrap Method", self.rectify_unwrap_method)

        self.rectify_unwrap = QtWidgets.QCheckBox()
        self.rectify_unwrap.setChecked(bool(self.settings.rectify_unwrap))
        self.rectify_unwrap.toggled.connect(self._save_rectify_unwrap)
        rectify_layout.addRow("Unwrap", self.rectify_unwrap)

        self.rectify_stretch = QtWidgets.QCheckBox()
        self.rectify_stretch.setChecked(bool(self.settings.rectify_stretch))
        self.rectify_stretch.setEnabled(bool(self.settings.rectify_unwrap))
        self.rectify_stretch.toggled.connect(self._save_rectify_stretch)
        rectify_layout.addRow("Stretch", self.rectify_stretch)

        self.rectify_pin = QtWidgets.QCheckBox()
        self.rectify_pin.setChecked(bool(self.settings.rectify_pin))
        self.rectify_pin.toggled.connect(self._save_rectify_pin)
        rectify_layout.addRow("Pinned", self.rectify_pin)

        layout.addRow(rectify_box)

        self.symmetry_uv_axis = QtWidgets.QComboBox()
        self.symmetry_uv_axis.addItems(["X", "Y"])
        self.symmetry_uv_axis.setCurrentText(self.settings.symmetry_uv_axis)
        self.symmetry_uv_axis.currentTextChanged.connect(self._save_symmetry_uv_axis)
        layout.addRow("Symmetry UV Axis", self.symmetry_uv_axis)

        self.symmetry_3d_axis = QtWidgets.QComboBox()
        self.symmetry_3d_axis.addItems(["AUTO", "X", "Y", "Z"])
        self.symmetry_3d_axis.setCurrentText(self.settings.symmetry_3d_axis)
        self.symmetry_3d_axis.currentTextChanged.connect(self._save_symmetry_3d_axis)
        layout.addRow("Symmetry 3D Axis", self.symmetry_3d_axis)

        return widget

    def _actions_tab(self, _title, actions):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._button_grid(actions, columns=2))
        layout.addStretch()
        return widget

    def _button_grid(self, actions, columns=2):
        holder = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for index, action in enumerate(actions):
            button = QtWidgets.QPushButton(action.label)
            button.setToolTip(action.tooltip)
            path = icon_path(action.icon)
            if path:
                button.setIcon(QtGui.QIcon(path))
            button.clicked.connect(action.run)
            row = index // columns
            col = index % columns
            grid.addWidget(button, row, col)
        return holder

    def _save_checker_size(self, value):
        self.settings.checker_map_size = value
        self.settings.save()

    def _save_texel_density(self, value):
        self.settings.texel_density = float(value)
        self.settings.save()

    def _save_gridify_ratio(self, value):
        self.settings.gridify_ratio_influence = float(value)
        self.settings.save()

    def _save_gridify_evenness(self, value):
        self.settings.gridify_shape_blend = float(value)
        self.settings.save()

    def _save_gridify_normalize(self, value):
        self.settings.gridify_normalize = bool(value)
        self.gridify_keep_aspect.setEnabled(bool(value))
        self.settings.save()

    def _save_gridify_keep_aspect(self, value):
        self.settings.gridify_keep_aspect = bool(value)
        self.settings.save()

    def _save_rectify_bbox_type(self, *_args):
        self.settings.rectify_bbox_type = self.rectify_bbox_type.currentData()
        self.settings.save()

    def _save_rectify_distribute(self, *_args):
        self.settings.rectify_distribute = self.rectify_distribute.currentData()
        self.settings.save()

    def _save_rectify_unwrap_method(self, *_args):
        self.settings.rectify_unwrap_method = self.rectify_unwrap_method.currentData()
        self.settings.save()

    def _save_rectify_unwrap(self, value):
        self.settings.rectify_unwrap = bool(value)
        self.rectify_stretch.setEnabled(bool(value))
        self.settings.save()

    def _save_rectify_stretch(self, value):
        self.settings.rectify_stretch = bool(value)
        self.settings.save()

    def _save_rectify_pin(self, value):
        self.settings.rectify_pin = bool(value)
        self.settings.save()

    def _save_symmetry_uv_axis(self, value):
        self.settings.symmetry_uv_axis = value
        self.settings.save()

    def _save_symmetry_3d_axis(self, value):
        self.settings.symmetry_3d_axis = value
        self.settings.save()
