# Mio3 UV Maya

Mio3 UV Maya is a dockable Autodesk Maya port of the Mio3 UV workflow. It brings the Blender add-on's UV editing ideas into a Maya-native Python/PySide2 package built around Maya's `OpenMaya.MFnMesh` UV data model.

The project is currently an early, usable port foundation: core UV shell models, a dockable panel, asset loading, and a first pass of practical operators are in place. Full Blender feature parity is intentionally staged behind explicit placeholders instead of pretending incomplete tools are finished.

## Highlights

- Dockable `workspaceControl` UI for Maya 2022-2024.
- PySide2 panel with Main, Align, Arrange, Symmetry, Select, Utility, and Options tabs.
- Maya-native UV shell and UV component models.
- Working first-pass tools for unfold/project, gridify, normalize, align, mirror, rotate, distribute, sort, relax, circle, stack, shuffle, merge, stitch, texel density get/set, selection helpers, checker maps, and UV mesh preview scaffolding.
- Bundled Mio3 icon set and checker map textures.
- Settings persisted through Maya option variables.

## Repository Layout

```text
mio3_uv_maya/
  assets/          Icons and checker map textures.
  core/            Maya API wrappers, UV data models, settings, undo helpers.
  operators/       Tool actions grouped by workflow area.
  ui/              Dock and panel implementation.
install/
  mio3_uv_maya.mod Maya module file.
  userSetup.py     Optional bootstrap helper.
```

## Requirements

- Autodesk Maya 2022, 2023, or 2024.
- Python and PySide2 as bundled with Maya.
- A mesh with UVs for most operators.

## Install

### Option 1: Maya Module

1. Clone this repository somewhere stable, for example:

   ```bash
   git clone https://github.com/studio-toolkit/maya-addon.git
   ```

2. Copy `install/mio3_uv_maya.mod` into one of Maya's module paths.

3. Edit the module file if needed so the module root points at the cloned repository path.

4. Restart Maya.

### Option 2: Python Path

Add the repository root to Maya's Python path, then run:

```python
import mio3_uv_maya
mio3_uv_maya.show()
```

## Launch

Run this in Maya's Python tab or attach it to a shelf button:

```python
import mio3_uv_maya
mio3_uv_maya.show()
```

During development, reload the package without restarting Maya:

```python
import mio3_uv_maya
mio3_uv_maya.reload_package()
mio3_uv_maya.show()
```

## Current Status

Implemented:

- Dockable Maya UI shell.
- Maya UV object, island, and node data foundation.
- Normalize, gridify, align, mirror, rotate, distribute, and 3D-position sort.
- Relax, circle, stack, shuffle, merge, and stitch.
- Texel density estimate and selected-shell scale-to-density.
- Basic selection and checker map utilities.
- UV mesh preview scaffold.

In progress:

- Full algorithmic parity for advanced Blender Mio3 UV tools.
- Padding overlay and exposure behavior adapted to Maya.
- More robust symmetry, stitch, unfoldify, body-part layout, and seam workflows.

## Development

Syntax-check the package from the repository root:

```bash
python3 -m compileall mio3_uv_maya
```

Most runtime behavior must be tested inside Maya because the package depends on Maya's Python modules and scene state.

Minimum smoke test:

1. Load the package in Maya.
2. Run `mio3_uv_maya.show()`.
3. Confirm the dock opens and closes cleanly.
4. Select a mesh with UVs.
5. Try Normalize, Align, Checker Map, and undo/redo.

## License

This port follows the Mio3 UV add-on licensing lineage and is distributed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
