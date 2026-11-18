# BSA archive constants
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

from enum import IntEnum


# ---------------------------------------------------------------------------
# Archive format flags
# ---------------------------------------------------------------------------

# Flag bits in the header flags field
ARCHIVE_PATHNAMES  = 0x0001  # Include Directory Names
ARCHIVE_FILENAMES  = 0x0002  # Include File Names
ARCHIVE_COMPRESS   = 0x0004  # Compressed
ARCHIVE_RETAINDIR  = 0x0008  # Retain Directory Names
ARCHIVE_RETAINNAME = 0x0010  # Retain File Names
ARCHIVE_RETAINOFF  = 0x0020  # Retain File Name Offsets
ARCHIVE_XBOX360    = 0x0040  # XBox 360 Archive
ARCHIVE_STARTUPSTR = 0x0080  # Retain Strings During Startup
ARCHIVE_EMBEDNAME  = 0x0100  # Embedded File Names
ARCHIVE_XMEM       = 0x0200  # XMem Codec
ARCHIVE_UNKNOWN10  = 0x0400  # Unknown flag

ARCHIVE_DEFAULT = ARCHIVE_PATHNAMES | ARCHIVE_FILENAMES  # always-set base flags

# Mask bits for the compression field
FILE_SIZE_COMPRESS = 0x40000000
FILE_SIZE_MASK = 0x3FFFFFFF

# File type flags
FILE_MESHES   = 0x0001
FILE_TEXTURES = 0x0002
FILE_MENUS    = 0x0004
FILE_SOUNDS   = 0x0008
FILE_VOICES   = 0x0010
FILE_SHADERS  = 0x0020
FILE_TREES    = 0x0040
FILE_FONTS    = 0x0080
FILE_MISC     = 0x0100

# Magic constants
MAGIC_BSA = b"BSA\x00"
MAGIC_BTDX = b"BTDX"
MAGIC_TES3 = b"\x00\x00\x01\x00"

# BA2 SFv3 compression method field values
# Mirrors COMPRESSION_METHOD_* constants from wbBSArchive.pas — TES5Edit@76d9d226
COMPRESSION_METHOD_ZLIB = 0
COMPRESSION_METHOD_LZ4 = 3


# ---------------------------------------------------------------------------
# Archive format
# ---------------------------------------------------------------------------

class ArchiveFormat(IntEnum):
    """TES / Bethesda archive format version."""

    TES3 = 0x00000100
    TES4 = 0x67
    FO3 = 0x68
    SSE = 0x69
