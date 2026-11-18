# BSA round-trip validation tests.

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from pathlib import Path

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logic.reader import BSAReader
from logic.writer import BSAWriter
from logic.bsa import ArchiveFormat


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _collect_files(dirpath: str) -> dict[str, bytes]:
    result = {}
    for root, _, files in os.walk(dirpath):
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, dirpath).replace("\\", "/")
            with open(full, "rb") as f:
                result[rel] = f.read()
    return result


def _make_hello_world() -> bytes:
    return b"Hello, BSA World!"


def _make_repetitive_data(size: int = 1024) -> bytes:
    return b"ABCD" * (size // 4)


def _make_large_data(size_mb: float = 0.5) -> bytes:
    return bytes(range(256)) * int(size_mb * 1024 * 1024 // 256)


class TestBSARoundTrip:
    """Full round-trip validation: pack -> unpack -> repack -> unpack -> compare.

    Each test verifies the complete cycle:
    1. Create synthetic files with known content (original directory)
    2. Pack the files into a BSA archive
    3. Unpack the BSA archive to temp directory A
    4. Repack from temp directory A back into a BSA archive
    5. Unpack the repacked BSA to temp directory B
    6. Compare SHA-256 hashes of all files between all sets:
       - original vs A
       - original vs B
       - A vs B
       (all computed dynamically, no hardcoded values)
    """

    def test_single_file_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as orig_dir:
            original_data = _make_hello_world()
            original_name = "test\\hello.txt"
            path = os.path.join(orig_dir, original_name.replace("\\", "/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(original_data)

            writer = BSAWriter.for_fallout3()
            for root, _, files in os.walk(orig_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, files in os.walk(dir_a):
                    for fname in files:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_multiple_files_roundtrip(self) -> None:
        files = {
            "meshes\\actor\\test.nif": b"NIF data here",
            "textures\\test.dds": b"DDS texture data",
            "scripts\\test.pex": b"PEX script data",
            "sound\\test.wav": b"WAV audio data" * 10,
        }

        with tempfile.TemporaryDirectory() as orig_dir:
            for name, data in files.items():
                path = os.path.join(orig_dir, name.replace("\\", "/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            writer = BSAWriter.for_fallout3()
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_compressed_roundtrip(self) -> None:
        original_data = _make_repetitive_data(4096)
        original_name = "compressed\\test.bin"

        with tempfile.TemporaryDirectory() as orig_dir:
            path = os.path.join(orig_dir, original_name.replace("\\", "/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(original_data)

            writer = BSAWriter.for_fallout3()
            writer.compress = True
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                writer2.compress = True
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_nested_paths_roundtrip(self) -> None:
        files = {
            "a\\b\\c\\d\\e\\file.txt": b"deep content",
            "x\\y\\z\\another.txt": b"another deep file",
            "root.txt": b"root level file",
        }

        with tempfile.TemporaryDirectory() as orig_dir:
            for name, data in files.items():
                path = os.path.join(orig_dir, name.replace("\\", "/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            writer = BSAWriter.for_fallout3()
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_many_files_roundtrip(self) -> None:
        num_files = 50
        files = {f"meshes\\file_{i:03d}.nif": f"nif_data_{i}".encode() for i in range(num_files)}

        with tempfile.TemporaryDirectory() as orig_dir:
            for name, data in files.items():
                path = os.path.join(orig_dir, name.replace("\\", "/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            writer = BSAWriter.for_fallout3()
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_large_file_roundtrip(self) -> None:
        original_data = _make_large_data(1.0)
        original_name = "large\\binary.bin"

        with tempfile.TemporaryDirectory() as orig_dir:
            path = os.path.join(orig_dir, original_name.replace("\\", "/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(original_data)

            writer = BSAWriter.for_fallout3()
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_mixed_compression_roundtrip(self) -> None:
        files = {
            "compressed\\test.bin": _make_repetitive_data(2048),
            "uncompressed\\test.txt": b"small text data",
            "also_compressed\\data.bin": _make_repetitive_data(1024),
        }

        with tempfile.TemporaryDirectory() as orig_dir:
            for name, data in files.items():
                path = os.path.join(orig_dir, name.replace("\\", "/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            writer = BSAWriter.for_fallout3()
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        content = f.read()
                        if "compressed" in rel or "also" in rel:
                            writer.compress = True
                        else:
                            writer.compress = False
                        writer.add_file(rel.replace("/", "\\"), content)
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_empty_file_roundtrip(self) -> None:
        files = {
            "empty1.txt": b"",
            "empty2.dat": b"",
            "normal.txt": b"not empty",
        }

        with tempfile.TemporaryDirectory() as orig_dir:
            for name, data in files.items():
                path = os.path.join(orig_dir, name.replace("\\", "/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            writer = BSAWriter.for_fallout3()
            for root, _, fnames in os.walk(orig_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, orig_dir)
                    with open(full, "rb") as f:
                        writer.add_file(rel.replace("/", "\\"), f.read())
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            with tempfile.TemporaryDirectory() as dir_a:
                reader = BSAReader()
                archive = reader.load_bytes(bsa_bytes.read())
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(dir_a, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = BSAWriter.for_fallout3()
                for root, _, fnames in os.walk(dir_a):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, dir_a)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())
                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                with tempfile.TemporaryDirectory() as dir_b:
                    reader2 = BSAReader()
                    archive2 = reader2.load_bytes(repacked.read())
                    for entry in archive2.files:
                        data = reader2.read_file(entry)
                        out_path = os.path.join(dir_b, entry.name.lstrip("\\").replace("\\", "/"))
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(data)

                    orig_map = _collect_files(orig_dir)
                    map_a = _collect_files(dir_a)
                    map_b = _collect_files(dir_b)
                    all_keys = set(list(orig_map.keys()) + list(map_a.keys()) + list(map_b.keys()))
                    for name in all_keys:
                        h_orig = _sha256(orig_map.get(name, b""))
                        h_a = _sha256(map_a.get(name, b""))
                        h_b = _sha256(map_b.get(name, b""))
                        assert h_orig == h_a, f"Hash mismatch original vs A for {name}"
                        assert h_orig == h_b, f"Hash mismatch original vs B for {name}"
                        assert h_a == h_b, f"Hash mismatch A vs B for {name}"

    def test_all_formats_roundtrip(self) -> None:
        formats = [
            (ArchiveFormat.TES4, BSAWriter.for_oblivion),
            (ArchiveFormat.FO3, BSAWriter.for_fallout3),
            (ArchiveFormat.SSE, BSAWriter.for_skyrim),
            (ArchiveFormat.FO4, BSAWriter.for_fallout4),
            (ArchiveFormat.SF, BSAWriter.for_starfield),
        ]

        for fmt, writer_cls in formats:
            writer = writer_cls()
            writer.add_file("test.txt", b"format test data")
            bsa_bytes = io.BytesIO()
            writer.save_to(bsa_bytes)
            bsa_bytes.seek(0)

            reader = BSAReader()
            archive = reader.load_bytes(bsa_bytes.read())
            assert archive.fmt == fmt

            with tempfile.TemporaryDirectory() as tmpdir:
                for entry in archive.files:
                    data = reader.read_file(entry)
                    out_path = os.path.join(tmpdir, entry.name.lstrip("\\").replace("\\", "/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(data)

                writer2 = writer_cls()
                for root, _, fnames in os.walk(tmpdir):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, tmpdir)
                        with open(full, "rb") as f:
                            writer2.add_file(rel.replace("/", "\\"), f.read())

                repacked = io.BytesIO()
                writer2.save_to(repacked)
                repacked.seek(0)

                reader2 = BSAReader()
                archive2 = reader2.load_bytes(repacked.read())

                orig_map = {e.name: reader.read_file(e) for e in archive.files}
                repack_map = {e.name: reader2.read_file(e) for e in archive2.files}

                assert set(orig_map.keys()) == set(repack_map.keys())
                for name in orig_map:
                    h1 = _sha256(orig_map[name])
                    h2 = _sha256(repack_map[name])
                    assert h1 == h2, f"Hash mismatch for {name} in {fmt.name}"
