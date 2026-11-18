# Game BSA Test Suite

Integration tests and utilities for comparing `py_bsa` against BSArch using real game BSA/BA2 files.

## Setup

### Prerequisites

- Python 3.10+ with dependencies from `requirements.txt`
- Wine (for running BSArch on Linux)
- BSArch from [TES5Edit](https://github.com/TES5Edit/TES5Edit)
- Game BSA/BA2 files

### Game File Layout

Organize game files under a base directory:

```
/mnt/bsa/
├── fallout3/
├── fallout4/
├── falloutnewvegas/
├── skyrimspecialedition/
├── morrowind/
├── oblivion/
└── skyrim/
```

## Running Comparisons

### Compare a Single File

```bash
python3 game_tests/compare_dump.py /path/to/archive.bsa
python3 game_tests/compare_dump.py /path/to/archive.ba2
```

Shows flag comparison, file comparison (paths, hashes, sizes, offsets), timing, and PASS/FAIL.

### Batch Compare a Directory

```bash
python3 game_tests/compare_dump.py --batch /path/to/games/
```

Recursively finds all `.bsa` and `.ba2` files and compares each against BSArch.

### Round-trip Test

> **Note:** The packer is a work in progress. Round-trip tests (unpack → repack → compare) may fail
> for TES4/FO3 formats due to known flag detection issues. The reader (unpack + dump) is verified.

```bash
python3 game_tests/roundtrip_test.py /path/to/archive.bsa
python3 game_tests/roundtrip_test.py /path/to/archive.ba2 --format fo4
```

Supported `--format` values: `tes3`, `tes4`, `tes5`, `sse`, `fo3`, `fnv`, `fo4`, `sf1` (auto-detected if omitted).

### Benchmark

```bash
python3 game_tests/bench.py dump /path/to/archive.bsa
python3 game_tests/bench.py unpack /path/to/archive.bsa
```

## BSArch Cache

Dump output is cached in `game_tests/cache/` to avoid re-running Wine. Cache is keyed by
(BSArch.exe MD5, BSA file MD5) and invalidated automatically if either changes.

## Current Results

### Dump Comparison (verified against BSArch v1.0)

```
$ python3 game_tests/compare_dump.py --batch "./Data/"

  Total: 243 files
  PASS: 243
  FAIL: 0
  RESULT: ALL TESTS PASSED
```

Reading and unpacking is verified across all tested formats. All 243 archives unpack and dump identically to BSArch v1.0.

Compression is handled per-format: zlib for TES5/FO3/FO4, LZ4F for SSE, LZ4 for Starfield v3, none for TES3/TES4.

### Unit Tests

```bash
pytest tests/ -v
```

## Issues and Pull Requests

Issues and PRs are welcome. See the main [README](../README.md) for more details.
