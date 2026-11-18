# CLI tests using synthetically generated archives.

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logic.bsa import ArchiveFormat
from logic.reader import BSAReader
from logic.writer import BSAWriter


def run_cli(args: list[str]) -> tuple[int, str, str]:
    cli_path = Path(__file__).parent.parent / "cli.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
    result = subprocess.run(
        [sys.executable, str(cli_path)] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _make_test_bsa(tmp_path: Path, name: str = "test.bsa", fmt: str = "fo3") -> Path:
    """Create a synthetic BSA file for CLI tests."""
    writer = BSAWriter.for_fallout3()
    if fmt == "sse":
        writer = BSAWriter.for_skyrim()
    elif fmt == "tes4":
        writer = BSAWriter.for_oblivion()
    writer.add_file("meshes\\actor\\test.nif", b"NIF_DATA")
    writer.add_file("textures\\test.dds", b"DDS_DATA" * 100)
    writer.add_file("scripts\\test.pex", b"PEX_DATA")
    output = tmp_path / name
    writer.save_to(output.open("wb"))
    return output


# ---------------------------------------------------------------------------
# Help tests
# ---------------------------------------------------------------------------


class TestCLIHelp:
    def test_help(self) -> None:
        rc, out, _ = run_cli(["--help"])
        assert rc == 0
        assert "BSA archive" in out.lower() or "unpack" in out.lower()

    def test_unpack_help(self) -> None:
        rc, out, _ = run_cli(["unpack", "--help"])
        assert rc == 0
        assert "--output" in out
        assert "--verbose" in out

    def test_pack_help(self) -> None:
        rc, out, _ = run_cli(["pack", "--help"])
        assert rc == 0
        assert "--output" in out
        assert "--format" in out
        assert "--compress" in out

    def test_info_help(self) -> None:
        rc, out, _ = run_cli(["info", "--help"])
        assert rc == 0

    def test_list_help(self) -> None:
        rc, out, _ = run_cli(["list", "--help"])
        assert rc == 0


# ---------------------------------------------------------------------------
# Info tests
# ---------------------------------------------------------------------------


class TestCLIInfo:
    def test_info_synthetic_bsa(self, tmp_path: Path) -> None:
        bsa_file = _make_test_bsa(tmp_path)

        rc, out, err = run_cli(["info", str(bsa_file)])
        assert rc == 0
        assert "test.bsa" in out or "Files:" in out
        assert "Files:" in out
        assert "Format:" in out

    def test_info_missing_file(self) -> None:
        rc, out, err = run_cli(["info", "/nonexistent/file.bsa"])
        assert rc == 1
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# List tests
# ---------------------------------------------------------------------------


class TestCLISlist:
    def test_list_synthetic_bsa(self, tmp_path: Path) -> None:
        bsa_file = _make_test_bsa(tmp_path)

        rc, out, err = run_cli(["list", str(bsa_file)])
        assert rc == 0
        lines = [l for l in out.strip().split("\n") if l]
        assert len(lines) == 3
        assert any("meshes" in l for l in lines)
        assert any("textures" in l for l in lines)
        assert any("scripts" in l for l in lines)

    def test_list_missing_file(self) -> None:
        rc, out, err = run_cli(["list", "/nonexistent/file.bsa"])
        assert rc == 1
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# Unpack tests
# ---------------------------------------------------------------------------


class TestCLIUnpack:
    def test_unpack_synthetic_bsa(self, tmp_path: Path) -> None:
        bsa_file = _make_test_bsa(tmp_path)
        output_dir = tmp_path / "unpacked"
        rc, out, err = run_cli(["unpack", str(bsa_file), "--output", str(output_dir)])
        assert rc == 0
        assert output_dir.exists()

        files = list(output_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        assert len(files) == 3

        reader = BSAReader()
        archive = reader.load(bsa_file)
        for entry in archive.files:
            expected = reader.read_file(entry)
            out_path = output_dir / entry.name.replace("\\", "/")
            assert out_path.exists(), f"Missing: {entry.name}"
            with open(out_path, "rb") as f:
                actual = f.read()
            assert actual == expected, f"Content mismatch: {entry.name}"

    def test_unpack_verbose(self, tmp_path: Path) -> None:
        bsa_file = _make_test_bsa(tmp_path)
        output_dir = tmp_path / "unpacked_verbose"
        rc, out, err = run_cli(["unpack", str(bsa_file), "--output", str(output_dir), "--verbose"])
        assert rc == 0
        assert "Unpacking 3 files" in out

    def test_unpack_missing_file(self, tmp_path: Path) -> None:
        rc, out, err = run_cli(["unpack", "/nonexistent/file.bsa", "--output", str(tmp_path / "out")])
        assert rc == 1
        assert "not found" in err.lower()

    def test_unpack_default_output(self, tmp_path: Path) -> None:
        bsa_file = _make_test_bsa(tmp_path)
        rc, out, err = run_cli(["unpack", str(bsa_file)])
        assert rc == 0
        expected_dir = bsa_file.parent / bsa_file.stem
        assert expected_dir.exists()
        import shutil
        shutil.rmtree(expected_dir)


# ---------------------------------------------------------------------------
# Pack tests
# ---------------------------------------------------------------------------


class TestCLIPack:
    def test_pack_basic(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        (test_dir / "meshes").mkdir(parents=True)
        (test_dir / "textures").mkdir(parents=True)
        (test_dir / "meshes" / "test.nif").write_bytes(b"NIF data")
        (test_dir / "textures" / "test.dds").write_bytes(b"DDS data" * 100)

        output_bsa = tmp_path / "output.bsa"
        rc, out, err = run_cli(["pack", str(test_dir), "--output", str(output_bsa)])
        assert rc == 0
        assert output_bsa.exists()

        reader = BSAReader()
        archive = reader.load(output_bsa)
        assert len(archive.files) == 2
        names = [f.name for f in archive.files]
        assert any("test.nif" in n for n in names)
        assert any("test.dds" in n for n in names)

    def test_pack_verbose(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test.txt").write_bytes(b"hello")

        output_bsa = tmp_path / "output.bsa"
        rc, out, err = run_cli(["pack", str(test_dir), "--output", str(output_bsa), "--verbose"])
        assert rc == 0
        assert "Adding:" in out
        assert "Packed" in out

    def test_pack_compressed(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test.bin").write_bytes(b"A" * 10000)

        output_bsa = tmp_path / "output_comp.bsa"
        rc, out, err = run_cli([
            "pack", str(test_dir), "--output", str(output_bsa),
            "--compress", "--level", "6"
        ])
        assert rc == 0
        assert output_bsa.exists()

        reader = BSAReader()
        archive = reader.load(output_bsa)
        assert archive.compressed

    def test_pack_skyrim_format(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test.txt").write_bytes(b"hello")

        output_bsa = tmp_path / "output_sse.bsa"
        rc, out, err = run_cli(["pack", str(test_dir), "--output", str(output_bsa), "--format", "sse"])
        assert rc == 0

        reader = BSAReader()
        archive = reader.load(output_bsa)
        assert archive.fmt == ArchiveFormat.SSE

    def test_pack_oblivion_format(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test.txt").write_bytes(b"hello")

        output_bsa = tmp_path / "output_tes4.bsa"
        rc, out, err = run_cli(["pack", str(test_dir), "--output", str(output_bsa), "--format", "tes4"])
        assert rc == 0

        reader = BSAReader()
        archive = reader.load(output_bsa)
        assert archive.fmt == ArchiveFormat.TES4

    def test_pack_nested_dirs(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        (test_dir / "a" / "b" / "c").mkdir(parents=True)
        (test_dir / "a" / "b" / "c" / "deep.txt").write_bytes(b"deep content")

        output_bsa = tmp_path / "output.bsa"
        rc, out, err = run_cli(["pack", str(test_dir), "--output", str(output_bsa)])
        assert rc == 0

        reader = BSAReader()
        archive = reader.load(output_bsa)
        assert len(archive.files) == 1
        assert "a\\b\\c\\deep.txt" in archive.files[0].name

    def test_pack_missing_input(self, tmp_path: Path) -> None:
        rc, out, err = run_cli(["pack", "/nonexistent/dir", "--output", str(tmp_path / "out.bsa")])
        assert rc == 1
        assert "not found" in err.lower()

    def test_pack_empty_dir(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "empty"
        test_dir.mkdir()

        output_bsa = tmp_path / "output.bsa"
        rc, out, err = run_cli(["pack", str(test_dir), "--output", str(output_bsa)])
        assert rc == 1
        assert "No files" in err

    def test_pack_roundtrip(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "input"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "meshes" / "actor").mkdir(parents=True)
        (test_dir / "textures" / "actor").mkdir(parents=True)
        (test_dir / "scripts").mkdir(parents=True)
        (test_dir / "meshes" / "actor" / "test.nif").write_bytes(b"NIF data here")
        (test_dir / "textures" / "actor" / "test.dds").write_bytes(b"DDS texture data" * 100)
        (test_dir / "scripts" / "test.pex").write_bytes(b"PEX script data")

        input_bsa = tmp_path / "input.bsa"
        rc, _, _ = run_cli(["pack", str(test_dir), "--output", str(input_bsa)])
        assert rc == 0

        output_dir = tmp_path / "output"
        rc, _, _ = run_cli(["unpack", str(input_bsa), "--output", str(output_dir)])
        assert rc == 0

        for root, _, files in os.walk(test_dir):
            for fname in files:
                full = Path(root) / fname
                rel = full.relative_to(test_dir).as_posix().replace("/", "\\")
                expected = full.read_bytes()

                out_path = output_dir / rel.replace("\\", "/")
                assert out_path.exists(), f"Missing: {rel}"
                actual = out_path.read_bytes()
                assert actual == expected, f"Content mismatch: {rel}"


# ---------------------------------------------------------------------------
# Error tests
# ---------------------------------------------------------------------------


class TestCLIErrors:
    def test_no_command(self) -> None:
        rc, out, err = run_cli([])
        assert rc == 1
        assert "usage:" in out.lower() or "positional arguments:" in out.lower()

    def test_invalid_subcommand(self) -> None:
        rc, out, err = run_cli(["invalid"])
        assert rc != 0
