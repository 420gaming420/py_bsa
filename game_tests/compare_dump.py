#!/usr/bin/env python3
"""Compare py_bsa dump output against BSArch dump for a single BSA file.

BSArch dump results are cached to game_tests/cache/ to avoid re-running wine
every time. Cache key = (bsa_file_hash, bsarch_exe_hash).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from common import check_bsarch_exe

CACHE_DIR = Path(__file__).parent / "cache"

# Load BSArch path from environment (optional dotenv support)
try:
    from dotenv import load_dotenv
    load_dotenv()
    BSARCH_EXE_WIN = os.getenv("BSARCH_EXE_WIN", "./BSArch.exe")
except ImportError:
    BSARCH_EXE_WIN = os.getenv("BSARCH_EXE_WIN", "./BSArch.exe")
_bsarch_exe_hash_cache: str | None = None


def _file_hash(path: Path) -> str:
    """Return hex MD5 of a file's contents."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _bsarch_exe_hash() -> str:
    """Return hex MD5 of the BSArch.exe binary (cached)."""
    global _bsarch_exe_hash_cache
    if _bsarch_exe_hash_cache is not None:
        return _bsarch_exe_hash_cache
    import subprocess
    result = subprocess.run(
        ["winepath", "-u", BSARCH_EXE_WIN],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        _bsarch_exe_hash_cache = "winepath_failed"
        return _bsarch_exe_hash_cache
    linux_path = result.stdout.strip()
    if not linux_path or not Path(linux_path).exists():
        _bsarch_exe_hash_cache = "path_invalid"
        return _bsarch_exe_hash_cache
    _bsarch_exe_hash_cache = _file_hash(Path(linux_path))
    return _bsarch_exe_hash_cache


def _cache_key(bsa_path: Path) -> str:
    """Sanitized cache filename from a BSA path."""
    # Replace path separators and colons to make a safe filename
    key = str(bsa_path).replace("\\", "_").replace("/", "_").replace(":", "_")
    return key


def get_cached_bsarch_dump(bsa_path: Path) -> str | None:
    """Return cached BSArch dump if valid, else None."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{_cache_key(bsa_path)}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
        if data.get("bsarch_hash") != _bsarch_exe_hash():
            return None
        if data.get("bsa_hash") != _file_hash(bsa_path):
            return None
        return data.get("dump", "")
    except Exception:
        return None


def save_bsarch_cache(bsa_path: Path, dump: str) -> None:
    """Save BSArch dump to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{_cache_key(bsa_path)}.json"
    data = {
        "bsarch_hash": _bsarch_exe_hash(),
        "bsa_hash": _file_hash(bsa_path),
        "dump": dump,
    }
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


def get_bsarch_dump(bsa_path: Path) -> str:
    """Run BSArch.exe -dump on a BSA file, using cache when valid."""
    cached = get_cached_bsarch_dump(bsa_path)
    if cached is not None:
        return cached

    result = subprocess.run(
        ["wine", BSARCH_EXE_WIN, f"Z:{bsa_path}", "-dump"],
        capture_output=True,
        env={**os.environ, "WINEDEBUG": "-all"},
        timeout=120,
    )
    stdout = result.stdout.decode("latin-1")
    if result.returncode != 0:
        return f"BSARCH_ERROR: {result.stderr.decode('latin-1')}"

    # Cache the result
    try:
        save_bsarch_cache(bsa_path, stdout)
    except Exception:
        pass
    return stdout


def get_pybsa_dump(bsa_path: Path) -> str:
    """Run py_bsa dump command and return output lines."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "cli.py"),
         "dump", str(bsa_path)],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
        timeout=120,
    )
    if result.returncode != 0:
        return f"PYBSA_ERROR: {result.stderr}"
    return result.stdout


def normalize_dump(output: str, bsa_path: Path) -> list[str]:
    """Normalize dump output for comparison.

    Skip BSArch header/help text, keep only the structured dump lines.
    """
    # Normalize line endings: BSArch on Windows uses \r\n, py_bsa uses \n
    output = output.replace("\r\n", "\n").replace("\r", "\n")
    lines = output.strip().split("\n")
    normalized = []
    skip_header = True
    for line in lines:
        stripped = line.strip()
        # Skip BSArch banner and help text
        if skip_header:
            if stripped.startswith("Archive Name:") or stripped.startswith("Format:"):
                skip_header = False
            continue
        # Skip empty lines between header and data
        if not stripped:
            continue
        normalized.append(line)
    return normalized


def split_flags_and_files(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split normalized dump into flag lines and file lines.

    Flag lines are lines that contain flag names (e.g., 'Include Directory Names', 'Meshes').
    File lines are lines that contain file paths or hash/size info.
    Also filters out header lines (Format, Version, Files) and DirUnknown lines.
    """
    flag_lines = []
    file_lines = []

    # Flag patterns - lines that contain archive/file flag names
    # BA2 dumps have no flag table; only TES3/TES4/BSA dumps do.
    # Flag lines are indented (start with spaces), path lines don't.
    flag_patterns = [
        'Archive Flags:', 'File Flags:',
        'Include Directory Names', 'Include File Names', 'Compressed',
        'Retain Directory Names', 'Retain File Names', 'Retain File Name Offsets',
        'XBox 360 Archive', 'Retain Strings During Startup',
        'Embed File Names', 'XMem Codec',
        'Bit 9', 'Bit 10',
        'Meshes', 'Textures', 'Menus', 'Sounds', 'Voices',
        'Shaders', 'Trees', 'Fonts', 'Misc',
    ]

    # Header patterns to filter out
    header_patterns = [
        'Format:', 'Version:', 'Files:',
    ]

    for line in lines:
        stripped = line.strip()
        # Skip header lines
        if any(pattern in stripped for pattern in header_patterns):
            continue
        # Skip BSArch Compressed header line (new in BSArch v1.0)
        if stripped.startswith('Compressed:'):
            continue
        # Skip DirUnknown lines
        if 'DirUnknown' in stripped:
            continue
        # Skip BSArch Warning lines (py_bsa doesn't emit these)
        if stripped.startswith('Warning:'):
            continue
        # Check if this is a flag line: must be indented AND contain a flag keyword
        # Path lines (e.g. 'Textures\CreationClub\...') are not indented
        is_flag = line.startswith(' ') and any(pattern in stripped for pattern in flag_patterns)
        if is_flag:
            flag_lines.append(line)
        else:
            file_lines.append(line)

    return flag_lines, file_lines


def normalize_flags(lines: list[str]) -> list[str]:
    """Normalize flag lines by replacing excessive whitespace with newlines.

    Rules:
    - Replace runs of 2+ spaces/tabs with newlines to split combined flag lines
      into individual flag entries.
    - Each resulting flag must be on its own line with NO leading or trailing
      whitespace (strip each part).
    - There must be exactly one flag per output line — no whitespace padding
      between flag names.
    - Single spaces within a flag name (e.g. 'Include File Names') are preserved;
      only 2+ consecutive spaces/tabs trigger a split.
    """
    normalized = []
    for line in lines:
        # Replace 2+ spaces/tabs with newline
        line = re.sub(r'[ \t]{2,}', '\n', line)
        # Split on newlines and strip each part
        parts = line.split('\n')
        for part in parts:
            part = part.strip()
            if part:
                normalized.append(part)
    return normalized


def compare_dumps(bsa_path: Path) -> tuple[int, float, float]:
    """Compare BSArch and py_bsa dumps for a single BSA file."""
    print(f"\n{'='*60}")
    print(f"Comparing: {bsa_path.name}")
    print(f"{'='*60}")

    # Get BSArch dump (cached)
    t_bsarch = time.perf_counter()
    cache_was_hit = get_cached_bsarch_dump(bsa_path) is not None
    try:
        bsarch_out = get_bsarch_dump(bsa_path)
    except subprocess.TimeoutExpired:
        print(f"  BSArch timeout!")
        return 1
    except Exception as e:
        print(f"  BSArch error: {e}")
        return 1
    bsarch_time = time.perf_counter() - t_bsarch
    bsarch_label = "(cache hit)" if cache_was_hit else "(first run)"

    if bsarch_out.startswith("BSARCH_ERROR"):
        print(f"  {bsarch_out}")
        return 1

    # Get py_bsa dump (never cached)
    t_pybsa = time.perf_counter()
    try:
        pybsa_out = get_pybsa_dump(bsa_path)
    except subprocess.TimeoutExpired:
        print(f"  py_bsa timeout!")
        return 1
    except Exception as e:
        print(f"  py_bsa error: {e}")
        return 1
    pybsa_time = time.perf_counter() - t_pybsa

    # Normalize
    bsarch_norm = normalize_dump(bsarch_out, bsa_path)
    pybsa_norm = normalize_dump(pybsa_out, bsa_path)

    # Split into flags and files
    bsarch_flags, bsarch_files = split_flags_and_files(bsarch_norm)
    pybsa_flags, pybsa_files = split_flags_and_files(pybsa_norm)

    # Normalize flags (split combined lines)
    bsarch_flags_norm = normalize_flags(bsarch_flags)
    pybsa_flags_norm = normalize_flags(pybsa_flags)

    # Compare flags
    print(f"\n--- Flag comparison ---")
    flag_diffs = []
    max_flags = max(len(bsarch_flags_norm), len(pybsa_flags_norm))
    for i in range(max_flags):
        a = bsarch_flags_norm[i] if i < len(bsarch_flags_norm) else "<missing>"
        b = pybsa_flags_norm[i] if i < len(pybsa_flags_norm) else "<missing>"
        if a != b:
            flag_diffs.append((i, a, b))

    if not flag_diffs:
        print(f"  PASS: Flags are identical")
    else:
        print(f"  FAIL: {len(flag_diffs)} flag differences found")
        for i, a, b in flag_diffs[:20]:
            print(f"    Line {i}:")
            print(f"      BSArch: '{a}'")
            print(f"      py_bsa: '{b}'")

    # Compare files
    print(f"\n--- File comparison ---")
    file_diffs = []
    max_files = max(len(bsarch_files), len(pybsa_files))
    for i in range(max_files):
        a = bsarch_files[i] if i < len(bsarch_files) else "<missing>"
        b = pybsa_files[i] if i < len(pybsa_files) else "<missing>"
        if a != b:
            file_diffs.append((i, a, b))

    if not file_diffs:
        print(f"  PASS: Files are identical")
    else:
        print(f"  FAIL: {len(file_diffs)} file difference(s) found")
        for i, a, b in file_diffs[:20]:
            print(f"    Line {i}:")
            print(f"      BSArch: {a}")
            print(f"      py_bsa: {b}")

    # Summary
    print(f"\n--- Summary ---")
    print(f"  BSArch: {len(bsarch_flags_norm)} flags, {len(bsarch_files)} file lines")
    print(f"  py_bsa: {len(pybsa_flags_norm)} flags, {len(pybsa_files)} file lines")
    print(f"  BSArch time: {bsarch_time:.3f}s {bsarch_label}")
    print(f"  py_bsa time: {pybsa_time:.3f}s")

    if not flag_diffs and not file_diffs:
        print(f"  PASS: Dumps are identical")
        return 0, bsarch_time, pybsa_time
    else:
        print(f"  FAIL: {len(flag_diffs)} flag diffs, {len(file_diffs)} file diffs")
        return 1, bsarch_time, pybsa_time


def batch_compare(root_dir: Path) -> int:
    """Recursively compare all .bsa and .ba2 files in a directory tree."""
    # Find all BSA/BA2 files
    bsa_files = list(root_dir.rglob("*.bsa")) + list(root_dir.rglob("*.ba2"))
    bsa_files.sort()

    if not bsa_files:
        print(f"No .bsa or .ba2 files found in {root_dir}")
        return 1

    print(f"Found {len(bsa_files)} archive files in {root_dir}")
    print(f"{'='*60}")

    pass_count = 0
    fail_count = 0
    error_count = 0
    total_bsarch = 0.0
    total_pybsa = 0.0

    for bsa_path in bsa_files:
        t_start = time.perf_counter()
        result, bt, pt = compare_dumps(bsa_path)
        elapsed = time.perf_counter() - t_start
        total_bsarch += bt
        total_pybsa += pt
        if result == 0:
            pass_count += 1
        elif result == 1:
            fail_count += 1
        else:
            error_count += 1
        print(f"  [{pass_count + fail_count + error_count}/{len(bsa_files)}] "
              f"{bsa_path.name}: {'PASS' if result == 0 else 'FAIL'} ({elapsed:.3f}s)")

    print(f"\n{'='*60}")
    print(f"BATCH SUMMARY")
    print(f"{'='*60}")
    print(f"  Total: {len(bsa_files)} files")
    print(f"  PASS: {pass_count}")
    print(f"  FAIL: {fail_count}")
    print(f"  ERROR: {error_count}")
    if pass_count + fail_count + error_count > 0:
        avg = (total_bsarch + total_pybsa) / (pass_count + fail_count + error_count)
        if avg >= 1.0:
            print(f"  Avg per file: {avg:.3f}s")
        else:
            print(f"  Avg per file: {avg * 1000:.1f}ms")

    if fail_count == 0 and error_count == 0:
        print(f"  RESULT: ALL TESTS PASSED")
        return 0
    else:
        print(f"  RESULT: SOME TESTS FAILED")
        return 1


def main():
    check_bsarch_exe(BSARCH_EXE_WIN)

    parser = argparse.ArgumentParser(description="Compare BSArch and py_bsa dumps")
    parser.add_argument("path", help="Path to BSA file or directory (use --batch for directory)")
    parser.add_argument("--batch", action="store_true", help="Recursively compare all .bsa/.ba2 files in directory")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: {path} not found")
        return 1

    if args.batch:
        return batch_compare(path)
    else:
        return compare_dumps(path)


if __name__ == "__main__":
    sys.exit(main())
