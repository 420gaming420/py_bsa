# BSA archive reader — TES3 (Morrowind) parsing
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

import struct
from typing import BinaryIO

from logic.bsa import BSAFileEntry, CompressionFlag


def _read_tes3(f: BinaryIO) -> object:
    """Parse a TES3 (Morrowind) BSA archive."""
    hash_offset = struct.unpack("<I", f.read(4))[0]
    file_count = struct.unpack("<I", f.read(4))[0]

    # File records (size, offset) — offset is relative to data start
    file_records = []
    for _ in range(file_count):
        size = struct.unpack("<I", f.read(4))[0]
        offset = struct.unpack("<I", f.read(4))[0]
        file_records.append((size, offset))

    # Name offsets
    name_offsets = []
    for _ in range(file_count):
        name_offsets.append(struct.unpack("<I", f.read(4))[0])

    # Hash records: hash_offset points to the hash block header, data starts at +12
    hash_start = hash_offset + 12
    f.seek(hash_start)
    hashes = []
    for _ in range(file_count):
        h = struct.unpack("<Q", f.read(8))[0]
        # Hash is stored as lo, hi in little-endian (same as uint64 LE)
        hashes.append(h)

    # Names: stored after name_offsets block
    # names_start = header(12) + file_records(8*fc) + name_offsets(4*fc) = 12 + 12*fc
    names_block_start = 12 + file_count * 12
    f.seek(names_block_start)
    if name_offsets:
        max_off = max(name_offsets)
        names_data = f.read(max_off + 1024)
    else:
        names_data = b""

    from logic.bsa import ArchiveFormat, BSAArchive

    files: list[BSAFileEntry] = []
    for i in range(file_count):
        size, offset = file_records[i]
        name_off = name_offsets[i]
        name = ""
        if name_off < len(names_data):
            end = names_data.find(b"\x00", name_off)
            name = names_data[name_off:end].decode("ascii", errors="replace")

        files.append(
            BSAFileEntry(
                name=name,
                directory_hash=0,
                name_hash=hashes[i],
                compression=CompressionFlag(compressed=False, unpacked_size=size),
                offset=offset,
            )
        )

    # Compute data_start: hashes start at hash_offset + 12, file data after hashes
    # C++ formula: hash_offset + header_size + file_count * hash_size
    # where header_size=12, hash_size=8
    data_start = hash_offset + 12 + file_count * 8
    return BSAArchive(fmt=ArchiveFormat.TES3, flags=0, file_flags=0, files=files,
                      data_start=data_start)


def dump_tes3(archive: object) -> str:
    """Dump a TES3 archive in BSArch-compatible format."""
    lines = []
    lines.append("        Format: Morrowind")
    lines.append(f"         Files: {len(archive.files)}")
    lines.append("")
    for entry in archive.files:
        h = entry.name_hash
        lines.append(entry.name)
        lines.append(
            f"  Hash: {h:016X}  "
            f"Size: {entry.compression.unpacked_size}  "
            f"Offset: {entry.offset}"
        )
        lines.append("")
    return "\n".join(lines).rstrip()
