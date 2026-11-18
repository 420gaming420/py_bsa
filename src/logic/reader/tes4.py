# BSA archive reader — TES4+ (Oblivion / Fallout / Skyrim) parsing
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

import struct
from typing import BinaryIO

from logic.bsa import ArchiveFormat, BSAFileEntry, CompressionFlag


def _read_tes4(f: BinaryIO) -> object:
    """Parse a TES4+ BSA archive (Oblivion, Fallout 3/NV, Skyrim)."""
    version = struct.unpack("<I", f.read(4))[0]
    folders_offset = struct.unpack("<I", f.read(4))[0]
    flags = struct.unpack("<I", f.read(4))[0]
    folder_count = struct.unpack("<I", f.read(4))[0]
    file_count = struct.unpack("<I", f.read(4))[0]
    folder_names_len = struct.unpack("<I", f.read(4))[0]
    file_names_len = struct.unpack("<I", f.read(4))[0]
    file_flags = struct.unpack("<I", f.read(4))[0]

    fmt = ArchiveFormat.from_version(version)
    archive_compressed = bool(flags & 0x00000004)
    has_names = file_names_len > 0

    # Inverted compression flag logic (wbBSArchive.pas:1543) — TES5Edit@76d9d226
    # compressed when exactly one of archive-level or file-level COMPRESS flag is set
    FILE_SIZE_COMPRESS = 0x40000000

    # Determine folder record size: SSE (v105) has 24B records (16B + 2×4B padding)
    if fmt == ArchiveFormat.SSE:
        folder_record_size = 24
    else:
        folder_record_size = 16

    # --- Folder records ---
    f.seek(folders_offset)
    folder_records = []
    for _ in range(folder_count):
        dir_hash = struct.unpack("<Q", f.read(8))[0]
        num_files = struct.unpack("<I", f.read(4))[0]
        offset = struct.unpack("<I", f.read(4))[0]
        # SSE has 2 extra 4B padding fields
        if folder_record_size == 24:
            f.read(8)  # skip 2 × 4B padding
        folder_records.append((dir_hash, num_files, offset))

    # --- Mixed blob: folder names + file records (parse dynamically) ---
    blob_start = folders_offset + folder_count * folder_record_size
    f.seek(blob_start)
    blob = f.read(folder_names_len + file_count * 16 + folder_count + 100)

    # --- Parse blob dynamically to find actual end ---
    bp = 0
    files_read = 0

    for dir_hash, num_files, _off in folder_records:
        if bp >= len(blob) or files_read >= file_count:
            break
        nlen = blob[bp]
        bp += 1
        if nlen > 0:
            bp += nlen - 1
            bp += 1  # skip null terminator
        # else: nlen=0, no name, no null - file record starts immediately

        for _ in range(num_files):
            if bp + 16 > len(blob) or files_read >= file_count:
                break
            bp += 16
            files_read += 1

    # Now read file names at the correct offset
    names_start = blob_start + bp
    f.seek(names_start)
    names_data = f.read(file_names_len)

    # --- Re-parse with correct names ---
    bp = 0
    files: list[BSAFileEntry] = []
    name_idx = 0
    folder_names_list: list[str] = []
    files_read = 0
    folder_idx = 0

    for dir_hash, num_files, _off in folder_records:
        if bp >= len(blob) or files_read >= file_count:
            break
        nlen = blob[bp]
        bp += 1
        if nlen > 0:
            folder_name = blob[bp:bp + nlen - 1].decode("latin-1")
            bp += nlen - 1
            bp += 1  # skip null terminator
        else:
            folder_name = ""
        folder_names_list.append(folder_name)

        for _ in range(num_files):
            if bp + 16 > len(blob) or files_read >= file_count:
                break
            file_hash = struct.unpack("<Q", blob[bp:bp + 8])[0]
            size_flags = struct.unpack("<I", blob[bp + 8:bp + 12])[0]
            file_offset = struct.unpack("<I", blob[bp + 12:bp + 16])[0]
            bp += 16
            files_read += 1

            file_name = ""
            if has_names and name_idx < len(names_data):
                nend = names_data.find(b"\x00", name_idx)
                if nend == -1:
                    nend = len(names_data)
                file_name = names_data[name_idx:nend].decode("latin-1")
                name_idx = nend + 1

            folder_str = folder_names_list[folder_idx]
            # BSArch always prepends backslash when in a folder (even empty root folder)
            if file_name:
                if folder_str:
                    full_name = folder_str + chr(92) + file_name
                else:
                    full_name = chr(92) + file_name
            elif folder_str:
                full_name = folder_str
            else:
                full_name = ""

            # Inverted flag: compressed if exactly one of archive/file flag is set
            file_compressed = bool(archive_compressed) ^ bool(size_flags & FILE_SIZE_COMPRESS)
            file_size = size_flags & ~FILE_SIZE_COMPRESS
            # For compressed files, the size field is the TOTAL data size
            # (4-byte unpacked-size prefix + compressed data).
            # The actual unpacked size is stored as a 4-byte prefix in the data.
            # We store file_size as packed_size; read_file() reads the prefix
            # to determine the actual unpacked size.
            # For uncompressed files, file_size IS the unpacked size.
            # Mirrors wbBSArchive.pas:1543-1550 — TES5Edit@76d9d226
            comp = CompressionFlag(
                compressed=file_compressed,
                unpacked_size=file_size if not file_compressed else 0,
                packed_size=file_size,
            )
            files.append(
                BSAFileEntry(
                    name=full_name,
                    directory_hash=dir_hash,
                    name_hash=file_hash,
                    compression=comp,
                    offset=file_offset,
                    ext_hash=0,
                )
            )
        folder_idx += 1

    from logic.bsa import BSAArchive

    return BSAArchive(
        fmt=fmt,
        flags=flags,
        file_flags=file_flags,
        files=files,
    )


# BSArch flag descriptions (archive flags, file flags)
# Matches wbBSArchive.pas cArchiveFlagNames and cFileFlagNames — TES5Edit@76d9d226
_ARCHIVE_FLAG_NAMES = [
    "Include Directory Names", "Include File Names", "Compressed",
    "Retain Directory Names", "Retain File Names",
    "Retain File Name Offsets", "XBox 360 Archive",
    "Retain Strings During Startup",
    "Embedded File Names", "XMem Codec",
]
_FILE_FLAG_NAMES = [
    "Meshes", "Textures", "Menus", "Sounds",
    "Voices", "Shaders", "Trees", "Fonts",
    "Misc",
]


def _format_flags(archive_flags: int, file_flags: int) -> list[str]:
    """Format archive and file flags in BSArch style (from wbBSArchive.pas) — TES5Edit@76d9d226."""
    lines = []
    lines.append(
        f" Archive Flags: 0x{archive_flags:04X}              File Flags: 0x{file_flags:04X}"
    )
    for i, arch_name in enumerate(_ARCHIVE_FLAG_NAMES):
        arch_set = bool(archive_flags >> i & 1)
        # Build left column: variable leading spaces + (* or space) + name
        prefix = " " * (16 if len(arch_name) <= 10 else 17)
        s = prefix + ("*" if arch_set else " ") + arch_name
        # Build right column: right-aligned at column 49
        if i < len(_FILE_FLAG_NAMES):
            file_set = bool(file_flags >> i & 1)
            s2 = ("*" if file_set else "") + _FILE_FLAG_NAMES[i]
            # Pad so right column starts at position 49
            lines.append(s + " " * (49 - len(s)) + s2)
        else:
            # XMem Codec: left column only, padded to same width
            lines.append(s + " " * (49 - len(s)) + " ")
    return lines


def dump_tes4(archive: object) -> str:
    """Dump a TES4 archive in BSArch-compatible format."""
    # Map version to BSArch format name
    version_map = {103: "Oblivion", 104: "Skyrim LE, New Vegas, Fallout 3", 105: "SkyrimSE"}
    fmt_name = version_map.get(archive.fmt.value, archive.fmt.name)
    version = {103: 0x67, 104: 0x68, 105: 0x69}.get(archive.fmt.value, 0)

    lines = []
    lines.append(f"        Format: {fmt_name}")
    lines.append(f"       Version: 0x{version:02X}")
    lines.append(f"         Files: {len(archive.files)}")
    lines.extend(_format_flags(archive.flags, archive.file_flags))
    lines.append("")
    for entry in archive.files:
        lines.append(entry.name)
        if entry.compression.compressed:
            lines.append(
                f"  DirHash: {entry.directory_hash:016X}  "
                f"NameHash: {entry.name_hash:016X}  "
                f"PackedSize: {entry.compression.packed_size}  "
                f"Offset: {entry.offset}"
            )
        else:
            lines.append(
                f"  DirHash: {entry.directory_hash:016X}  "
                f"NameHash: {entry.name_hash:016X}  "
                f"Size: {entry.compression.unpacked_size}  "
                f"Offset: {entry.offset}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()
