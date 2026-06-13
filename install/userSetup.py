"""Optional Maya userSetup bootstrap for Mio3 UV Maya.

Copy or source this from Maya's scripts path if automatic shelf/bootstrap
loading is desired. The add-on can also be launched manually with:

    import mio3_uv_maya
    mio3_uv_maya.show()
"""

from __future__ import annotations


def mio3_uv_maya_show():
    import mio3_uv_maya

    return mio3_uv_maya.show()

