#!/usr/bin/env python3
# CLI thin wrapper — sets up path and delegates to logic

import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from logic.reader.core import BSAReader
from logic.writer.files import BSAWriter
from logic.hasher.hashes import TES3Hash, TES4Hash
from logic.bsa.models import ArchiveFormat, BSAArchive, BSAFileEntry, CompressionFlag
from ui.cli.parser import build_parser
from ui.cli import cmd_unpack, cmd_pack, cmd_info, cmd_list, cmd_dump
import argparse


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "unpack":
        return cmd_unpack(args)
    elif args.command == "pack":
        return cmd_pack(args)
    elif args.command == "info":
        return cmd_info(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "dump":
        return cmd_dump(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
