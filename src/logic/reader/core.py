# BSA archive reader core
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import BinaryIO, Optional

from logic.bsa import ArchiveFormat, BSAFileEntry, BSAArchive, CompressionMethod
from logic.reader.extraction import read_file, compute_data_start, find_entry
from logic.reader.tes3 import _read_tes3, dump_tes3
from logic.reader.tes4 import _read_tes4, dump_tes4
from logic.reader.ba2 import _read_ba2, dump_ba2


_MAGIC_TES3 = struct.pack("<I", 0x00000100)
_MAGIC_BSA = b"BSA\x00"
_MAGIC_BTDX = b"BTDX"


class BSAReader:
    """Reads and extracts files from BSA archives."""

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self._path = Path(path) if path else None
        self._archive: Optional[BSAArchive] = None
        self._data: Optional[bytes] = None
        self._compression_method: Optional[CompressionMethod] = None

    @property
    def archive(self) -> BSAArchive:
        if self._archive is None:
            if self._path is None:
                raise ValueError("No path set; call load() first")
            self.load(self._path)
        return self._archive

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def load(self, path: Path | str) -> BSAArchive:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"BSA file not found: {p}")
        self._path = p
        with open(p, "rb") as f:
            self._archive = self._read(f)
        self._compression_method = self._detect_compression(self._archive)
        return self._archive

    def load_bytes(self, data: bytes) -> BSAArchive:
        self._data = data
        self._archive = self._read(io.BytesIO(data))
        self._compression_method = self._detect_compression(self._archive)
        return self._archive

    def read_file(self, entry: BSAFileEntry) -> bytes:
        if self._path is None and self._data is None:
            raise ValueError("No archive loaded")
        # TES3 uses relative offsets (from data_start); TES4+ also uses relative offsets
        data_start = self.archive.data_start
        if self._data is not None:
            return read_file(io.BytesIO(self._data), entry, is_ba2=self.archive.fmt.is_ba2,
                             data_start=data_start, archive_flags=self.archive.flags,
                             archive_fmt=self.archive.fmt,
                             compression_method=self._compression_method)
        with open(self._path, "rb") as f:
            return read_file(f, entry, is_ba2=self.archive.fmt.is_ba2,
                             data_start=data_start, archive_flags=self.archive.flags,
                             archive_fmt=self.archive.fmt,
                             compression_method=self._compression_method)

    def read_file_by_name(self, name: str) -> bytes:
        entry = find_entry(self.archive, name)
        if entry is None:
            raise KeyError(f"File not found in archive: {name}")
        return self.read_file(entry)

    def list_files(self) -> list[str]:
        return [f.name for f in self.archive.files]

    def __iter__(self):
        return iter(self.archive.files)

    def info(self) -> str:
        a = self.archive
        comp = sum(1 for f in a.files if f.compression.compressed)
        uncomp = len(a.files) - comp
        if self._path is None and self._data is not None:
            path_name = "bytes"
        else:
            path_name = self._path.name if self._path else "unknown"
        fmt_name = {
            0: "Morrowind",
            103: "Oblivion",
            104: "FO3",
            105: "SSE",
            1: "FO4",
            3: "Starfield",
        }.get(int(a.fmt), a.fmt.name)
        return (
            f"BSA Archive: {path_name}\n"
            f"  Format:    {fmt_name} (v{int(a.fmt)})\n"
            f"  Files:     {len(a.files)}\n"
            f"  Compressed: {'yes' if a.compressed else 'no'}\n"
            f"  Flags:     0x{a.flags:08X}\n"
            f"  FileFlags: 0x{a.file_flags:08X}\n"
            f"  Compressed files: {comp}  Uncompressed: {uncomp}"
        )

    def dump(self) -> str:
        """Dump archive in BSArch-compatible info format."""
        a = self.archive
        if self._path is not None:
            name = self._path.name
        else:
            name = "unknown"
        if a.fmt == ArchiveFormat.TES3:
            lines = [f"  Archive Name: {name}"]
            lines.extend(dump_tes3(a).split("\n"))
            return "\n".join(lines)
        elif a.fmt.is_ba2:
            lines = [f"  Archive Name: {name}"]
            lines.extend(dump_ba2(a).split("\n"))
            return "\n".join(lines)
        else:
            lines = [f"  Archive Name: {name}"]
            lines.extend(dump_tes4(a).split("\n"))
            return "\n".join(lines)

    def _detect_compression(self, archive: BSAArchive) -> Optional[CompressionMethod]:
        """Detect the compression method used by an archive.

        For BA2 archives, reads the CompressionMethod field from the header
        (SFv3 uses LZ4, others use zlib). For BSA archives, uses the format
        default. Mirrors wbBSArchive.pas:1587-1590 — TES5Edit@76d9d226.
        """
        if archive.fmt.is_ba2 and archive.fmt in (ArchiveFormat.SF, ArchiveFormat.SF_DDS):
            # SF v3 stores CompressionMethod in header: 0=zlib, 3=lz4
            # Read from the archive file if available
            if self._path is not None:
                try:
                    with open(self._path, "rb") as f:
                        f.read(16)  # magic(4) + version(4) + format(4) + fileCount(4)
                        str_off = struct.unpack("<Q", f.read(8))[0]
                        f.read(8)  # UInt64 padding
                        if str_off > 36:  # v3 header has 36 bytes before data
                            f.seek(32)  # after magic+version+format+fc+strOff
                            f.read(4)  # UInt64
                            comp_byte = struct.unpack("<I", f.read(4))[0]
                            from logic.bsa.constants import COMPRESSION_METHOD_LZ4
                            if comp_byte == COMPRESSION_METHOD_LZ4:
                                return CompressionMethod.LZ4
                    return CompressionMethod.ZLIB
                except Exception:
                    pass
            return archive.fmt.default_compression()
        return archive.fmt.default_compression()

    def _compute_tes3_data_start(self, path: Path) -> int:
        """Compute the byte offset where TES3 file data begins."""
        with open(path, "rb") as f:
            f.read(4)  # magic
            hash_offset = struct.unpack("<I", f.read(4))[0]
            file_count = struct.unpack("<I", f.read(4))[0]
        # C++ formula: hash_offset + header_size + file_count * hash_size
        # where header_size=12, hash_size=8
        return hash_offset + 12 + file_count * 8

    # ------------------------------------------------------------------
    def _read(self, f: BinaryIO) -> BSAArchive:
        magic = f.read(4)
        if magic == _MAGIC_TES3:
            return _read_tes3(f)
        elif magic == _MAGIC_BSA:
            return _read_tes4(f)
        elif magic == _MAGIC_BTDX:
            return _read_ba2(f)
        else:
            raise ValueError(f"Unknown BSA magic: {magic!r}")
