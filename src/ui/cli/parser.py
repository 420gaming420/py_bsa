# CLI argument parser setup

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="BSA archive unpacker/packer for Bethesda games (Fallout, Skyrim)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # unpack
    unpack_parser = subparsers.add_parser(
        "unpack",
        help="Unpack a BSA archive to a directory",
        epilog="examples:\n  ./cli.py unpack mod.bsa\n  ./cli.py unpack mod.bsa -o ./extracted\n  ./cli.py unpack --batch ./bsa_dir\n",
    )
    unpack_parser.add_argument("input", help="Path to input .bsa file (or directory for --batch)")
    unpack_parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory (default: <input_path>.stem/)",
    )
    unpack_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    unpack_parser.add_argument(
        "--batch", "-b", action="store_true",
        help="Unpack all .bsa files found in the input directory",
    )

    # pack
    pack_parser = subparsers.add_parser(
        "pack",
        help="Pack a directory into a BSA archive",
        epilog="examples:\n  ./cli.py pack ./my_mod -o mod.bsa\n  ./cli.py pack ./my_mod -o mod.bsa --compress\n  ./cli.py pack --batch ./mod_dirs\n",
    )
    pack_parser.add_argument("input", help="Path to input directory (or directory for --batch)")
    pack_parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output .bsa path (required without --batch; default: <input_path>.bsa)",
    )
    pack_parser.add_argument(
        "--format",
        "-f",
        choices=["tes3", "tes4", "tes5", "sse", "fo3", "fnv", "fo4", "sf1"],
        default="fo3",
        help="BSA format version (default: fo3)",
    )
    pack_parser.add_argument(
        "--compress", "-c", action="store_true", help="Enable zlib compression"
    )
    pack_parser.add_argument(
        "--level",
        type=int,
        default=9,
        help="Compression level 0-9 (default: 9, only used with --compress)",
    )
    pack_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    pack_parser.add_argument(
        "--batch", "-b", action="store_true",
        help="Pack each subdirectory of the input into its own .bsa file",
    )

    # info
    info_parser = subparsers.add_parser(
        "info",
        help="Show information about a BSA archive",
        epilog="example:\n  ./cli.py info mod.bsa\n",
    )
    info_parser.add_argument("input", help="Path to input .bsa file")

    # list
    list_parser = subparsers.add_parser(
        "list",
        help="List files in a BSA archive",
        epilog="example:\n  ./cli.py list mod.bsa\n",
    )
    list_parser.add_argument("input", help="Path to input .bsa file")

    # dump
    dump_parser = subparsers.add_parser(
        "dump",
        help="Dump BSA archive info in BSArch-compatible format",
        epilog="example:\n  ./cli.py dump mod.bsa\n",
    )
    dump_parser.add_argument("input", help="Path to input .bsa file")

    return parser
