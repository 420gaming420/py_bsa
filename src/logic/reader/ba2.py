# BA2 archive reader — Fallout 4 / Starfield BA2 format
# References: bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0)

from __future__ import annotations

import struct
from typing import BinaryIO

from logic.bsa import ArchiveFormat, BSAFileEntry, CompressionFlag, CompressionMethod
from logic.bsa.constants import COMPRESSION_METHOD_LZ4
from logic.hasher import BA2Hash
from logic.reader.tes4 import _format_flags


def _read_ba2(f: BinaryIO) -> object:
    """Parse a BA2 (Fallout 4 / Starfield) archive."""
    # Header: version(4) + format(4) + fileCount(4) + stringTableOffset(8)
    # Magic was already consumed by the dispatcher in core.py
    version = struct.unpack("<I", f.read(4))[0]
    fmt_code = struct.unpack("<I", f.read(4))[0]
    file_count = struct.unpack("<I", f.read(4))[0]
    string_table_offset = struct.unpack("<Q", f.read(8))[0]

    # On-disk format is a 4-char ASCII code read little-endian:
    # "GNRL" (0x4C524E47) = general format, "DX10" (0x30315844) = DDS/DX10 format
    # "GNMF" (0x464D4E47) = PS DDS format (Starfield only)
    is_dx10 = fmt_code == 0x30315844  # "DX10"
    is_gnmf = fmt_code == 0x464D4E47  # "GNMF"
    is_sf = version in (2, 3)

    # v2 and v3 have extra fields
    if version in (2, 3):
        f.read(8)  # 8-byte padding field (UInt64 = 1)
    if version == 3:
        comp_method_byte = struct.unpack("<I", f.read(4))[0]
        # 0=zlib, 3=lz4 (COMPRESSION_METHOD_* from wbBSArchive.pas — TES5Edit@76d9d226)
        is_lz4 = (comp_method_byte == COMPRESSION_METHOD_LZ4)
    else:
        is_lz4 = False

    # Layout constants:
    # GNRL file record: 4+4+4 (hashes) + 1 (mod) + 1 (count) + 2 (hdrsz) = 16
    # DX10 file record: 16 + 8 (DX header) = 24
    # GNMF file record: 16 + 32 (PS header) = 48
    # SF fixed records: 36 bytes (16 base + 20 GNRL chunk) for general format
    # SF DDS: variable (16/24/48) like FO4
    if is_sf and not is_dx10 and not is_gnmf:
        # Starfield general: fixed 36-byte records (16 base + embedded 20-byte GNRL chunk)
        file_record_size = 36
    else:
        file_record_size = 48 if is_gnmf else (24 if is_dx10 else 16)
    chunk_header_size = 48 if is_gnmf else (24 if is_dx10 else 20)

    # Header size
    header_size = 24  # 4+4+4+4+8
    if version in (2, 3):
        header_size += 12

    # Data starts after header + file records
    data_start = header_size + file_count * file_record_size

    # Read file records and chunk headers sequentially
    files: list[BSAFileEntry] = []
    chunk_info: list[list[tuple[int, int, int, int, int]]] = []
    file_hashes: list[int] = []
    ext_hashes: list[int] = []
    dir_hashes: list[int] = []
    dx_headers: list[dict] = []

    for i in range(file_count):
        file_hash = struct.unpack("<I", f.read(4))[0]
        ext_hash = struct.unpack("<I", f.read(4))[0]
        dir_hash = struct.unpack("<I", f.read(4))[0]
        mod_index = struct.unpack("B", f.read(1))[0]
        chunk_count = struct.unpack("B", f.read(1))[0]
        chunk_hdr_sz = struct.unpack("<H", f.read(2))[0]

        # SF general format: embedded GNRL chunk header in the file record
        if is_sf and not is_dx10 and not is_gnmf:
            data_offset = struct.unpack("<Q", f.read(8))[0]
            comp_size = struct.unpack("<I", f.read(4))[0]
            decomp_size = struct.unpack("<I", f.read(4))[0]
            sentinel = struct.unpack("<I", f.read(4))[0]
            if sentinel != 0xBAADF00D:
                raise ValueError(
                    f"Invalid chunk sentinel at offset {f.tell() - 4}: 0x{sentinel:08X}"
                )
            chunks = [(data_offset, comp_size, decomp_size, 0, 0)]
            width = height = mip_count = dds_fmt = 0
            dx_headers.append({"width": 0, "height": 0, "mip_count": 0, "format": 0, "flags": 0})
        else:
            # DX file header (8 bytes): width(2), height(2), mip_count(1), format(1), flags(1), tile_mode(1)
            # GNMF file header (32 bytes): PS-specific DDS format
            width = 0
            height = 0
            mip_count = 0
            dds_fmt = 0
            flags = 0
            if is_dx10:
                height = struct.unpack("<H", f.read(2))[0]
                width = struct.unpack("<H", f.read(2))[0]
                mip_count = struct.unpack("B", f.read(1))[0]
                dds_fmt = struct.unpack("B", f.read(1))[0]
                flags = struct.unpack("B", f.read(1))[0]
                f.read(1)  # tile_mode
                dx_headers.append({
                    "width": width, "height": height,
                    "mip_count": mip_count, "format": dds_fmt,
                    "flags": flags,
                })
            elif is_gnmf:
                f.read(32)  # GNMF: 32-byte PS header
                dx_headers.append({
                    "width": 0, "height": 0,
                    "mip_count": 0, "format": 0,
                    "flags": 0,
                })
            else:
                dx_headers.append({
                    "width": 0, "height": 0,
                    "mip_count": 0, "format": 0,
                    "flags": 0,
                })

            # Read chunk headers
            chunks = []
            for _ in range(chunk_count):
                data_offset = struct.unpack("<Q", f.read(8))[0]
                comp_size = struct.unpack("<I", f.read(4))[0]
                decomp_size = struct.unpack("<I", f.read(4))[0]
                if is_dx10:
                    mip_first = struct.unpack("<H", f.read(2))[0]
                    mip_last = struct.unpack("<H", f.read(2))[0]
                else:
                    mip_first = 0
                    mip_last = 0
                sentinel = struct.unpack("<I", f.read(4))[0]
                if sentinel != 0xBAADF00D:
                    raise ValueError(
                        f"Invalid chunk sentinel at offset {f.tell() - 4}: 0x{sentinel:08X}"
                    )
                chunks.append((data_offset, comp_size, decomp_size, mip_first, mip_last))

        chunk_info.append(chunks)
        file_hashes.append(file_hash)
        ext_hashes.append(ext_hash)
        dir_hashes.append(dir_hash)

    # Read string table for names
    names: list[str] = []
    if string_table_offset != 0:
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(string_table_offset)
        str_data = f.read(file_size - string_table_offset)

        pos = 0
        for _ in range(file_count):
            if pos + 2 > len(str_data):
                names.append("")
                break
            str_len = struct.unpack("<H", str_data[pos:pos+2])[0]
            pos += 2
            if pos + str_len > len(str_data):
                names.append("")
                break
            name = str_data[pos:pos+str_len].decode("latin-1")
            name = name.replace("/", "\\")
            names.append(name)
            pos += str_len

    # Build file entries
    for i in range(file_count):
        entry_name = names[i] if i < len(names) else ""
        chunks = chunk_info[i]
        file_hash = file_hashes[i]
        ext_hash = ext_hashes[i]
        dir_hash = dir_hashes[i]

        total_comp = sum(cs for _, cs, _, _, _ in chunks if cs > 0)
        total_decomp = sum(ds for _, _, ds, _, _ in chunks)
        is_compressed = any(cs > 0 for _, cs, _, _, _ in chunks)

        file_offset = chunks[0][0] if chunks else data_start

        width = 0
        height = 0
        mip_count = 0
        dds_fmt = 0
        is_cubemap = False
        if is_dx10 and i < len(dx_headers):
            dh = dx_headers[i]
            width = dh["width"]
            height = dh["height"]
            mip_count = dh["mip_count"]
            dds_fmt = dh["format"]
            is_cubemap = dh["flags"] & 1

        entry = BSAFileEntry(
            name=entry_name,
            directory_hash=dir_hash,
            name_hash=file_hash,
            ext_hash=ext_hash,
            compression=CompressionFlag(
                compressed=is_compressed,
                unpacked_size=total_decomp,
                packed_size=total_comp,
            ),
            offset=file_offset,
            is_dx10=is_dx10,
            width=width,
            height=height,
            mip_count=mip_count,
            dds_format=dds_fmt,
            is_cubemap=is_cubemap,
            chunks=list(chunks) if is_dx10 else None,
        )
        files.append(entry)

    from logic.bsa import BSAArchive

    if version in (2, 3):
        fmt = ArchiveFormat.SF_DDS if is_dx10 else ArchiveFormat.SF
    else:
        fmt = ArchiveFormat.FO4_DDS if is_dx10 else ArchiveFormat.FO4

    return BSAArchive(
        fmt=fmt,
        flags=0,
        file_flags=0,
        files=files,
        _compression_method=CompressionMethod.LZ4 if is_lz4 else CompressionMethod.ZLIB,
    )


def _ext_from_hash(ext_hash: int) -> str:
    """Decode a 4-byte little-endian extension hash to a string."""
    return ext_hash.to_bytes(4, "little").decode("ascii", errors="replace").rstrip("\x00")


def _dds_format_name(fmt: int) -> str:
    """Map a format byte to BSArch's display name (from wbDataFormatMisc.pas)."""
    mapping = {
        70: "BC1_TYPELESS",
        71: "BC1_UNORM",
        72: "BC1_UNORM_SRGB",
        73: "BC1_SNORM",
        74: "BC2_TYPELESS",
        75: "BC2_UNORM",
        76: "BC2_UNORM_SRGB",
        77: "BC3_UNORM",
        78: "BC3_UNORM_SRGB",
        79: "BC3_SNORM",
        80: "BC4_TYPELESS",
        81: "BC4_UNORM",
        82: "BC4_UNORM_SRGB",
        83: "BC5_UNORM",
        84: "BC5_UNORM_SRGB",
        85: "BC5_SNORM",
        86: "BC6H_TYPELESS",
        87: "BC6H_UF16",
        88: "BC6H_SF16",
        89: "BC7_TYPELESS",
        90: "BC7_UNORM",
        91: "BC7_UNORM_SRGB",
        92: "BC7_SNORM",
    }
    return mapping.get(fmt, f"UNKNOWN_{fmt}")


def dump_ba2(archive: object) -> str:
    """Dump a BA2 archive in BSArch-compatible format."""
    lines = []
    if archive.fmt == ArchiveFormat.FO4_DDS:
        lines.append("        Format: Fallout 4 DDS")
    elif archive.fmt == ArchiveFormat.FO4:
        lines.append("        Format: Fallout 4")
    elif archive.fmt == ArchiveFormat.SF_DDS:
        lines.append("        Format: Starfield DDS")
    else:
        lines.append("        Format: Starfield")
    lines.append(f"         Files: {len(archive.files)}")
    lines.append("")
    for entry in archive.files:
        ext = _ext_from_hash(entry.ext_hash)
        lines.append(entry.name)
        if entry.is_dx10:
            lines.append(
                f"  DirHash: {entry.directory_hash:08X}  "
                f"NameHash: {entry.name_hash:08X}  "
                f"Ext: {ext}"
            )
            cubemap_str = "Yes" if entry.is_cubemap else "No"
            lines.append(
                f"  Width: {entry.width}  Height: {entry.height}  "
                f"CubeMap: {cubemap_str}  Format: {_dds_format_name(entry.dds_format)}"
            )
            if entry.chunks:
                for off, cs, ds, mf, ml in entry.chunks:
                    lines.append(
                        f"    MipMaps {mf:02d}-{ml:02d}  "
                        f"Size: {ds:>8}  PackedSize: {cs:>8}  Offset: {off}"
                    )
        else:
            lines.append(
                f"  DirHash: {entry.directory_hash:08X}  "
                f"NameHash: {entry.name_hash:08X}  "
                f"Ext: {ext}  "
                f"Size: {entry.compression.unpacked_size}  "
                f"PackedSize: {entry.compression.packed_size}  "
                f"Offset: {entry.offset}"
            )
    return "\n".join(lines)
