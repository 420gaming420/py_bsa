# BSA archive core data types
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from logic.bsa.flags import detect_flags
from logic.bsa.models import (
    ARCHIVE_COMPRESS,
    ARCHIVE_EMBEDNAME,
    ARCHIVE_FILENAMES,
    ARCHIVE_PATHNAMES,
    ArchiveFormat,
    BSAArchive,
    BSAFileEntry,
    CompressionFlag,
    CompressionMethod,
    FILE_MESHES,
    FILE_SIZE_COMPRESS,
    FILE_SIZE_MASK,
    FILE_TEXTURES,
)

from logic.hasher.hashes import TES3Hash, TES4Hash

__all__ = [
    "ArchiveFormat",
    "BSAArchive",
    "BSAFileEntry",
    "CompressionFlag",
    "CompressionMethod",
    "TES3Hash",
    "TES4Hash",
    "ARCHIVE_COMPRESS",
    "ARCHIVE_EMBEDNAME",
    "ARCHIVE_FILENAMES",
    "ARCHIVE_PATHNAMES",
    "FILE_MESHES",
    "FILE_TEXTURES",
    "FILE_SIZE_COMPRESS",
    "FILE_SIZE_MASK",
    "detect_flags",
]
