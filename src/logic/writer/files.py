# BSA archive writer — file adding and data management
# References: BSAopt@91d7bcf (github.com/Ethatron/bsaopt, MPL 1.1/LGPL 3.0),
#             TES5Edit@76d9d226 (github.com/TES5Edit/TES5Edit, MPL 2.0),
#             bsa@b6ab3c8 (github.com/Ryan-rsm-McKenzie/bsa, MIT)

from __future__ import annotations

import struct
import zlib
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

from logic.bsa import ArchiveFormat, BSAFileEntry, CompressionFlag, CompressionMethod, detect_flags
from logic.hasher import TES3Hash, TES4Hash, BA2Hash


class BSAWriter:
    """Writes BSA archives to disk."""

    def __init__(
        self,
        fmt: ArchiveFormat = ArchiveFormat.FO3,
        file_flags: int = 0,
        compress: bool = False,
        compression_level: int = -1,
    ) -> None:
        self.fmt = fmt
        self._file_flags = file_flags
        self._archive_flags = 0
        self.compress = compress
        self.compression_level = compression_level
        self._entries: list[BSAFileEntry] = []
        self._data: dict[int, bytes] = {}

    @property
    def file_flags(self) -> int:
        """File flags — auto-detected from entries if not explicitly set."""
        if self._file_flags != 0:
            return self._file_flags
        names = [e.name for e in self._entries]
        _, ff = detect_flags(int(self.fmt), names, self.compress)
        return ff

    @property
    def archive_flags(self) -> int:
        """Archive flags — auto-detected from entries if not explicitly set."""
        if self._archive_flags != 0:
            return self._archive_flags
        names = [e.name for e in self._entries]
        af, _ = detect_flags(int(self.fmt), names, self.compress)
        return af

    @classmethod
    def for_oblivion(cls) -> "BSAWriter":
        return cls(fmt=ArchiveFormat.TES4)

    @classmethod
    def for_fallout3(cls) -> "BSAWriter":
        return cls(fmt=ArchiveFormat.FO3)

    @classmethod
    def for_new_vegas(cls) -> "BSAWriter":
        return cls(fmt=ArchiveFormat.FO3)

    @classmethod
    def for_skyrim(cls) -> "BSAWriter":
        return cls(fmt=ArchiveFormat.SSE)

    @classmethod
    def for_morrowind(cls) -> "BSAWriter":
        """Create a TES3 (Morrowind) BSA writer."""
        return cls(fmt=ArchiveFormat.TES3)

    @classmethod
    def for_fallout4(cls) -> "BSAWriter":
        """Create a BA2 (Fallout 4) BSA writer."""
        return cls(fmt=ArchiveFormat.FO4)

    @classmethod
    def for_starfield(cls) -> "BSAWriter":
        """Create a BA2 (Starfield) BSA writer."""
        return cls(fmt=ArchiveFormat.SF)

    @classmethod
    def for_starfielddds(cls) -> "BSAWriter":
        """Create a BA2 (Starfield DDS) BSA writer."""
        return cls(fmt=ArchiveFormat.SF_DDS)

    def add_file(self, name: str, data: bytes) -> BSAFileEntry:
        name = name.replace("/", "\\")
        sep = name.rfind("\\")
        if sep >= 0:
            dir_part = name[:sep]
        else:
            dir_part = ""

        if self.fmt == ArchiveFormat.TES3:
            h = TES3Hash.hash(name)
            entry = BSAFileEntry(
                name=name,
                directory_hash=0,
                name_hash=h,
                compression=CompressionFlag(compressed=False, unpacked_size=len(data)),
                offset=0,
            )
        elif self.fmt.is_ba2:
            dir_h, file_h, ext_h = BA2Hash.compute_full_hash(name)
            entry = BSAFileEntry(
                name=name,
                directory_hash=dir_h,
                name_hash=file_h,
                ext_hash=ext_h,
                compression=CompressionFlag(compressed=False, unpacked_size=len(data)),
                offset=0,
            )
        else:
            # TES4-like: use signed hash for TES4 (Oblivion)
            signed = self.fmt.uses_signed_hash
            dir_h = TES4Hash.hash_directory(dir_part, signed=signed)
            file_h = TES4Hash.hash_file(name, signed=signed)
            entry = BSAFileEntry(
                name=name,
                directory_hash=dir_h,
                name_hash=file_h,
                compression=CompressionFlag(compressed=False, unpacked_size=len(data)),
                offset=0,
            )

        self._entries.append(entry)
        self._data[id(entry)] = data
        return entry

    def add_entry(self, entry: BSAFileEntry, data: bytes) -> None:
        self._entries.append(entry)
        self._data[id(entry)] = data

    def save(self, path: Path | str) -> Path:
        p = Path(path)
        with open(p, "wb") as f:
            self._write(f)
        return p

    def save_to(self, stream: BinaryIO) -> None:
        self._write(stream)

    def _write(self, f: BinaryIO) -> None:
        if self.fmt == ArchiveFormat.TES3:
            self._write_tes3(f)
        elif self.fmt.is_ba2:
            self._write_ba2(f)
        else:
            self._write_tes4(f)

    def _write_tes3(self, f: BinaryIO) -> None:
        """Write a TES3 (Morrowind) BSA archive."""
        # BSArch HashSortTES3: sort by low 32 bits first, then high 32 bits
        entries = sorted(self._entries, key=lambda e: (e.name_hash & 0xFFFFFFFF, e.name_hash >> 32))

        # Compute name data
        name_offsets: list[int] = []
        name_data = b""
        for entry in entries:
            name_offsets.append(len(name_data))
            encoded = entry.name.encode("ascii", errors="replace")
            name_data += encoded + b"\x00"

        # Compute file data
        file_data_parts: list[bytes] = []
        for entry in entries:
            raw = self._data[id(entry)]
            if self.compress:
                compressed = zlib.compress(raw, self.compression_level)
                file_data_parts.append(compressed)
            else:
                file_data_parts.append(raw)

        # Hash offset = after header + file records + name offsets + names - 12
        # TES3 format: hash_offset points to last 12 bytes of names;
        # hashes start at hash_offset + 12 = names_end
        header_size = 12  # magic(4) + hashOffset(4) + fileCount(4)
        file_records_size = len(entries) * 8  # size(4) + offset(4)
        name_offsets_size = len(entries) * 4
        hash_offset = header_size + file_records_size + name_offsets_size + len(name_data) - 12
        hash_size = len(entries) * 8
        data_start = hash_offset + 12 + hash_size

        file_sizes = [len(d) for d in file_data_parts]
        # Offsets are relative to data_start
        file_offsets = []
        off = 0
        for sz in file_sizes:
            file_offsets.append(off)
            off += sz

        # --- Write header ---
        f.write(struct.pack("<I", 0x00000100))  # magic
        f.write(struct.pack("<I", hash_offset))
        f.write(struct.pack("<I", len(entries)))

        # --- Write file records (offsets are relative to data_start) ---
        for i, entry in enumerate(entries):
            f.write(struct.pack("<I", file_sizes[i]))
            f.write(struct.pack("<I", file_offsets[i]))

        # --- Write name offsets ---
        for noff in name_offsets:
            f.write(struct.pack("<I", noff))

        # --- Write names ---
        f.write(name_data)

        # --- Write hashes (start at hash_offset + 12 = names_end) ---
        for entry in entries:
            f.write(struct.pack("<Q", entry.name_hash))

        # --- Write file data ---
        for d in file_data_parts:
            f.write(d)

    def _write_tes4(self, f: BinaryIO) -> None:
        """Write a TES4+ BSA archive."""
        # BSArch HashSortTES4: sort by directory hash, then name hash
        entries = sorted(self._entries, key=lambda e: (e.directory_hash, e.name_hash))

        # Prepare: compress if needed
        # SSE defaults to LZ4F; FO3/TES5/FO4 default to zlib; TES3/TES4 don't compress
        # Mirrors TwbCustomBSArchive.DefaultCompression — wbBSArchive.pas:1096, TES5Edit@76d9d226
        default_comp = self.fmt.default_compression()
        use_lz4f = (self.compress and default_comp == CompressionMethod.LZ4F)
        use_lz4 = (self.compress and default_comp == CompressionMethod.LZ4)

        for entry in entries:
            raw = self._data[id(entry)]
            if self.compress:
                if use_lz4f:
                    import lz4.frame as _lz4f
                    compressed = _lz4f.compress(raw, compression_level=self.compression_level)
                elif use_lz4:
                    import lz4.block as _lz4b
                    compressed = _lz4b.compress(raw, compression_level=self.compression_level)
                else:
                    compressed = zlib.compress(raw, self.compression_level)
                # Compressed data includes 4-byte unpacked size prefix (TES4-like)
                prefixed = struct.pack("<I", len(raw)) + compressed
                self._data[id(entry)] = prefixed
                entry.compression = CompressionFlag(compressed=True, unpacked_size=len(prefixed))
            else:
                entry.compression = CompressionFlag(compressed=False, unpacked_size=len(raw))

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
        if self.fmt == ArchiveFormat.SSE:
            folder_record_size = 24
        else:
            folder_record_size = 16

        # Layout
        header_size = 36
        folder_records_size = num_folders * folder_record_size
        mixed_blob_size = num_folders + total_folder_names + num_files * 16
        names_blob_size = total_file_names
        data_start = header_size + folder_records_size + mixed_blob_size + names_blob_size

        # Compute file data offsets — absolute (relative to archive start)
        file_offsets: list[int] = []
        pos = data_start
        for entry in entries:
            file_offsets.append(pos)
            d = self._data[id(entry)]
            pos += len(d)
            pad = (4 - len(d) % 4) % 4
            pos += pad

        # --- Write header ---
        version = int(self.fmt)
        flags = self.archive_flags

        f.write(b"BSA\x00")
        f.write(struct.pack("<I", version))
        f.write(struct.pack("<I", header_size))  # folders_offset
        f.write(struct.pack("<I", flags))
        f.write(struct.pack("<I", num_folders))
        f.write(struct.pack("<I", num_files))
        f.write(struct.pack("<I", total_folder_names))
        f.write(struct.pack("<I", total_file_names))
        f.write(struct.pack("<I", self.file_flags))

        # --- Write folder records ---
        for idx, (dh, flist) in enumerate(folders):
            f.write(struct.pack("<Q", dh))
            f.write(struct.pack("<I", len(flist)))
            f.write(struct.pack("<I", 0))  # placeholder
            # SSE padding
            if folder_record_size == 24:
                f.write(b"\x00\x00\x00\x00\x00\x00\x00\x00")

        # --- Write mixed blob ---
        entry_idx = 0
        for idx, (dh, flist) in enumerate(folders):
            name, sz = folder_name_entries[idx]
            encoded = name.encode("ascii", errors="replace")
            f.write(struct.pack("B", len(encoded) + 1))  # nlen includes null
            f.write(encoded)
            f.write(b"\x00")

            # Write file records for this folder
            for _ in flist:
                entry = entries[entry_idx]
                f.write(struct.pack("<Q", entry.name_hash))
                f.write(struct.pack("<I", entry.compression.to_size_flags(archive_compressed=bool(flags & 0x00000004))))
                f.write(struct.pack("<I", file_offsets[entry_idx]))
                entry_idx += 1

        # --- Write file names ---
        for entry in entries:
            filename = PureWindowsPath(entry.name).name
            encoded = filename.encode("ascii", errors="replace")
            f.write(encoded)
            f.write(b"\x00")

        # --- Write file data ---
        for entry in entries:
            data = self._data[id(entry)]
            pad = (4 - len(data) % 4) % 4
            f.write(data)
            if pad:
                f.write(b"\x00" * pad)

    def _write_ba2(self, f: BinaryIO) -> None:
        """Write a BA2 (Fallout 4 / Starfield) archive.

        Layout (mirrors bsa C++ archive::write) — bsa@b6ab3c8.
          [header][hash(12)+mod(1)+count(1)+hdrsz(2)+chunk_hdr...][all_chunk_data][string_table]
        """
        entries = sorted(self._entries, key=lambda e: (e.directory_hash, e.name_hash))

        # Prepare data
        # SF defaults to zlib; SFv3 (compress=True) uses LZ4 per header CompressionMethod
        # Mirrors wbBSArchive.pas:1559,1589 — TES5Edit@76d9d226
        default_comp = self.fmt.default_compression()
        use_lz4f = (self.compress and default_comp == CompressionMethod.LZ4F)
        use_lz4 = (self.compress and default_comp == CompressionMethod.LZ4)

        for entry in entries:
            raw = self._data[id(entry)]
            if self.compress:
                if use_lz4f:
                    import lz4.frame as _lz4f
                    compressed = _lz4f.compress(raw, compression_level=self.compression_level)
                elif use_lz4:
                    import lz4.block as _lz4b
                    compressed = _lz4b.compress(raw, compression_level=self.compression_level)
                else:
                    compressed = zlib.compress(raw, self.compression_level)
                self._data[id(entry)] = compressed
                entry.compression = CompressionFlag(compressed=True, unpacked_size=len(raw))
            else:
                entry.compression = CompressionFlag(compressed=False, unpacked_size=len(raw))

        file_count = len(entries)
        is_sf = self.fmt in (ArchiveFormat.SF, ArchiveFormat.SF_DDS)
        is_dx10 = self.fmt in (ArchiveFormat.FO4_DDS, ArchiveFormat.SF_DDS)

        # Chunk header sizes (matching bsa C++ constants) — bsa@b6ab3c8
        CHUNK_HDR_GNRL = 20  # offset(8) + comp(4) + decomp(4) + sentinel(4)
        CHUNK_HDR_DX10 = 24  # + start_mip(2) + end_mip(2)

        # Version and format code
        if is_sf:
            version = 3 if self.compress else 2
        else:
            version = 1
        fmt_code = 0x30315844 if is_dx10 else 0x00000001  # DX10 = "DX10", GNRL = 1

        # Header sizes
        # v1: 24 bytes (magic+version+format+fc+strOff)
        # v2: 32 bytes (+ 8-byte UInt64)
        # v3: 36 bytes (+ 4-byte compression format)
        if version == 1:
            header_size = 24
        elif version == 2:
            header_size = 32
        else:
            header_size = 36

        # Compute data offsets: data starts after header + all file records
        # File record size per entry: hash(12) + mod(1) + count(1) + hdrsz(2) + chunks*chunk_hdr
        # Each chunk: CHUNK_HDR_GNRL (20) or CHUNK_HDR_DX10 (24)
        chunk_hdr_size = CHUNK_HDR_DX10 if is_dx10 else CHUNK_HDR_GNRL
        file_record_size = 16 + chunk_hdr_size  # 12+1+1+2 + chunk_hdr

        # Compute per-entry data sizes and offsets
        entry_data_sizes: list[int] = []
        data_offsets: list[int] = []
        pos = header_size + file_count * file_record_size
        for entry in entries:
            ds = len(self._data[id(entry)])
            entry_data_sizes.append(ds)
            data_offsets.append(pos)
            pos += ds

        # String table after all data
        string_table_data = b""
        for entry in entries:
            name_for_table = entry.name.replace("\\", "/")
            encoded = name_for_table.encode("ascii", errors="replace")
            string_table_data += struct.pack("<H", len(encoded)) + encoded

        string_table_offset = pos

        # --- Write header ---
        f.write(b"BTDX")
        f.write(struct.pack("<I", version))
        f.write(struct.pack("<I", fmt_code))
        f.write(struct.pack("<I", file_count))
        f.write(struct.pack("<Q", string_table_offset))
        if version in (2, 3):
            f.write(struct.pack("<Q", 1))  # UInt64 = 1
        if version == 3:
            # SFv3: 0=zlib, 3=lz4 (COMPRESSION_METHOD_* from wbBSArchive.pas — TES5Edit@76d9d226)
            comp_method = 3 if use_lz4 else 0
            f.write(struct.pack("<I", comp_method))

        # --- Write file records (hash + mod + count + hdrsz + chunk headers) ---
        for i, entry in enumerate(entries):
            # Hash: file(4) + ext(4) + dir(4)
            f.write(struct.pack("<III", entry.name_hash, entry.ext_hash, entry.directory_hash))
            f.write(struct.pack("B", 0))  # mod index
            f.write(struct.pack("B", 1))  # chunk count

            if is_dx10:
                f.write(struct.pack("<H", CHUNK_HDR_DX10))
                # DX10 file header: height(2) + width(2) + mip_count(1) + format(1) + flags(1) + tile_mode(1)
                f.write(struct.pack("<H", entry.height))
                f.write(struct.pack("<H", entry.width))
                f.write(struct.pack("B", entry.mip_count))
                f.write(struct.pack("B", entry.dds_format))
                f.write(struct.pack("B", 1 if entry.is_cubemap else 0))
                f.write(struct.pack("B", 0))  # tile_mode
            else:
                f.write(struct.pack("<H", CHUNK_HDR_GNRL))

            # Chunk header: offset(8) + comp_size(4) + decomp_size(4) + sentinel(4)
            f.write(struct.pack("<Q", data_offsets[i]))
            comp_size = entry_data_sizes[i] if entry.compression.compressed else 0
            f.write(struct.pack("<I", comp_size))
            f.write(struct.pack("<I", entry.compression.unpacked_size))
            if is_dx10:
                f.write(struct.pack("<H", 0))  # start_mip
                f.write(struct.pack("<H", entry.mip_count - 1 if entry.mip_count > 0 else 0))  # end_mip
            f.write(struct.pack("<I", 0xBAADF00D))  # sentinel

        # --- Write all chunk data ---
        for entry in entries:
            f.write(self._data[id(entry)])

        # --- Write string table ---
        f.write(string_table_data)
