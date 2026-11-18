# BSA archive writer — layout computation
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

import struct
import zlib
from pathlib import PureWindowsPath
from typing import BinaryIO

from logic.bsa import ARCHIVE_COMPRESS, ArchiveFormat, BSAFileEntry, CompressionFlag, detect_flags


def compute_layout(
    entries: list[BSAFileEntry],
    data: dict[int, bytes],
    compress: bool,
) -> tuple[int, int, int, int, int, list[int], list[BSAFileEntry], list[tuple[int, list[BSAFileEntry]]]]:
    """Compute the layout for a BSA archive and return all layout components."""

    # Sort entries by directory hash, then name hash (matching BSArch)
    entries = sorted(entries, key=lambda e: (e.directory_hash, e.name_hash))

    # Recompute compression flags (immutable dataclass requires new objects)
    final_entries = []
    for entry in entries:
        raw = data[id(entry)]
        if compress:
            compressed = zlib.compress(raw, -1)
            new_entry = BSAFileEntry(
                name=entry.name,
                directory_hash=entry.directory_hash,
                name_hash=entry.name_hash,
                compression=CompressionFlag(compressed=True, unpacked_size=len(compressed)),
                offset=entry.offset,
            )
            final_entries.append(new_entry)
        else:
            new_entry = BSAFileEntry(
                name=entry.name,
                directory_hash=entry.directory_hash,
                name_hash=entry.name_hash,
                compression=CompressionFlag(compressed=False, unpacked_size=len(raw)),
                offset=entry.offset,
            )
            final_entries.append(new_entry)

    entries = final_entries

    # Gather folders
    folder_set: dict[int, list[BSAFileEntry]] = {}
    for entry in entries:
        folder_set.setdefault(entry.directory_hash, []).append(entry)
    folders = sorted(folder_set.items())

    num_folders = len(folders)
    num_files = len(entries)

    # Compute folder name entries
    folder_name_entries: list[tuple[str, int]] = []
    for dh, flist in folders:
        name = ""
        if flist:
            name = "\\".join(PureWindowsPath(flist[0].name).parts[:-1])
        encoded = name.encode("ascii", errors="replace")
        folder_name_entries.append((name, 1 + len(encoded)))

    total_folder_names = sum(s for _, s in folder_name_entries)
    total_file_names = sum(1 + len(PureWindowsPath(e.name).name.encode("ascii", errors="replace")) for e in entries)

    # SSE folder records are 24B (16B + 2×4B padding)
    folder_record_size = 24 if num_folders > 0 else 0

    # Layout
    header_size = 36
    folder_records_size = num_folders * folder_record_size
    # Mixed blob = folder count (length prefixes) + folder names + file records
    mixed_blob_size = num_folders + total_folder_names + num_files * 16
    names_blob_size = total_file_names
    data_start = header_size + folder_records_size + mixed_blob_size + names_blob_size

    # Compute file data offsets — absolute (relative to archive start)
    file_offsets: list[int] = []
    pos = data_start
    for entry in entries:
        file_offsets.append(pos)
        d = data[id(entry)]
        pos += len(d)
        pad = (4 - len(d) % 4) % 4
        pos += pad

    return (
        header_size,
        folder_records_size,
        mixed_blob_size,
        names_blob_size,
        data_start,
        file_offsets,
        entries,
        folders,
    )


def write_header(
    f: BinaryIO,
    fmt: ArchiveFormat,
    num_folders: int,
    num_files: int,
    total_folder_names: int,
    total_file_names: int,
    file_flags: int,
    compress: bool,
    entries: list[BSAFileEntry] | None = None,
) -> None:
    """Write the BSA archive header."""
    version = int(fmt)
    # Auto-detect archive flags from file names if not provided
    if entries is not None:
        names = [e.name for e in entries]
        archive_flags, _ = detect_flags(int(fmt), names, compress)
    else:
        archive_flags = ARCHIVE_COMPRESS if compress else 0
        # Ensure base flags are always present
        from logic.bsa.constants import ARCHIVE_PATHNAMES, ARCHIVE_FILENAMES
        archive_flags |= ARCHIVE_PATHNAMES | ARCHIVE_FILENAMES

    f.write(b"BSA\x00")
    f.write(struct.pack("<I", version))
    f.write(struct.pack("<I", 36))  # folders_offset
    f.write(struct.pack("<I", archive_flags))
    f.write(struct.pack("<I", num_folders))
    f.write(struct.pack("<I", num_files))
    f.write(struct.pack("<I", total_folder_names))
    f.write(struct.pack("<I", total_file_names))
    f.write(struct.pack("<I", file_flags))


def write_folder_records(f: BinaryIO, folders: list[tuple[int, list[BSAFileEntry]]]) -> None:
    """Write folder records (16 bytes each, 24 for SSE)."""
    for dh, flist in folders:
        f.write(struct.pack("<Q", dh))
        f.write(struct.pack("<I", len(flist)))
        f.write(struct.pack("<I", 0))  # placeholder offset
        # SSE: 2 × 4B padding
        if len(folders) > 0:
            f.write(b"\x00\x00\x00\x00\x00\x00\x00\x00")


def write_mixed_blob(
    f: BinaryIO,
    folders: list[tuple[int, list[BSAFileEntry]]],
    entries: list[BSAFileEntry],
    file_offsets: list[int],
    archive_compressed: bool = False,
) -> None:
    """Write the mixed blob (folder names interleaved with file records)."""
    entry_idx = 0
    for idx, (dh, flist) in enumerate(folders):
        name = "\\".join(PureWindowsPath(flist[0].name).parts[:-1]) if flist else ""
        encoded = name.encode("ascii", errors="replace")
        f.write(struct.pack("B", len(encoded) + 1))  # nlen includes null
        f.write(encoded)
        f.write(b"\x00")

        # Write file records for this folder
        for _ in flist:
            entry = entries[entry_idx]
            f.write(struct.pack("<Q", entry.name_hash))
            f.write(struct.pack("<I", entry.compression.to_size_flags(archive_compressed=archive_compressed)))
            f.write(struct.pack("<I", file_offsets[entry_idx]))
            entry_idx += 1


def write_file_names(f: BinaryIO, entries: list[BSAFileEntry]) -> None:
    """Write the file names blob (null-terminated names only)."""
    for entry in entries:
        filename = PureWindowsPath(entry.name).name
        encoded = filename.encode("ascii", errors="replace")
        f.write(encoded)
        f.write(b"\x00")
