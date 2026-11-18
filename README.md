# py_bsa
Python library and CLI for **reading and writing** Bethesda Game Studios archive files (`.bsa` / `.ba2`).
Built on Linux for Linux with a modular architecture that's easy to drop into your own projects.
The archive dump output matches BSArch for all tested games.
The BSA/BA2 **reader** can parse archive headers, enumerate files, read file data, and unpack archives.
The BSA/BA2 **writer** is unfinished and untested. For creating or modifying archives, use [BSArch](https://github.com/TES5Edit/TES5Edit) instead.

## Format Support

| | Morrowind | Oblivion | Skyrim | Skyrim SE |
|---|---|---|---|---|
| dump | ✅ | ✅ | ✅ | ✅ |
| unpack | ✅ | ✅ | ✅* | ✅ |
| pack | ❌ | ❌ | ❌ | ❌ |

| | Fallout 3 | Fallout NV | Fallout 4 | Starfield |
|---|---|---|---|---|
| dump | ✅ | ✅ | ✅ | ❌ |
| unpack | ✅* | ✅* | 🚧 | ❌ |
| pack | ❌ | ❌ | ❌ | ❌ |

**Legend:**
- ✅ Complete
- ✅* Works but contains exceptions/fixes not in BSArch v1.0 or Windows
- 🚧 Work in progress
- ❌ Unfinished or untested

I compared the results with BSArch v1.0 which although is the **latest** release build, contains bugs that have been since fixed in the source code.
py_bsa references the fixed source code so when encountering known bugs the tester makes an exception and marks it as a pass with a warning to update BSArch.
Another issue I ran into was case sensitivity between windows and linux filesystems. Windows and in extension BSArch treat "Scripts/" and "scripts/" as the same folder which lead to false positive diff failures during unpacking. This was resolved with a path normalization post process that renamed all files and folders into lowercase, this is only done exclusively for the roundtrip tests.

To add support for FO4DDS and SF1DDS you will need the DirectXTex source code to understand the DDS file format: [https://github.com/microsoft/DirectXTex](https://github.com/microsoft/DirectXTex)

## Compression Support
Compression methods by format (mirrors `cArchiveCompressionTypes` from `wbBSArchive.pas:194-204` — TES5Edit@76d9d226):

| Format | Game | Compression |
|--------|------|-------------|
| `tes3` | Morrowind | none |
| `tes4` | Oblivion | zlib/selective |
| `fo3` | Fallout 3 / New Vegas / Skyrim LE | zlib |
| `sse` | Skyrim Special/AE Edition | LZ4F |
| `fo4` | Fallout 4 | zlib |
| `sf` | Starfield (v2) | zlib |
| `sf` | Starfield (v3) | LZ4 (via `CompressionMethod` header field) |
| `sf_dds` | Starfield DDS | LZ4 |

Requires `pip install lz4` for SSE and Starfield v3 archive support.

## Quick Start

No compile step needed, simply use `cli.py` directly:

```bash
# List files in an archive
./cli.py list Data/Morrowind.bsa

# Show archive metadata
./cli.py info Data/Morrowind.bsa

# Dump archive info (BSArch-compatible format)
./cli.py dump Data/Morrowind.bsa

# Unpack to disk
./cli.py unpack Data/Morrowind.bsa
#or
./cli.py unpack Data/Morrowind.bsa -o ./extracted

# Recursively unpack all archives in a directory
./cli.py unpack --batch Data/
```

## Using the library in your project

The code is split into small, focused modules under `src/logic/`. Just add `src/` to your Python path:

```python
import sys
sys.path.insert(0, "src")

from logic.reader import BSAReader
from logic.hasher import TES3Hash, TES4Hash, BA2Hash
from logic.bsa import ArchiveFormat, BSAFileEntry

# Read an archive
reader = BSAReader("MyMod.bsa")
archive = reader.archive

print(f"Format: {archive.fmt.name}")
print(f"Files:  {len(archive.files)}")

for entry in archive.files:
    print(f"  {entry.name}  ({entry.compression.unpacked_size} bytes)")

# Read a single file's data
data = reader.read_file_by_name("meshes\\actor\\character.nif")
```

The modular layout makes it straightforward to borrow individual pieces:

| Module | What it does |
|--------|-------------|
| `logic/reader/core.py` | Archive opening and dispatch by format |
| `logic/reader/tes3.py` | Morrowind BSA parsing |
| `logic/reader/tes4.py` | Oblivion/Fallout/Skyrim BSA parsing |
| `logic/reader/ba2.py` | Fallout 4 / Starfield BA2 parsing |
| `logic/hasher/hashes.py` | TES3, TES4, and BA2 hash functions |
| `logic/bsa/constants.py` | Format constants, flag bits, magic numbers, compression method constants |
| `logic/bsa/models.py` | `BSAArchive`, `BSAFileEntry`, `CompressionFlag`, `CompressionMethod` dataclasses/enums |

## Verification against BSArch

I compared `py_bsa` dump output against BSArch v1.0 (from [TES5Edit](https://github.com/TES5Edit/TES5Edit)) across all available game files. The dumps are identical, including file hashes:

```
$ python3 game_tests/compare_dump.py --batch "./Data/" | tail -n 10

============================================================
BATCH SUMMARY
============================================================
  Total: 243 files
  PASS: 243
  FAIL: 0
  ERROR: 0
  Avg per file: 1.245s
  RESULT: ALL TESTS PASSED
```
All 243 (some games had the archive invalidator bsa) game files from`tes3` (Morrowind), `tes4` (Oblivion), `tes5` (Skyrim LE), `fo3`/`fnv` (Fallout 3/New Vegas), `sse` (Skyrim Special/AE Edition), and `fo4` (Fallout 4) dump identically.
User-created mod archives have not been tested so there may be edge cases that I missed.

## Running Tests

```bash
pytest
```

## More About This Project

This is a vibecoded project. I was able to unpack the vanilla game files, but have yet to test BSAs from mods.

**Purpose:** I made this for several reasons. Python is cross-platform and doesn't require complicated build environments — you simply install the required pip packages and run the code directly, no complicated compiling is needed. Another reason is for native Linux support, so that BSA files can be read and written on Linux without needing to use Wine. Making the code available as Python modules also allows easy reuse in other projects or scripts via import, which I plan to do for future projects.

I'm primarily interested in **reading** BSAs — specifically the game files from Fallout New Vegas — so little to no work has been done on the writer logic. I currently have no interest in the BA2 file format, but if you need it let me know and I'll go out of my way to make an attempt (no promises on quality).

## Issues and Pull Requests

Issues and PRs are welcome — especially for packer improvements and Starfield BA2 support since I personally don't own that game.

## References & Attribution

BSA format implementation based on:

- [TES5Edit / BSArch](https://github.com/TES5Edit/TES5Edit) (MPL 2.0) — archive structure, flag definitions, dump format
- [BSAopt](https://github.com/Ethatron/BSAopt) (MPL 1.1 / LGPL 3.0) — hash algorithms, compression
- [bsa (C++ library)](https://github.com/Ryan-rsm-McKenzie/bsa) (MIT) — hash test vectors, format docs
- [BethesdaLibrary](https://github.com/Ryan-rsm-McKenzie/BethesdaLibrary) (MIT) — format overview

## License

This project is mainly built from BSArch so it also uses the MPL 2.0 license.

## AI Disclosure

This project was developed with [opencode](https://github.com/anomalyco/opencode/releases) using a locally hosted [llama.cpp server](https://github.com/ggml-org/llama.cpp) as the provider with 256k context size running Qwen3.6 35B [Myric/KAT-Coder-V2.5-Dev-MTP-APEX-GGUF](https://huggingface.co/Myric/KAT-Coder-V2.5-Dev-MTP-APEX-GGUF) i-quality version.

This repo may contain inaccuracies, hallucinated logic, or suboptimal patterns introduced by the model. Scripts were manually reviewed and tested by a human operator.
Contributions and pull requests fixing bugs or making improvements are welcome.
