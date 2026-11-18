# BSA archive reader — file extraction
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path
from typing import BinaryIO, Optional

from logic.bsa import ArchiveFormat, BSAFileEntry, BSAArchive, CompressionMethod

try:
    import lz4.frame as lz4f
    import lz4.block as lz4b
    _HAS_LZ4 = True
except ImportError:
    _HAS_LZ4 = False


def _is_valid_zlib_header(data: bytes) -> bool:
    """Check if data starts with a valid zlib header (matching BSArch)."""
    if len(data) < 2:
        return False
    cmf = data[0]
    flg = data[1]
    return (cmf & 0x0F == 8) and (cmf >> 4 <= 7) and ((cmf * 256 + flg) % 31 == 0) and (flg & 0x20 == 0)


def _decompress_lz4f(raw: bytes, expected_size: int,
                      entry: BSAFileEntry) -> bytes:
    """Decompress LZ4F frame data (used by SSE archives).

    Mirrors LZ4FDecompress from wbCompression.pas:211-251 — TES5Edit@76d9d226.
    """
    if not _HAS_LZ4:
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: lz4 package not installed. "
            f"Install with: pip install lz4"
        )
    try:
        result = lz4f.decompress(raw)
    except Exception as exc:
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: {exc}"
        ) from exc
    if len(result) != expected_size:
        raise RuntimeError(
            f"Decompressed size mismatch for {entry.name!r}: "
            f"expected {expected_size}, got {len(result)}"
        )
    return result


def _decompress_lz4(raw: bytes, expected_size: int,
                     entry: BSAFileEntry) -> bytes:
    """Decompress raw LZ4 block data (used by Starfield v3 archives).

    Mirrors LZ4Decompress from wbCompression.pas — TES5Edit@76d9d226.
    """
    if not _HAS_LZ4:
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: lz4 package not installed. "
            f"Install with: pip install lz4"
        )
    try:
        result = lz4b.decompress(raw, uncompressed_size=expected_size)
    except Exception as exc:
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: {exc}"
        ) from exc
    if len(result) != expected_size:
        raise RuntimeError(
            f"Decompressed size mismatch for {entry.name!r}: "
            f"expected {expected_size}, got {len(result)}"
        )
    return result


def _decompress_with_trailer_fallback(raw: bytes, expected_size: int,
                                       entry: BSAFileEntry) -> bytes:
    """Fall back to raw deflate when zlib fails, for missing Adler-32 trailer.

    Matches BSArch fix ad8c249b: try decompressing as raw deflate (skip 2-byte
    zlib header), accept only if it decodes to exactly expected_size and fewer
    than 4 input bytes remain unconsumed (missing or truncated trailer).
    """
    if not _is_valid_zlib_header(raw):
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: invalid zlib header"
        )
    # Try raw deflate (skip 2-byte zlib header), tracking consumed bytes
    try:
        d = zlib.decompressobj(-zlib.MAX_WBITS)
        result = d.decompress(raw[2:])
    except zlib.error as exc:
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: {exc}"
        ) from exc
    consumed = len(raw) - 2 - len(d.unused_data)
    if len(result) != expected_size:
        raise RuntimeError(
            f"Decompressed size mismatch for {entry.name!r}: "
            f"expected {expected_size}, got {len(result)}"
        )
    if consumed + 4 <= len(raw) - 2:
        raise RuntimeError(
            f"Decompression failed for {entry.name!r}: "
            f"trailer present but zlib stream was still invalid"
        )
    return result


def _make_dds_header(width: int, height: int, mip_count: int,
                      dds_format: int, is_cubemap: bool = False,
                      unpacked_size: int = 0) -> bytes:
    """Build a 128-byte DDS header matching BSArch's output for DX10 textures."""
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)

    if dds_format == 87:
        # Format 87 is stored as raw 32-bit BGRA pixels
        struct.pack_into("<I", header, 8, 0x0002100F)
        struct.pack_into("<I", header, 12, height)
        struct.pack_into("<I", header, 16, width)
        struct.pack_into("<I", header, 20, width * 4)
        struct.pack_into("<I", header, 24, 1)
        struct.pack_into("<I", header, 28, mip_count)
        struct.pack_into("<I", header, 76, 32)
        struct.pack_into("<I", header, 80, 0x00000041)
        struct.pack_into("<I", header, 88, 32)
        struct.pack_into("<I", header, 92, 0x00FF0000)
        struct.pack_into("<I", header, 96, 0x0000FF00)
        struct.pack_into("<I", header, 100, 0x000000FF)
        struct.pack_into("<I", header, 104, 0xFF000000)
        # dwCaps at 108, dwCaps2 at 112 (wbDDS.pas:180-205)
        caps2 = 0x00008200 if is_cubemap else 0
        struct.pack_into("<I", header, 112, caps2)
    else:
        struct.pack_into("<I", header, 8, 0x000A1007)
        struct.pack_into("<I", header, 12, height)
        struct.pack_into("<I", header, 16, width)
        # Linear size for base mip (bytes per 4x4 block)
        if dds_format in (71, 72, 73, 81, 82):  # BC1, BC4
            linear = ((width + 3) // 4) * ((height + 3) // 4) * 8
        elif dds_format in (75, 76, 77, 78, 79, 80, 83, 84, 85, 87):  # BC2, BC3, BC5
            linear = ((width + 3) // 4) * ((height + 3) // 4) * 16
        elif dds_format > 92:  # Non-standard formats (e.g. 98): use unpacked size
            linear = unpacked_size
        else:
            linear = 0
        struct.pack_into("<I", header, 20, linear)
        struct.pack_into("<I", header, 24, 1)
        struct.pack_into("<I", header, 28, mip_count)
        struct.pack_into("<I", header, 76, 32)
        struct.pack_into("<I", header, 80, 4)
        fourcc_map = {
            71: b"DXT1", 72: b"DXT1", 73: b"DXT1",
            75: b"DXT3", 76: b"DXT3",
            77: b"DXT5", 78: b"DXT5", 79: b"DXT5", 80: b"DXT5",
            81: b"BC4U", 82: b"BC4S",
            83: b"BC5U", 84: b"BC5S", 85: b"BC5S", 87: b"BC5S",
        }
        header[84:88] = fourcc_map.get(dds_format, b"DXT1")
        # caps2: 0x00000000 for regular textures, DDSCAPS2_CUBEMAP | DDSCAPS2_CUBEMAP_ALLFACES for cubemaps
        # (wbDDS.pas:899 - dwCaps2 only set for cubemaps in source; v1.0 binary has bug writing to dwCaps)
        caps2 = 0x00008200 if is_cubemap else 0
        struct.pack_into("<I", header, 112, caps2)

    return bytes(header)


def _make_dx10_header(dxgi_format: int, is_cubemap: bool = False) -> bytes:
    """Build a 20-byte DX10 extra header matching BSArch's output.

    Reference: TES5Edit@76d9d226 Core/wbDDS.pas:208-215 (TDDSHeaderDX10 layout)
    The DX10 header is placed at offset 124 (replacing reserved2 in the 128-byte
    DDS header), not after it.
    """
    return struct.pack(
        "<IIIII",
        dxgi_format,      # dxgiFormat (4 bytes) at offset 124
        3,                # resourceDimension = D3D10_RESOURCE_DIMENSION_TEXTURE2D
        0x1 if is_cubemap else 0,  # miscFlags = DDS_RESOURCE_MISC_TEXTURECUBE
        1,                # arraySize
        0,                # miscFlags2
    )


def read_file(f: BinaryIO, entry: BSAFileEntry, is_ba2: bool = False,
              data_start: int = 0, archive_flags: int = 0,
              archive_fmt: Optional[ArchiveFormat] = None,
              compression_method: Optional[CompressionMethod] = None) -> bytes:
    """Read a file's data from the archive stream.

    For TES3 (Morrowind) archives, file offsets are relative to data_start.
    For TES4+ archives, file offsets are absolute (point to data in the
    data stream), not relative to data_start.
    """
    # TES3 uses relative offsets; TES4+ uses absolute offsets
    if data_start != 0:
        seek_pos = data_start + entry.offset
    else:
        seek_pos = entry.offset
    f.seek(seek_pos)

    if entry.compression.compressed:
        # BA2 (FO4/SF) compressed files: raw zlib data, no prefix
        # TES4+ compressed files:
        #   - FO3/SSE with EMBEDNAME: embedded name (1-byte len + name bytes)
        #     + 4-byte unpacked size prefix + zlib-compressed data
        #   - TES4 (Oblivion) / FO3 without EMBEDNAME:
        #     4-byte unpacked size prefix + zlib-compressed data
        if is_ba2:
            # BA2 DX10 files have multiple non-contiguous chunks; read each separately
            if entry.chunks:
                parts: list[bytes] = []
                for chunk_off, chunk_cs, chunk_ds, _, _ in entry.chunks:
                    f.seek(chunk_off)
                    chunk_raw = f.read(chunk_cs)
                    # BA2 compression dispatch (mirrors wbBSArchive.pas decompression) — TES5Edit@76d9d226
                    if compression_method == CompressionMethod.LZ4:
                        chunk_raw = _decompress_lz4(chunk_raw, chunk_ds, entry)
                    elif compression_method == CompressionMethod.LZ4F:
                        chunk_raw = _decompress_lz4f(chunk_raw, chunk_ds, entry)
                    else:
                        try:
                            chunk_raw = zlib.decompress(chunk_raw)
                        except zlib.error as exc:
                            raise RuntimeError(
                                f"Decompression failed for chunk at offset {chunk_off} "
                                f"in {entry.name!r}: {exc}"
                            ) from exc
                    if len(chunk_raw) != chunk_ds:
                        raise RuntimeError(
                            f"Decompressed size mismatch for chunk at offset {chunk_off} "
                            f"in {entry.name!r}: expected {chunk_ds}, got {len(chunk_raw)}"
                        )
                    parts.append(chunk_raw)
                raw = b"".join(parts)
            else:
                raw = f.read(entry.compression.packed_size)
                if compression_method == CompressionMethod.LZ4:
                    raw = _decompress_lz4(raw, entry.compression.unpacked_size, entry)
                elif compression_method == CompressionMethod.LZ4F:
                    raw = _decompress_lz4f(raw, entry.compression.unpacked_size, entry)
                else:
                    try:
                        raw = zlib.decompress(raw)
                    except zlib.error as exc:
                        raise RuntimeError(
                            f"Decompression failed for {entry.name!r}: {exc}"
                        ) from exc
            if len(raw) != entry.compression.unpacked_size:
                raise RuntimeError(
                    f"Decompressed size mismatch for {entry.name!r}: "
                    f"expected {entry.compression.unpacked_size}, got {len(raw)}"
                )
        else:
            # Determine if this archive uses embedded file names
            # Reference: wbBSArchive.pas:2391 (FO3/SSE only) — TES5Edit@76d9d226
            # When EMBEDNAME is set, data format is:
            #   [1-byte name_len][name_len bytes name][4-byte unpacked size][zlib data]
            # When EMBEDNAME is not set, data format is:
            #   [4-byte unpacked size][zlib data]
            # EMBEDNAME is only used for FO3/SSE decompression, not TES4.
            # Mirrors wbBSArchive.pas:2391 — TES5Edit@76d9d226
            has_embedded_name = (
                archive_flags & 0x0100 != 0 and  # ARCHIVE_EMBEDNAME
                entry.name_hash != 0 and  # Has a name
                archive_fmt in (ArchiveFormat.FO3, ArchiveFormat.SSE)  # FO3/SSE only
            )

            if has_embedded_name:
                # Read embedded file name (1-byte length prefix + name bytes)
                nlen_byte = f.read(1)
                if not nlen_byte:
                    raise RuntimeError(
                        f"Embedded name missing for {entry.name!r}"
                    )
                nlen = nlen_byte[0]
                name_data = f.read(nlen)
                if len(name_data) < nlen:
                    raise RuntimeError(
                        f"Embedded name truncated for {entry.name!r}"
                    )

                # Read 4-byte unpacked size prefix
                size_prefix = f.read(4)
                if len(size_prefix) < 4:
                    raise RuntimeError(
                        f"Compressed data missing for {entry.name!r}"
                    )
                expected_size = struct.unpack("<I", size_prefix)[0]

                # Compressed data size = packed_size - name_len - 1 - 4
                comp_size = entry.compression.packed_size - nlen - 1 - 4
            else:
                # No embedded name: data starts with 4-byte unpacked size
                size_prefix = f.read(4)
                if len(size_prefix) < 4:
                    raise RuntimeError(
                        f"Compressed data missing for {entry.name!r}"
                    )
                expected_size = struct.unpack("<I", size_prefix)[0]
                comp_size = entry.compression.packed_size - 4

            if comp_size < 0:
                raise RuntimeError(
                    f"Compressed data missing for {entry.name!r}"
                )
            raw = f.read(comp_size)
            if not raw:
                # No zlib data after prefix — empty compressed file
                return b""

            # Dispatch decompression based on archive format's compression method.
            # Defaults mirror cArchiveCompressionTypes from wbBSArchive.pas:194-204 — TES5Edit@76d9d226
            #   TES3/TES4=none, FO3/TES5/FO4=zlib, SSE=LZ4F, SF=zlib(default)/lz4(v3)
            if compression_method is None:
                compression_method = archive_fmt.default_compression() if archive_fmt else CompressionMethod.ZLIB

            if compression_method == CompressionMethod.LZ4F:
                raw = _decompress_lz4f(raw, expected_size, entry)
            elif compression_method == CompressionMethod.LZ4:
                raw = _decompress_lz4(raw, expected_size, entry)
            else:
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    # Some vanilla archives (e.g. Skyrim - Meshes.bsa) have zlib
                    # streams missing their Adler-32 checksum trailer. Fall back
                    # to raw deflate decompression, matching BSArch fix ad8c249b.
                    raw = _decompress_with_trailer_fallback(raw, expected_size, entry)
            if len(raw) != expected_size:
                raise RuntimeError(
                    f"Decompressed size mismatch for {entry.name!r}: "
                    f"expected {expected_size}, got {len(raw)}"
                )
    else:
        # Re-seek in case compressed path changed position
        f.seek(seek_pos)
        raw = f.read(entry.compression.unpacked_size)

    # BA2 DDS files: prepend DDS header + DX10 extra header so output matches BSArch
    # The DX10 header is placed at offset 124 (inside the 128-byte DDS header),
    # not after it. This matches BSArch's output.
    if is_ba2 and entry.is_dx10:
        header = bytearray(_make_dds_header(
            entry.width, entry.height, entry.mip_count, entry.dds_format,
            entry.is_cubemap, entry.compression.unpacked_size,
        ))
        dx10_header = _make_dx10_header(entry.dds_format, entry.is_cubemap)
        # Overwrite bytes 124-143 with DX10 header
        header[124:144] = dx10_header
        raw = bytes(header) + raw

    return raw


def compute_data_start(f: BinaryIO, archive: BSAArchive) -> int:
    """Compute the byte offset where file data begins in the archive.

    TES3 uses relative offsets (from data_start); TES4+ uses absolute offsets.
    Mirrors wbBSArchive.pas:2388-2440 — TES5Edit@76d9d226.
    """
    if archive.fmt == ArchiveFormat.TES3:
        return 0

    # TES4+ (Oblivion, FO3, Skyrim, SSE): offsets are absolute
    return 0


def find_entry(archive: BSAArchive, name: str) -> Optional[BSAFileEntry]:
    """Find a file entry by name (case-insensitive, slash-normalized)."""
    name_norm = name.lower().replace("/", chr(92)).lstrip(chr(92))
    for f in archive.files:
        fn = f.name.lower().replace("/", chr(92)).lstrip(chr(92))
        if fn == name_norm:
            return f
    return None
