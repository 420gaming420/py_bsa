# BSA archive models and constants
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class CompressionMethod(IntEnum):
    """Compression method used by each archive format.

    Mirrors TwbCompressionType from wbCompression.pas — TES5Edit@76d9d226.
    Values: ctNone=0, ctZLib=1, ctLZ4=2, ctLZ4F=3.
    """
    NONE = 0
    ZLIB = 1
    LZ4 = 2
    LZ4F = 3


class ArchiveFormat(IntEnum):
    """Supported BSA archive formats / versions."""

    TES3 = 0  # Morrowind — magic 0x00000100
    TES4 = 103  # Oblivion — magic 0x00415342 ("BSA\\0"), version 0x67
    FO3 = 104  # Fallout 3 / New Vegas / Skyrim LE — version 0x68
    SSE = 105  # Skyrim SE/AE — version 0x69
    FO4 = 1  # Fallout 4 — magic 0x42544458 ("BTDX"), general format
    FO4_DDS = 2  # Fallout 4 DDS — magic 0x42544458 ("BTDX"), DX10 format
    SF = 3  # Starfield — magic 0x42544458 ("BTDX"), general format, v2/v3
    SF_DDS = 4  # Starfield DDS — magic 0x42544458 ("BTDX"), DX10/GNMF format

    @classmethod
    def from_version(cls, version: int) -> "ArchiveFormat":
        """Map a numeric version to the closest ArchiveFormat."""
        mapping = {
            0: cls.TES3, 103: cls.TES4, 104: cls.FO3, 105: cls.SSE,
            1: cls.FO4, 2: cls.SF, 3: cls.SF,
        }
        return mapping.get(version, cls.TES4)

    @property
    def is_tes4_like(self) -> bool:
        """True for Oblivion-through-Skyrim LE format (v103/v104)."""
        return self in (self.TES4, self.FO3, self.SSE)

    @property
    def is_xbox(self) -> bool:
        """True for Xbox 360 big-endian variants (negative versions)."""
        return False  # Extended in reader if needed

    @property
    def is_ba2(self) -> bool:
        """True for BA2 (Fallout 4 / Starfield) format."""
        return self in (self.FO4, self.FO4_DDS, self.SF, self.SF_DDS)

    @property
    def uses_signed_hash(self) -> bool:
        """True for TES4/Oblivion which uses signed hash mode."""
        return self == self.TES4

    def default_compression(self) -> CompressionMethod:
        """Return the default compression method for this archive format.

        Mirrors TwbCustomBSArchive.DefaultCompression from wbBSArchive.pas:1096 — TES5Edit@76d9d226.
        """
        return _DEFAULT_COMPRESSION.get(self, CompressionMethod.ZLIB)

    @property
    def supports_lz4f(self) -> bool:
        """True if this format's default compression is LZ4F."""
        return self.default_compression() == CompressionMethod.LZ4F

    @property
    def supports_lz4(self) -> bool:
        """True if this format supports LZ4 (not LZ4F)."""
        return self.default_compression() == CompressionMethod.LZ4


# Default compression per archive format.
# Mirrors cArchiveCompressionTypes from wbBSArchive.pas:194-204 — TES5Edit@76d9d226
#   [baNone]     [ctNone]
#   [baTES3]     [ctNone]
#   [baTES4]     [ctNone]
#   [baFO3]      [ctZLib]
#   [baSSE]      [ctLZ4F]
#   [baFO4]      [ctZLib]
#   [baFO4dds]   [ctZLib]
#   [baSF]       [ctZLib, ctLZ4]   (ctZLib default, ctLZ4 for SFv3)
#   [baSFdds]    [ctLZ4, ctZLib]
_DEFAULT_COMPRESSION: dict[ArchiveFormat, CompressionMethod] = {
    ArchiveFormat.TES3: CompressionMethod.NONE,
    ArchiveFormat.TES4: CompressionMethod.NONE,
    ArchiveFormat.FO3: CompressionMethod.ZLIB,
    ArchiveFormat.SSE: CompressionMethod.LZ4F,
    ArchiveFormat.FO4: CompressionMethod.ZLIB,
    ArchiveFormat.FO4_DDS: CompressionMethod.ZLIB,
    ArchiveFormat.SF: CompressionMethod.ZLIB,
    ArchiveFormat.SF_DDS: CompressionMethod.LZ4,
}


# Archive flags (TES4-like)
# Imported from logic.bsa.constants
from logic.bsa.constants import (  # noqa: F401
    ARCHIVE_PATHNAMES, ARCHIVE_FILENAMES, ARCHIVE_COMPRESS,
    ARCHIVE_RETAINDIR, ARCHIVE_RETAINNAME, ARCHIVE_RETAINOFF,
    ARCHIVE_XBOX360, ARCHIVE_STARTUPSTR, ARCHIVE_EMBEDNAME,
    ARCHIVE_XMEM, ARCHIVE_UNKNOWN10, ARCHIVE_DEFAULT,
    FILE_SIZE_COMPRESS, FILE_SIZE_MASK,
    FILE_MESHES, FILE_TEXTURES, FILE_MENUS, FILE_SOUNDS,
    FILE_VOICES, FILE_SHADERS, FILE_TREES, FILE_FONTS, FILE_MISC,
)

# Compression flag in file size field
FILE_SIZE_COMPRESS = 0x40000000
FILE_SIZE_MASK = 0x3FFFFFFF


class CompressionFlag:
    """Describes whether a file entry is compressed."""

    __slots__ = ("compressed", "unpacked_size", "packed_size")

    def __init__(self, compressed: bool, unpacked_size: int, packed_size: int = 0) -> None:
        self.compressed = compressed
        self.unpacked_size = unpacked_size
        self.packed_size = packed_size

    @classmethod
    def from_size_flags(cls, size_flags: int) -> "CompressionFlag":
        compressed = bool(size_flags & 0x40000000)
        unpacked = size_flags & 0x3FFFFFFF
        return cls(compressed=compressed, unpacked_size=unpacked)

    def to_size_flags(self, archive_compressed: bool = False) -> int:
        """Encode compression state into size flags.

        The BSA format uses inverted per-file flags: when the archive-level
        COMPRESS flag is set, the per-file bit must be CLEAR for the file
        to be treated as compressed (XOR logic).
        """
        flags = self.unpacked_size & 0x3FFFFFFF
        file_compressed = self.compressed and not archive_compressed
        if file_compressed:
            flags |= 0x40000000
        return flags

    def __repr__(self) -> str:
        return f"CompressionFlag(compressed={self.compressed}, unpacked={self.unpacked_size}, packed={self.packed_size})"


@dataclass
class BSAFileEntry:
    """A single file entry inside a BSA archive."""

    name: str
    """Virtual path of the file inside the archive (e.g. ``meshes\\actor\\foo.nif``)."""

    directory_hash: int
    """64-bit hash of the directory path."""

    name_hash: int
    """64-bit hash of the filename."""

    compression: CompressionFlag
    """Compression state and unpacked size."""

    offset: int
    """Byte offset from the start of the file data section."""

    ext_hash: int = 0
    """4-byte little-endian extension hash (BA2 only)."""

    is_dx10: bool = False
    """True for BA2 DDS (DX10) format files."""

    width: int = 0
    """DDS texture width (DX10 only)."""

    height: int = 0
    """DDS texture height (DX10 only)."""

    mip_count: int = 0
    """Number of mip levels (DX10 only)."""

    dds_format: int = 0
    """DXGI format value (DX10 only)."""

    is_cubemap: bool = False
    """True if DDS is a cubemap (DX10 only)."""

    chunks: list[tuple[int, int, int, int, int]] | None = None
    """Per-chunk data: [(offset, comp_size, decomp_size, mip_first, mip_last), ...] (DX10 only)."""

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("BSAFileEntry offset must be non-negative")
        if self.compression.unpacked_size < 0:
            raise ValueError("BSAFileEntry unpacked_size must be non-negative")


@dataclass
class BSAArchive:
    """Parsed representation of a BSA archive."""

    fmt: ArchiveFormat
    """The archive format / game version."""

    flags: int
    """Archive flags (see hasher module constants)."""

    file_flags: int
    """File type flags."""

    files: list[BSAFileEntry] = field(default_factory=list)
    """All file entries, ordered as they appear in the archive."""

    data_start: int = 0
    """Byte offset from start of file where file data begins (TES3 only)."""

    _compression_method: Optional[CompressionMethod] = None
    """Detected compression method (BA2 SFv3: LZ4 or ZLIB). None uses format default."""

    # --- convenience properties ---

    @property
    def compressed(self) -> bool:
        """Whether the archive has the COMPRESSED flag set."""
        return bool(self.flags & ARCHIVE_COMPRESS)

    @property
    def has_directory_names(self) -> bool:
        return bool(self.flags & ARCHIVE_PATHNAMES)

    @property
    def has_file_names(self) -> bool:
        return bool(self.flags & ARCHIVE_FILENAMES)

    @property
    def embedded_names(self) -> bool:
        return bool(self.flags & ARCHIVE_EMBEDNAME)

    def file_by_hash(self, name_hash: int) -> Optional[BSAFileEntry]:
        """Look up a file entry by its name hash."""
        for f in self.files:
            if f.name_hash == name_hash:
                return f
        return None

    def files_by_directory(self, directory_hash: int) -> list[BSAFileEntry]:
        """Return all file entries belonging to a directory hash."""
        return [f for f in self.files if f.directory_hash == directory_hash]

    def __len__(self) -> int:
        return len(self.files)

    def __iter__(self):
        return iter(self.files)

    def __repr__(self) -> str:
        return (
            f"BSAArchive(fmt={self.fmt.name}, "
            f"files={len(self.files)}, "
            f"compressed={self.compressed})"
        )
