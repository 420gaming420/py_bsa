# Round-trip tests: write a BSA, then read it back and verify contents.

from __future__ import annotations

import io
import zlib

import pytest

from logic.reader import BSAReader
from logic.writer import BSAWriter
from logic.bsa import ArchiveFormat, BSAFileEntry, CompressionFlag
from logic.hasher import TES4Hash


# ---------------------------------------------------------------------------
# Basic write / read round-trip
# ---------------------------------------------------------------------------


class TestWriteReadRoundTrip:
    """Test that writing and reading back produces identical results."""

    def test_empty_archive(self) -> None:
        writer = BSAWriter.for_fallout3()
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 0

    def test_single_file_uncompressed(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("meshes\\actor\\test.nif", b"Hello, BSA!")

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 1

        entry = archive.files[0]
        assert entry.name == "meshes\\actor\\test.nif"
        data = reader.read_file(entry)
        assert data.rstrip(b"\x00") == b"Hello, BSA!"

    def test_single_file_compressed(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.compress = True
        writer.add_file("textures\\test.dds", b"x" * 1000)

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 1

        entry = archive.files[0]
        assert entry.compression.compressed is True
        data = reader.read_file(entry)
        assert data == b"x" * 1000

    def test_multiple_files(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("meshes\\a.nif", b"data_a")
        writer.add_file("meshes\\b.nif", b"data_b")
        writer.add_file("textures\\c.dds", b"data_c")

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 3

        for name, expected in [
            ("meshes\\a.nif", b"data_a"),
            ("meshes\\b.nif", b"data_b"),
            ("textures\\c.dds", b"data_c"),
        ]:
            data = reader.read_file_by_name(name)
            assert data == expected

    def test_nested_paths(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("sound\\voice\\test.fuz", b"voice_data")
        writer.add_file("scripts\\test.pex", b"script_data")

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 2

        for name, expected in [
            ("sound\\voice\\test.fuz", b"voice_data"),
            ("scripts\\test.pex", b"script_data"),
        ]:
            data = reader.read_file_by_name(name)
            assert data == expected


# ---------------------------------------------------------------------------
# Hash consistency
# ---------------------------------------------------------------------------


class TestHashConsistency:
    """Verify that written hashes match computed hashes."""

    def test_file_hash_matches(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("meshes\\test.nif", b"data")

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        entry = archive.files[0]

        expected_hash = TES4Hash.hash_file("meshes\\test.nif")
        assert entry.name_hash == expected_hash


# ---------------------------------------------------------------------------
# Format variants
# ---------------------------------------------------------------------------


class TestFormatVariants:
    """Test writing different archive formats."""

    def test_oblivion_format(self) -> None:
        writer = BSAWriter.for_oblivion()
        writer.add_file("test.txt", b"hello")
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert archive.fmt == ArchiveFormat.TES4

    def test_skyrim_format(self) -> None:
        writer = BSAWriter.for_skyrim()
        writer.add_file("test.txt", b"hello")
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert archive.fmt == ArchiveFormat.SSE

    def test_starfield_format(self) -> None:
        writer = BSAWriter.for_starfield()
        writer.add_file("test.txt", b"hello")
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert archive.fmt == ArchiveFormat.SF

    def test_starfield_roundtrip(self) -> None:
        writer = BSAWriter.for_starfield()
        writer.add_file("meshes\\actor\\test.nif", b"NIF data")
        writer.add_file("textures\\test.dds", b"DDS data" * 100)
        writer.add_file("scripts\\test.pex", b"PEX data")

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert archive.fmt == ArchiveFormat.SF
        assert len(archive.files) == 3

        expected = {
            "meshes\\actor\\test.nif": b"NIF data",
            "textures\\test.dds": b"DDS data" * 100,
            "scripts\\test.pex": b"PEX data",
        }
        for entry in archive.files:
            data = reader.read_file(entry)
            assert data == expected[entry.name]

    def test_starfield_compressed_roundtrip(self) -> None:
        writer = BSAWriter.for_starfield()
        writer.compress = True
        writer.add_file("meshes\\actor\\test.nif", b"NIF data" * 100)
        writer.add_file("textures\\test.dds", b"DDS data" * 100)

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert archive.fmt == ArchiveFormat.SF
        assert len(archive.files) == 2

        expected = {
            "meshes\\actor\\test.nif": b"NIF data" * 100,
            "textures\\test.dds": b"DDS data" * 100,
        }
        for entry in archive.files:
            assert entry.compression.compressed is True
            data = reader.read_file(entry)
            assert data == expected[entry.name]


# ---------------------------------------------------------------------------
# Compression quality
# ---------------------------------------------------------------------------


class TestCompression:
    """Test compression behavior."""

    def test_compressed_smaller(self) -> None:
        original = b"A" * 10000
        writer = BSAWriter.for_fallout3()
        writer.compress = True
        writer.add_file("test.txt", original)

        stream = io.BytesIO()
        writer.save_to(stream)
        compressed_size = len(stream.getvalue())

        writer2 = BSAWriter.for_fallout3()
        writer2.compress = False
        writer2.add_file("test.txt", original)
        stream2 = io.BytesIO()
        writer2.save_to(stream2)
        uncompressed_size = len(stream2.getvalue())

        assert compressed_size < uncompressed_size

    def test_compression_levels(self) -> None:
        data = b"test content " * 100
        for level in (0, 1, 5, 9):
            writer = BSAWriter.for_fallout3()
            writer.compress = True
            writer.compression_level = level
            writer.add_file("test.txt", data)

            stream = io.BytesIO()
            writer.save_to(stream)
            stream.seek(0)

            reader = BSAReader()
            archive = reader.load_bytes(stream.read())
            entry = archive.files[0]
            result = reader.read_file(entry)
            assert result == data
