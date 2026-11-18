# CLI commands for BSA unpack/pack

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from logic.bsa import ArchiveFormat
from logic.reader import BSAReader
from logic.writer import BSAWriter


def cmd_unpack(args: argparse.Namespace) -> int:
    """Unpack a BSA archive to a directory."""
    if args.batch:
        return cmd_unpack_batch(args)

    return _cmd_unpack_single(args)


def _cmd_unpack_single(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output) if args.output else input_path.parent / input_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = BSAReader()
    try:
        archive = reader.load(input_path)
    except Exception as e:
        print(f"Error reading BSA: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(reader.info())
        print(f"\nUnpacking {len(archive.files)} files to: {output_dir}")

    extracted = 0
    for entry in archive.files:
        try:
            data = reader.read_file(entry)
        except Exception as e:
            print(f"  Warning: Failed to read {entry.name}: {e}", file=sys.stderr)
            continue

        rel_name = entry.name.replace("\\", "/").lstrip("/")
        # Normalize directory case to match BSArch behavior (lowercase)
        # This prevents duplicate directories on case-sensitive filesystems
        parts = rel_name.split("/")
        normalized_parts = [part.lower() for part in parts[:-1]]  # Normalize directory parts
        normalized_parts.append(parts[-1])  # Keep filename case
        rel_name = "/".join(normalized_parts)

        out_path = output_dir / rel_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        extracted += 1

        if args.verbose:
            comp = "compressed" if entry.compression.compressed else "uncompressed"
            print(f"  [{extracted}/{len(archive.files)}] {entry.name} ({len(data)} bytes, {comp})")

    print(f"\nExtracted {extracted} files to: {output_dir}")
    return 0


def cmd_unpack_batch(args: argparse.Namespace) -> int:
    """Unpack all .bsa files found in the input directory."""
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"Error: Directory not found: {input_dir}", file=sys.stderr)
        return 1

    bsa_files = sorted(input_dir.glob("*.bsa"))
    if not bsa_files:
        print(f"Error: No .bsa files found in {input_dir}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Batch unpack: {len(bsa_files)} archive(s) in {input_dir}")

    success = 0
    failed = 0
    for bsa_path in bsa_files:
        # In batch mode, output defaults to <bsa_stem>/ next to the archive
        output_dir = input_dir / bsa_path.stem
        if args.verbose:
            print(f"\n  {bsa_path.name} -> {output_dir}/")
        # Reuse single unpack with a temporary namespace
        batch_args = argparse.Namespace(
            input=str(bsa_path),
            output=str(output_dir),
            verbose=args.verbose,
            batch=False,
        )
        rc = _cmd_unpack_single(batch_args)
        if rc == 0:
            success += 1
        else:
            failed += 1

    print(f"\nBatch unpack complete: {success} succeeded, {failed} failed")
    return 0 if failed == 0 else 1


def cmd_pack(args: argparse.Namespace) -> int:
    """Pack a directory into a BSA archive."""
    if args.batch:
        return cmd_pack_batch(args)

    return _cmd_pack_single(args)


def _cmd_pack_single(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Error: Directory not found: {input_dir}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if not output_path.suffix:
        output_path = output_path.with_suffix(".bsa")

    format_map = {
        "tes3": ArchiveFormat.TES3,
        "tes4": ArchiveFormat.TES4,
        "tes5": ArchiveFormat.SSE,
        "sse": ArchiveFormat.SSE,
        "fo3": ArchiveFormat.FO3,
        "fnv": ArchiveFormat.FO3,
        "fo4": ArchiveFormat.FO4,
        "sf1": ArchiveFormat.SF,
    }
    fmt = format_map.get(args.format.lower(), ArchiveFormat.FO3)

    if fmt == ArchiveFormat.TES3:
        writer = BSAWriter.for_morrowind()
    elif fmt == ArchiveFormat.FO4:
        writer = BSAWriter.for_fallout4()
    elif fmt == ArchiveFormat.SF:
        writer = BSAWriter.for_starfield()
    elif fmt == ArchiveFormat.TES4:
        writer = BSAWriter.for_oblivion()
    elif fmt == ArchiveFormat.SSE:
        writer = BSAWriter.for_skyrim()
    else:
        writer = BSAWriter.for_fallout3()

    writer.compress = args.compress
    if args.compress:
        writer.compression_level = args.level

    file_count = 0
    for root, _, files in os.walk(input_dir):
        for fname in sorted(files):
            full_path = Path(root) / fname
            rel_path = full_path.relative_to(input_dir)
            bsa_name = rel_path.as_posix().replace("/", "\\")

            try:
                with open(full_path, "rb") as f:
                    data = f.read()
                writer.add_file(bsa_name, data)
                file_count += 1
                if args.verbose:
                    print(f"  Adding: {bsa_name} ({len(data)} bytes)")
            except Exception as e:
                print(f"  Warning: Failed to read {full_path}: {e}", file=sys.stderr)

    if file_count == 0:
        print("Error: No files found in directory", file=sys.stderr)
        return 1

    try:
        writer.save(output_path)
    except Exception as e:
        print(f"Error writing BSA: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"\nPacked {file_count} files to: {output_path}")
        print(f"  Format: {fmt.name}")
        print(f"  Compressed: {'yes' if args.compress else 'no'}")
        if args.compress:
            print(f"  Compression level: {args.level}")
        print(f"  Output size: {output_path.stat().st_size:,} bytes")
    else:
        print(f"Packed {file_count} files to: {output_path}")

    return 0


def cmd_pack_batch(args: argparse.Namespace) -> int:
    """Pack each subdirectory of the input into its own .bsa file."""
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"Error: Directory not found: {input_dir}", file=sys.stderr)
        return 1

    subdirs = sorted([d for d in input_dir.iterdir() if d.is_dir()])
    if not subdirs:
        print(f"Error: No subdirectories found in {input_dir}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Batch pack: {len(subdirs)} directory(ies) in {input_dir}")

    success = 0
    failed = 0
    for subdir in subdirs:
        output_bsa = input_dir / f"{subdir.name}.bsa"
        if args.verbose:
            print(f"\n  {subdir.name}/ -> {output_bsa.name}")
        batch_args = argparse.Namespace(
            input=str(subdir),
            output=str(output_bsa),
            format=args.format,
            compress=args.compress,
            level=args.level,
            verbose=args.verbose,
            batch=False,
        )
        rc = _cmd_pack_single(batch_args)
        if rc == 0:
            success += 1
        else:
            failed += 1

    print(f"\nBatch pack complete: {success} succeeded, {failed} failed")
    return 0 if failed == 0 else 1


def cmd_info(args: argparse.Namespace) -> int:
    """Show information about a BSA archive."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    reader = BSAReader()
    try:
        archive = reader.load(input_path)
    except Exception as e:
        print(f"Error reading BSA: {e}", file=sys.stderr)
        return 1

    print(reader.info())
    print(f"\nFiles:")
    for i, entry in enumerate(archive.files, 1):
        comp = "C" if entry.compression.compressed else "U"
        print(f"  {i:4d} [{comp}] {entry.name} ({entry.compression.unpacked_size:,} bytes)")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List files in a BSA archive."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    reader = BSAReader()
    try:
        archive = reader.load(input_path)
    except Exception as e:
        print(f"Error reading BSA: {e}", file=sys.stderr)
        return 1

    files = reader.list_files()
    for name in files:
        print(name)

    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    """Dump BSA archive info in BSArch-compatible format."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    reader = BSAReader()
    try:
        archive = reader.load(input_path)
    except Exception as e:
        print(f"Error reading BSA: {e}", file=sys.stderr)
        return 1

    print(reader.dump())
    return 0
