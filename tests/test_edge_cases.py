# Edge-case and stress tests for the BSA module.

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logic.reader import BSAReader
from logic.writer import BSAWriter
from logic.hasher import TES3Hash, TES4Hash
from logic.bsa import CompressionFlag


# ---------------------------------------------------------------------------
# Hash edge cases
# ---------------------------------------------------------------------------


class TestHashEdgeCases:
    """Edge cases for hash functions."""

    def test_tes3_single_char(self) -> None:
        h = TES3Hash.hash("a")
        assert isinstance(h, int)
        assert h >= 0

    def test_tes3_unicode(self) -> None:
        h = TES3Hash.hash("meshes/\u00e9test.nif")
        assert isinstance(h, int)

    def test_tes4_single_char_stem(self) -> None:
        h = TES4Hash.hash_file("a.txt")
        assert isinstance(h, int)

    def test_tes4_no_extension(self) -> None:
        h = TES4Hash.hash_file("README")
        assert isinstance(h, int)

    def test_tes4_multiple_dots(self) -> None:
        h1 = TES4Hash.hash_file("test.file.name.txt")
        h2 = TES4Hash.hash_file("test.file.name.txt")
        assert h1 == h2

    def test_tes4_special_chars(self) -> None:
        h = TES4Hash.hash_file("test-file_name.txt")
        assert isinstance(h, int)

    def test_tes3_path_with_spaces(self) -> None:
        h = TES3Hash.hash("meshes/r/xkwama worker.nif")
        assert isinstance(h, int)


# ---------------------------------------------------------------------------
# Writer edge cases
# ---------------------------------------------------------------------------


class TestWriterEdgeCases:
    """Edge cases for BSA writing."""

    def test_zero_byte_file(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("empty.txt", b"")
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 1
        data = reader.read_file(archive.files[0])
        assert data.rstrip(b"\x00") == b""

    def test_large_file(self) -> None:
        data = bytes(range(256)) * 3906  # ~1 MB
        writer = BSAWriter.for_fallout3()
        writer.add_file("large.bin", data)
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        entry = archive.files[0]
        result = reader.read_file(entry)
        assert result == data

    def test_compressed_large_file(self) -> None:
        data = b"repeat " * 50000
        writer = BSAWriter.for_fallout3()
        writer.compress = True
        writer.add_file("large.txt", data)
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        result = reader.read_file(archive.files[0])
        assert result == data

    def test_many_files(self) -> None:
        writer = BSAWriter.for_fallout3()
        for i in range(100):
            writer.add_file(f"meshes\\file_{i:03d}.nif", f"data_{i}".encode())

        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        assert len(archive.files) == 100

        for i in range(100):
            name = f"meshes\\file_{i:03d}.nif"
            data = reader.read_file_by_name(name)
            assert data == f"data_{i}".encode()

    def test_deeply_nested_paths(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("a\\b\\c\\d\\e\\file.txt", b"deep")
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)

        reader = BSAReader()
        archive = reader.load_bytes(stream.read())
        data = reader.read_file_by_name("a\\b\\c\\d\\e\\file.txt")
        assert data == b"deep"

    def test_unicode_filename(self) -> None:
        writer = BSAWriter.for_fallout3()
        writer.add_file("meshes\\test\u00e9.nif", b"data")
        stream = io.BytesIO()
        writer.save_to(stream)
        stream.seek(0)


# ---------------------------------------------------------------------------
# Reader error handling
# ---------------------------------------------------------------------------


class TestReaderErrorHandling:
    """Test that the reader handles errors gracefully."""

    def test_nonexistent_file(self) -> None:
        reader = BSAReader()
        with pytest.raises(FileNotFoundError):
            reader.load("/nonexistent/path/file.bsa")

    def test_invalid_magic(self) -> None:
        reader = BSAReader()
        with pytest.raises(ValueError):
            reader.load_bytes(b"XXXX\x00\x00\x00\x00")

    def test_truncated_header(self) -> None:
        reader = BSAReader()
        with pytest.raises(Exception):
            reader.load_bytes(b"BSA\x00")

    def test_truncated_file_data(self) -> None:
        # Archive flags 0x07 = PATHNAMES | FILENAMES | COMPRESS
        header = b"BSA\x00"
        header += b"\x68\x00\x00\x00"
        header += b"\x24\x00\x00\x00"
        header += b"\x07\x00\x00\x00"
        header += b"\x01\x00\x00\x00"
        header += b"\x01\x00\x00\x00"
        header += b"\x00\x00\x00\x00"
        header += b"\x0b\x00\x00\x00"
        header += b"\x00\x00\x00\x00"
        header += b"\x00\x00"

        folder_rec = b"\x00\x00\x00\x00\x00\x00\x00\x00"
        folder_rec += b"\x01\x00\x00\x00"
        folder_rec += b"\x00\x00\x00\x00"

        # size_flags = 0x05, archive COMPRESS is set
        # XOR: true ^ false = true -> compressed
        # But there's no actual data after the header, so read_file should fail
        mixed = b"\x00\x00"
        mixed += b"\x00\x00\x00\x00\x00\x00\x00\x00"
        mixed += b"\x05\x00\x00\x00"
        mixed += b"\x00\x00\x00\x00"
        mixed += b"test.txt\x00"

        truncated = header + folder_rec + mixed
        reader = BSAReader()
        archive = reader.load_bytes(truncated)
        with pytest.raises(Exception):
            reader.read_file(archive.files[0])


# ---------------------------------------------------------------------------
# CompressionFlag tests
# ---------------------------------------------------------------------------


class TestCompressionFlag:
    """Unit tests for the CompressionFlag model."""

    def test_uncompressed(self) -> None:
        flag = CompressionFlag(compressed=False, unpacked_size=100)
        assert not flag.compressed
        assert flag.unpacked_size == 100

    def test_compressed(self) -> None:
        flag = CompressionFlag(compressed=True, unpacked_size=50)
        assert flag.compressed
        assert flag.unpacked_size == 50

    def test_roundtrip(self) -> None:
        original = 0x40000005
        flag = CompressionFlag.from_size_flags(original)
        assert flag.compressed
        assert flag.unpacked_size == 5
        assert flag.to_size_flags() == original

    def test_uncompressed_roundtrip(self) -> None:
        original = 0x00000064
        flag = CompressionFlag.from_size_flags(original)
        assert not flag.compressed
        assert flag.unpacked_size == 100
        assert flag.to_size_flags() == original
