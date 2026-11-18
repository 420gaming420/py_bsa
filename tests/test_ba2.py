# Tests for BA2 (Fallout 4 / Starfield) archive reader and dump format.

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logic.bsa import ArchiveFormat
from logic.hasher import BA2Hash


# ---------------------------------------------------------------------------
# _ext_from_hash tests
# ---------------------------------------------------------------------------


class TestExtFromHash:
    def test_pex(self) -> None:
        assert BA2Hash.hash_extension("test.pex") == 0x00786570

    def test_txt(self) -> None:
        assert BA2Hash.hash_extension("test.txt") == 0x00747874

    def test_dds(self) -> None:
        assert BA2Hash.hash_extension("test.dds") == 0x00736464

    def test_nif(self) -> None:
        assert BA2Hash.hash_extension("test.nif") == 0x0066696E

    def test_empty_ext(self) -> None:
        assert BA2Hash.hash_extension("test") == 0

    def test_fuz(self) -> None:
        assert BA2Hash.hash_extension("test.fuz") == 0x007A7566

    def test_wav(self) -> None:
        assert BA2Hash.hash_extension("test.wav") == 0x00766177


# ---------------------------------------------------------------------------
# BA2 hash vector tests (from bsa C++ fo4.test.cpp — github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)
# ---------------------------------------------------------------------------


class TestBA2HashVectors:
    """Verify BA2 hashes match bsa::fo4::hashing test vectors
    (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""

    def test_fo4_hash_vectors(self) -> None:
        """FO4 hash vectors from bsa::fo4::hashing tests
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        vectors = [
            (
                r"Sound\Voice\Fallout4.esm\RobotMrHandy\María_M.fuz",
                0xC9FB26F9, 0x007A7566, 0x8A9C014E,
            ),
            (
                r"Strings\ccBGSFO4001-PipBoy(Black)_en.DLSTRINGS",
                0x1985075C, 0x74736C64, 0x29F6B58B,
            ),
            (
                r"Textures\CreationClub\BGSFO4001\AnimObjects\PipBoy\PipBoy02(Black)_d.DDS",
                0x69E1E82C, 0x00736464, 0x23157A84,
            ),
            (
                r"Meshes\Weapons\HandmadeShotgun\HandmadeShotgun_GlowSights.nif",
                0x4E080CE2, 0x0066696E, 0xCCD47ECF,
            ),
            (
                r"Textures\Weapons\HandmadeShotgun\HandmadeShotgun_Barrels_GhoulSlayer_d.DDS",
                0xBBFC484C, 0x00736464, 0xCEAE4154,
            ),
            (
                r"Sound\FX\DLC03\NPC\Gulper\NPC_Gulper_Foot_Walk_02.xwm",
                0xFE001981, 0x006D7778, 0xE7FBD6C4,
            ),
            (
                r"scripts\MinRadiantOwnedBuildResourceScript.pex",
                0xA2DAD4FD, 0x00786570, 0x40724840,
            ),
            (
                r"Textures\Effects\ColorBlackZeroAlphaUtility.DDS",
                0xF912F225, 0x00736464, 0xEA3C9738,
            ),
        ]
        for path, exp_file, exp_ext, exp_dir in vectors:
            dir_hash, file_hash, ext_hash = BA2Hash.compute_full_hash(path)
            assert dir_hash == exp_dir, (
                f"Dir hash mismatch for {path}: got 0x{dir_hash:08X}, expected 0x{exp_dir:08X}"
            )
            assert file_hash == exp_file, (
                f"File hash mismatch for {path}: got 0x{file_hash:08X}, expected 0x{exp_file:08X}"
            )
            assert ext_hash == exp_ext, (
                f"Ext hash mismatch for {path}: got 0x{ext_hash:08X}, expected 0x{exp_ext:08X}"
            )


# ---------------------------------------------------------------------------
# Synthetic BA2 archive generation and round-trip
# ---------------------------------------------------------------------------


def _make_fo4_ba2() -> bytes:
    """Create a minimal FO4 general-format BA2 archive."""
    from logic.writer import BSAWriter

    writer = BSAWriter.for_fallout4()
    writer.add_file("scripts\\ScriptArchiveOrder.txt", b"order data")
    writer.add_file("scripts\\Form.pex", b"PEX_DATA")
    writer.add_file("textures\\test.dds", b"DDS_DATA" * 10)
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


def _make_starfield_ba2() -> bytes:
    """Create a minimal Starfield general-format BA2 archive."""
    from logic.writer import BSAWriter

    writer = BSAWriter.for_starfield()
    writer.add_file("meshes\\actor\\test.nif", b"NIF_DATA")
    writer.add_file("textures\\test.dds", b"DDS_DATA" * 10)
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


def _make_starfield_dds_ba2() -> bytes:
    """Create a minimal Starfield DDS-format BA2 archive."""
    from logic.writer import BSAWriter

    writer = BSAWriter.for_starfielddds()
    writer.add_file("textures\\test.dds", b"DDS_DATA" * 10)
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def fo4_ba2_bytes() -> bytes:
    return _make_fo4_ba2()


@pytest.fixture(scope="module")
def sf_ba2_bytes() -> bytes:
    return _make_starfield_ba2()


@pytest.fixture(scope="module")
def sf_dds_ba2_bytes() -> bytes:
    return _make_starfield_dds_ba2()


class TestFO4BA2:
    def test_load(self, fo4_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(fo4_ba2_bytes)
        assert archive.fmt == ArchiveFormat.FO4
        assert len(archive.files) == 3

    def test_first_entry_hashes(self, fo4_ba2_bytes: bytes) -> None:
        """Verify hash values match bsa C++ vectors for synthetic paths
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(fo4_ba2_bytes)
        # First file: scripts\\ScriptArchiveOrder.txt
        first = archive.files[0]
        assert first.name == "scripts\\ScriptArchiveOrder.txt"
        dir_h, file_h, ext_h = BA2Hash.compute_full_hash(first.name)
        assert first.directory_hash == dir_h
        assert first.name_hash == file_h
        assert first.ext_hash == ext_h

    def test_read_all_files(self, fo4_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(fo4_ba2_bytes)
        expected = {
            "scripts\\ScriptArchiveOrder.txt": b"order data",
            "scripts\\Form.pex": b"PEX_DATA",
            "textures\\test.dds": b"DDS_DATA" * 10,
        }
        for entry in archive.files:
            data = reader.read_file(entry)
            assert data == expected[entry.name], f"Mismatch for {entry.name}"

    def test_dump_format(self, fo4_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(fo4_ba2_bytes)
        dump = reader.dump()
        assert isinstance(dump, str)
        assert "Files:" in dump
        assert "Format:" in dump
        # Check that hash lines are present
        assert "DirHash:" in dump
        assert "NameHash:" in dump


class TestStarfieldBA2:
    def test_sf_general_load(self, sf_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(sf_ba2_bytes)
        assert archive.fmt == ArchiveFormat.SF
        assert len(archive.files) == 2

    def test_sf_dds_load(self, sf_dds_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(sf_dds_ba2_bytes)
        assert archive.fmt == ArchiveFormat.SF_DDS
        assert len(archive.files) == 1

    def test_sf_roundtrip(self, sf_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(sf_ba2_bytes)
        expected = {
            "meshes\\actor\\test.nif": b"NIF_DATA",
            "textures\\test.dds": b"DDS_DATA" * 10,
        }
        for entry in archive.files:
            data = reader.read_file(entry)
            assert data == expected[entry.name], f"Mismatch for {entry.name}"

    def test_sf_compressed_roundtrip(self) -> None:
        from logic.reader.core import BSAReader
        from logic.writer import BSAWriter

        writer = BSAWriter.for_starfield()
        writer.compress = True
        writer.add_file("meshes\\actor\\test.nif", b"NIF_COMPRESSED" * 100)
        writer.add_file("textures\\test.dds", b"DDS_COMPRESSED" * 100)
        buf = io.BytesIO()
        writer.save_to(buf)
        buf.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(buf.read())
        assert archive.fmt == ArchiveFormat.SF
        assert len(archive.files) == 2
        for entry in archive.files:
            assert entry.compression.compressed is True
            data = reader.read_file(entry)
            assert len(data) > 0


class TestBA2EdgeCases:
    def test_empty_ba2(self) -> None:
        from logic.reader.core import BSAReader
        from logic.writer import BSAWriter

        writer = BSAWriter.for_fallout4()
        buf = io.BytesIO()
        writer.save_to(buf)
        buf.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(buf.read())
        assert archive.fmt == ArchiveFormat.FO4
        assert len(archive.files) == 0

    def test_missing_file_raises(self, fo4_ba2_bytes: bytes) -> None:
        from logic.reader.core import BSAReader

        reader = BSAReader()
        archive = reader.load_bytes(fo4_ba2_bytes)
        with pytest.raises(KeyError):
            reader.read_file_by_name("nonexistent.file")
