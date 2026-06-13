"""Shared package constants."""

PACKAGE_NAME = "mio3_uv_maya"
DISPLAY_NAME = "Mio3 UV"
VERSION = "0.1.0"

WORKSPACE_CONTROL = "Mio3UVMayaWorkspaceControl"
OBJECT_METADATA_ATTR = "mio3UvMayaData"
OPTION_PREFIX = "mio3UvMaya"

OWNED_PREFIX = "mio3UvMaya_"
CHECKER_SHADER_PREFIX = OWNED_PREFIX + "checkerShader_"
CHECKER_FILE_PREFIX = OWNED_PREFIX + "checkerFile_"
CHECKER_PLACE2D_PREFIX = OWNED_PREFIX + "checkerPlace2d_"
CHECKER_SHADING_GROUP_PREFIX = OWNED_PREFIX + "checkerSG_"
UVMESH_GROUP = OWNED_PREFIX + "uvMeshPreview_GRP"

DEFAULT_TEXTURE_SIZES = ("512", "1024", "2048", "4096", "8192")
PADDING_AUTO = {
    "512": 4,
    "1024": 8,
    "2048": 16,
    "4096": 32,
    "8192": 64,
}

