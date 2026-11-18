# Tests for the BSA reader using synthetically generated archives.

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logic.reader import BSAReader
from logic.writer import BSAWriter
from logic.bsa import ArchiveFormat
from logic.hasher import TES3Hash, TES4Hash


def _make_tes3_archive() -> bytes:
    """Create a minimal TES3 (Morrowind) BSA with known content."""
    writer = BSAWriter.for_morrowind()
    writer.add_file("meshes\\c\\artifact_bloodring_01.nif", b"NIF_DATA_01")
    writer.add_file("textures\\tx_rock_cave_mu_01.dds", b"DDS_DATA_01")
    writer.add_file("share\\License.txt", b"MIT License\n")
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


def _make_tes4_archive() -> bytes:
    """Create a minimal TES4 (Oblivion) BSA with known content."""
    writer = BSAWriter.for_oblivion()
    writer.add_file("meshes\\actor\\test.nif", b"NIF_DATA_TEST")
    writer.add_file("textures\\actor\\test.dds", b"DDS_DATA_TEST")
    writer.add_file("scripts\\test.pex", b"PEX_DATA_TEST")
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


def _make_fo3_archive() -> bytes:
    """Create a minimal Fallout 3 BSA with known content."""
    writer = BSAWriter.for_fallout3()
    writer.add_file("meshes\\a\\test.nif", b"NIF_FO3")
    writer.add_file("textures\\b\\test.dds", b"DDS_FO3")
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


def _make_sse_archive() -> bytes:
    """Create a minimal Skyrim SE BSA with known content."""
    writer = BSAWriter.for_skyrim()
    writer.add_file("meshes\\c\\test.nif", b"NIF_SSE")
    writer.add_file("textures\\d\\test.dds", b"DDS_SSE")
    writer.add_file("sound\\test.fuz", b"FUZ_DATA")
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


def _make_compressed_tes4_archive() -> bytes:
    """Create a compressed TES4 BSA."""
    writer = BSAWriter.for_oblivion()
    writer.compress = True
    writer.add_file("meshes\\actor\\test.nif", b"NIF_COMPRESSED" * 100)
    writer.add_file("textures\\test.dds", b"DDS_COMPRESSED" * 100)
    buf = io.BytesIO()
    writer.save_to(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def tes3_archive_bytes() -> bytes:
    return _make_tes3_archive()


@pytest.fixture(scope="module")
def tes4_archive_bytes() -> bytes:
    return _make_tes4_archive()


@pytest.fixture(scope="module")
def fo3_archive_bytes() -> bytes:
    return _make_fo3_archive()


@pytest.fixture(scope="module")
def sse_archive_bytes() -> bytes:
    return _make_sse_archive()


@pytest.fixture(scope="module")
def compressed_tes4_bytes() -> bytes:
    return _make_compressed_tes4_archive()


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------


class TestBSAStructure:
    """Test that synthetic archives parse without errors."""

    def test_tes3_load(self, tes3_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes3_archive_bytes)
        assert archive is not None
        assert len(archive.files) > 0
        assert archive.fmt == ArchiveFormat.TES3

    def test_tes4_load(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        assert archive is not None
        assert len(archive.files) == 3
        assert archive.fmt == ArchiveFormat.TES4

    def test_fo3_load(self, fo3_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(fo3_archive_bytes)
        assert archive is not None
        assert len(archive.files) == 2
        assert archive.fmt == ArchiveFormat.FO3

    def test_sse_load(self, sse_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(sse_archive_bytes)
        assert archive is not None
        assert len(archive.files) == 3
        assert archive.fmt == ArchiveFormat.SSE

    def test_compressed_tes4_load(self, compressed_tes4_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(compressed_tes4_bytes)
        assert archive is not None
        assert archive.compressed is True
        assert len(archive.files) == 2


# ---------------------------------------------------------------------------
# File listing tests
# ---------------------------------------------------------------------------


class TestFileListing:
    """Test that all files can be listed."""

    def test_tes3_list_files(self, tes3_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes3_archive_bytes)
        files = reader.list_files()
        assert len(files) == len(archive.files)
        for name in files:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_tes4_iterate(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        files = list(reader)
        assert len(files) == len(archive.files)


# ---------------------------------------------------------------------------
# File content tests
# ---------------------------------------------------------------------------


class TestFileExtraction:
    """Test that individual files can be read and decompressed."""

    def test_tes3_read_all(self, tes3_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes3_archive_bytes)
        expected = {
            "meshes\\c\\artifact_bloodring_01.nif": b"NIF_DATA_01",
            "textures\\tx_rock_cave_mu_01.dds": b"DDS_DATA_01",
            "share\\License.txt": b"MIT License\n",
        }
        for entry in archive.files:
            data = reader.read_file(entry)
            assert data == expected[entry.name], f"Mismatch for {entry.name}"

    def test_tes4_read_all(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        expected = {
            "meshes\\actor\\test.nif": b"NIF_DATA_TEST",
            "textures\\actor\\test.dds": b"DDS_DATA_TEST",
            "scripts\\test.pex": b"PEX_DATA_TEST",
        }
        for entry in archive.files:
            data = reader.read_file(entry)
            assert data == expected[entry.name], f"Mismatch for {entry.name}"

    def test_compressed_roundtrip(self, compressed_tes4_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(compressed_tes4_bytes)
        for entry in archive.files:
            assert entry.compression.compressed is True
            data = reader.read_file(entry)
            assert len(data) > 0

    def test_read_by_name(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        data = reader.read_file_by_name("meshes\\actor\\test.nif")
        assert data == b"NIF_DATA_TEST"


# ---------------------------------------------------------------------------
# Hash verification against known vectors
# ---------------------------------------------------------------------------


class TestHashVectors:
    """Verify hashes match bsa C++ library test vectors
    (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""

    def test_tes3_known_vectors(self) -> None:
        """TES3 hash vectors from bsa::tes3::hashing tests
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        vectors = [
            ("meshes/c/artifact_bloodring_01.nif", 0x1C3C1149920D5F0C),
            ("meshes/x/ex_stronghold_pylon00.nif", 0x20250749ACCCD202),
            ("meshes/r/xsteam_centurions.kf", 0x6E5C0F3125072EA6),
            ("textures/tx_rock_cave_mu_01.dds", 0x58060C2FA3D8F759),
            ("meshes/f/furn_ashl_chime_02.nif", 0x7C3B2F3ABFFC8611),
            ("textures/tx_rope_woven.dds", 0x5865632F0C052C64),
            ("icons/a/tx_templar_skirt.dds", 0x46512A0B60EDA673),
            ("icons/m/misc_prongs00.dds", 0x51715677BBA837D3),
            ("meshes/i/in_c_stair_plain_tall_02.nif", 0x2A324956BF89B1C9),
            ("meshes/r/xkwama worker.nif", 0x6D446E352C3F5A1E),
        ]
        for path, expected in vectors:
            h = TES3Hash.hash(path)
            assert h == expected, f"TES3 hash mismatch for {path}: got 0x{h:016X}, expected 0x{expected:016X}"

    def test_tes4_directory_vectors(self) -> None:
        """TES4 directory hash vectors from bsa::tes4::hashing tests
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        vectors = [
            ("textures/armor/amuletsandrings/elder council", 0x04BC422C742C696C),
            ("sound/voice/skyrim.esm/maleuniquedbguardian", 0x594085AC732B616E),
            ("textures/architecture/windhelm", 0xC1D97EBE741E6C6D),
        ]
        for path, expected in vectors:
            h = TES4Hash.hash_directory(path)
            assert h == expected, f"TES4 dir hash mismatch for {path}: got 0x{h:016X}, expected 0x{expected:016X}"

    def test_tes4_file_vectors(self) -> None:
        """TES4 file hash vectors from bsa::tes4::hashing tests
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        vectors = [
            ("darkbrotherhood__0007469a_1.fuz", 0x011F11B0641B5F31),
            ("elder_council_amulet_n.dds", 0xDC531E2F6516DFEE),
            ("testtoddquest_testtoddhappy_00027fa2_1.mp3", 0xDE0301EE74265F31),
        ]
        for path, expected in vectors:
            h = TES4Hash.hash_file(path)
            assert h == expected, f"TES4 file hash mismatch for {path}: got 0x{h:016X}, expected 0x{expected:016X}"

    def test_tes3_case_insensitive(self) -> None:
        h1 = TES3Hash.hash("Meshes\\Actor\\Test.Nif")
        h2 = TES3Hash.hash("meshes\\actor\\test.nif")
        assert h1 == h2

    def test_tes3_forward_slash_normalization(self) -> None:
        h1 = TES3Hash.hash("meshes/actor/test.nif")
        h2 = TES3Hash.hash("meshes\\actor\\test.nif")
        assert h1 == h2

    def test_tes4_root_paths_different(self) -> None:
        h1 = TES4Hash.hash_directory("C:\\foo\\bar\\baz")
        h2 = TES4Hash.hash_directory("foo/bar/baz")
        assert h1 != h2

    def test_tes4_long_directory_equivalent_to_empty(self) -> None:
        long_path = "a" * 300
        empty = TES4Hash.hash_directory("")
        assert TES4Hash.hash_directory(long_path) == empty

    def test_tes4_long_file_stems_fail(self) -> None:
        good = TES4Hash.hash_file("a" * 259 + ".txt")
        bad = TES4Hash.hash_file("a" * 260 + ".txt")
        assert good != 0
        assert bad == 0


# ---------------------------------------------------------------------------
# Info output test
# ---------------------------------------------------------------------------


class TestInfo:
    """Test the info() summary output."""

    def test_info_is_string(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        info = reader.info()
        assert isinstance(info, str)
        assert len(info) > 0

    def test_info_contains_file_count(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        info = reader.info()
        assert str(len(archive.files)) in info


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_file_raises(self, tes4_archive_bytes: bytes) -> None:
        reader = BSAReader()
        archive = reader.load_bytes(tes4_archive_bytes)
        with pytest.raises(KeyError):
            reader.read_file_by_name("nonexistent_file.txt")

    def test_empty_archive(self) -> None:
        writer = BSAWriter.for_fallout3()
        buf = io.BytesIO()
        writer.save_to(buf)
        buf.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(buf.read())
        assert archive.fmt == ArchiveFormat.FO3
        assert len(archive.files) == 0

    def test_empty_file_in_archive(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("empty.txt", b"")
        writer.add_file("normal.txt", b"not empty")
        buf = io.BytesIO()
        writer.save_to(buf)
        buf.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(buf.read())
        assert len(archive.files) == 2

        data = reader.read_file_by_name("empty.txt")
        assert data == b""
        data = reader.read_file_by_name("normal.txt")
        assert data == b"not empty"
