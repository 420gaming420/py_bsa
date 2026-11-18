# Tests for BSA hash functions with known vectors from bsa C++ library
# (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8).

from __future__ import annotations

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logic.hasher import TES3Hash, TES4Hash, BA2Hash


# ---------------------------------------------------------------------------
# TES3 hash tests
# ---------------------------------------------------------------------------


class TestTES3Hash:
    """Test TES3 (Morrowind) hash function against bsa C++ test vectors
    (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""

    def test_known_vectors(self) -> None:
        """Verify against known test vectors from bsa::tes3::hashing tests
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
            assert h == expected, f"Expected 0x{expected:016X}, got 0x{h:016X}"

    def test_case_insensitive(self) -> None:
        h1 = TES3Hash.hash("Meshes\\Actor\\Test.Nif")
        h2 = TES3Hash.hash("meshes\\actor\\test.nif")
        assert h1 == h2

    def test_forward_slash_normalization(self) -> None:
        h1 = TES3Hash.hash("meshes/actor/test.nif")
        h2 = TES3Hash.hash("meshes\\actor\\test.nif")
        assert h1 == h2

    def test_different_paths(self) -> None:
        h1 = TES3Hash.hash("meshes\\actor\\test.nif")
        h2 = TES3Hash.hash("meshes\\actor\\other.nif")
        assert h1 != h2

    def test_empty_path(self) -> None:
        h = TES3Hash.hash("")
        assert isinstance(h, int)

    def test_single_char(self) -> None:
        h = TES3Hash.hash("a")
        assert isinstance(h, int)
        assert h > 0

    def test_unicode(self) -> None:
        """Unicode paths should not crash."""
        h = TES3Hash.hash("meshes/\u00e9test.nif")
        assert isinstance(h, int)

    def test_path_with_spaces(self) -> None:
        h = TES3Hash.hash("meshes/r/xkwama worker.nif")
        assert isinstance(h, int)


# ---------------------------------------------------------------------------
# TES4 hash tests
# ---------------------------------------------------------------------------


class TestTES4Hash:
    """Test TES4+ (Oblivion/Fallout/Skyrim) hash function against bsa C++ vectors
    (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""

    def test_directory_vectors(self) -> None:
        """Directory hash vectors from bsa::tes4::hashing tests
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        vectors = [
            ("textures/armor/amuletsandrings/elder council", 0x04BC422C742C696C),
            ("sound/voice/skyrim.esm/maleuniquedbguardian", 0x594085AC732B616E),
            ("textures/architecture/windhelm", 0xC1D97EBE741E6C6D),
        ]
        for path, expected in vectors:
            h = TES4Hash.hash_directory(path)
            assert h == expected, f"Expected 0x{expected:016X}, got 0x{h:016X}"

    def test_file_vectors(self) -> None:
        """File hash vectors from bsa::tes4::hashing tests."""
        vectors = [
            ("darkbrotherhood__0007469a_1.fuz", 0x011F11B0641B5F31),
            ("elder_council_amulet_n.dds", 0xDC531E2F6516DFEE),
            ("testtoddquest_testtoddhappy_00027fa2_1.mp3", 0xDE0301EE74265F31),
        ]
        for path, expected in vectors:
            h = TES4Hash.hash_file(path)
            assert h == expected, f"Expected 0x{expected:016X}, got 0x{h:016X}"

    def test_case_insensitive(self) -> None:
        h1 = TES4Hash.hash_file("Meshes\\Actor\\Test.Nif")
        h2 = TES4Hash.hash_file("meshes\\actor\\test.nif")
        assert h1 == h2

    def test_forward_slash_normalization(self) -> None:
        h1 = TES4Hash.hash_file("meshes/actor/test.nif")
        h2 = TES4Hash.hash_file("meshes\\actor\\test.nif")
        assert h1 == h2

    def test_strips_directory_for_file_hash(self) -> None:
        """hash_file should only hash the filename, not the full path."""
        h1 = TES4Hash.hash_file("meshes\\actor\\test.nif")
        h2 = TES4Hash.hash_file("textures\\actor\\test.nif")
        assert h1 == h2

    def test_different_files(self) -> None:
        h1 = TES4Hash.hash_file("meshes\\actor\\test.nif")
        h2 = TES4Hash.hash_file("meshes\\actor\\other.nif")
        assert h1 != h2

    def test_single_char_stem(self) -> None:
        h = TES4Hash.hash_file("a.txt")
        assert isinstance(h, int)

    def test_no_extension(self) -> None:
        h = TES4Hash.hash_file("README")
        assert isinstance(h, int)

    def test_multiple_dots(self) -> None:
        """Files with multiple dots: only the last extension is used."""
        h1 = TES4Hash.hash_file("test.file.name.txt")
        h2 = TES4Hash.hash_file("test.file.name.txt")
        assert h1 == h2

    def test_special_chars(self) -> None:
        h = TES4Hash.hash_file("test-file_name.txt")
        assert isinstance(h, int)

    def test_empty_path(self) -> None:
        h = TES4Hash.hash_file("")
        assert h == 0

    def test_long_path(self) -> None:
        """Paths >= 260 chars should hash to 0."""
        h = TES4Hash.hash_file("a" * 300)
        assert h == 0

    def test_directory_edge_cases(self) -> None:
        """Edge cases for directory hashing."""
        assert TES4Hash.hash_directory("") == TES4Hash.hash_directory(".")
        h1 = TES4Hash.hash_directory("\\")
        h2 = TES4Hash.hash_directory("")
        assert h1 == h2
        h1 = TES4Hash.hash_directory("meshes\\actor\\")
        h2 = TES4Hash.hash_directory("meshes\\actor")
        assert h1 == h2
        h1 = TES4Hash.hash_directory("\\meshes\\actor")
        h2 = TES4Hash.hash_directory("meshes\\actor")
        assert h1 == h2
        h = TES4Hash.hash_directory("a" * 300)
        assert h == TES4Hash.hash_directory(".")

    def test_root_paths_included(self) -> None:
        h1 = TES4Hash.hash_directory("C:\\foo\\bar\\baz")
        h2 = TES4Hash.hash_directory("foo/bar/baz")
        assert h1 != h2

    def test_long_directory_equivalent_to_empty(self) -> None:
        long_path = "a" * 300
        assert TES4Hash.hash_directory(long_path) == TES4Hash.hash_directory("")

    def test_long_file_stem_fails(self) -> None:
        good = TES4Hash.hash_file("a" * 259 + ".txt")
        bad = TES4Hash.hash_file("a" * 260 + ".txt")
        assert good != 0
        assert bad == 0

    def test_long_extension_fails(self) -> None:
        good = TES4Hash.hash_file("test.123456789ABCDE")
        bad = TES4Hash.hash_file("test.123456789ABCDEF")
        assert good != 0
        assert bad == 0


# ---------------------------------------------------------------------------
# BA2 hash tests
# ---------------------------------------------------------------------------


class TestBA2Hash:
    """Test BA2 (Fallout 4) hash function against bsa C++ test vectors
    (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""

    def test_known_vectors(self) -> None:
        """FO4 hash vectors from bsa::fo4::hashing tests
        (github.com/Ryan-rsm-McKenzie/bsa@b6ab3c8)."""
        vectors = [
            (
                "Sound\\Voice\\Fallout4.esm\\RobotMrHandy\\María_M.fuz",
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
            assert dir_hash == exp_dir, f"Dir: expected 0x{exp_dir:08X}, got 0x{dir_hash:08X} for {path}"
            assert file_hash == exp_file, f"File: expected 0x{exp_file:08X}, got 0x{file_hash:08X} for {path}"
            assert ext_hash == exp_ext, f"Ext: expected 0x{exp_ext:08X}, got 0x{ext_hash:08X} for {path}"

    def test_extension_raw_bytes(self) -> None:
        """Extension hash is raw 4-byte LE u32, not CRC32."""
        assert BA2Hash.hash_extension("test.txt") == 0x00747874
        assert BA2Hash.hash_extension("test.dds") == 0x00736464
        assert BA2Hash.hash_extension("test.nif") == 0x0066696E
        assert BA2Hash.hash_extension("test.pex") == 0x00786570
        assert BA2Hash.hash_extension("test.fuz") == 0x007A7566
        assert BA2Hash.hash_extension("test") == 0

    def test_empty_path(self) -> None:
        assert BA2Hash.hash_directory("") == 0
        assert BA2Hash.hash_file("") == 0


# ---------------------------------------------------------------------------
# Hash consistency between file and directory hashes
# ---------------------------------------------------------------------------


class TestHashConsistency:
    """Test that file hashes are consistent with directory + file hashes."""

    def test_file_hash_includes_directory(self) -> None:
        """hash_file should produce a different result than hash_directory."""
        dir_hash = TES4Hash.hash_directory("meshes\\actor")
        file_hash = TES4Hash.hash_file("meshes\\actor\\test.nif")
        assert dir_hash != file_hash

    def test_same_filename_different_directories(self) -> None:
        """Same filename in different directories produces same file hash
        (hash_file only hashes the filename, not the directory)."""
        h1 = TES4Hash.hash_file("meshes\\actor\\test.nif")
        h2 = TES4Hash.hash_file("textures\\actor\\test.nif")
        assert h1 == h2
