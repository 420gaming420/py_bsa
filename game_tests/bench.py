# Benchmark utility for py_bsa CLI commands
# Times each individual step and reports per-step breakdowns

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _print_benchmark_table(
    entries: list[tuple[str, float, dict[str, float]]],
    step_names: list[str],
) -> None:
    """Print a benchmark table similar to the reference example."""
    if not entries:
        return
    func_col = max(len(e[0]) for e in entries) + 2
    step_cols = {s: max(len(s), max(len(e[2].get(s, 0.0)) for e in entries) if entries else 0)
                 for s in step_names}
    total_w = max(len("TOTAL"), max(len(f"{e[1]:.3f}") for e in entries)) + 2

    header = "FUNC".ljust(func_col)
    for s in step_names:
        header += s.rjust(step_cols[s] + 1)
    header += "TOTAL".rjust(total_w)
    print(header)
    sep = "-" * len(header)
    print(sep)

    for name, total, steps in entries:
        line = name.ljust(func_col)
        for s in step_names:
            line += f"{steps.get(s, 0.0):.{min(5, step_cols[s])}f}".rjust(step_cols[s] + 1)
        line += f"{total:.3f}".rjust(total_w)
        print(line)

    print(sep)

    # Summary stats
    print()
    print("=" * len(header))
    print("SUMMARY")
    print(sep)
    col_w = max(len(s) for s in ["Step"] + step_names + ["Total"]) + 2
    avg_w, min_w, max_w, p90_w, p95_w = 8, 8, 8, 8, 8
    hdr = "Step".ljust(col_w)
    for w in [avg_w, min_w, max_w, p90_w, p95_w]:
        hdr += ("AVG" if w == avg_w else "MIN" if w == min_w else "MAX" if w == max_w else "P90" if w == p90_w else "P95").rjust(w)
    print(hdr)
    print("-" * len(hdr))
    totals = {s: sum(e[2].get(s, 0.0) for e in entries) for s in step_names}
    totals["total"] = sum(e[1] for e in entries)
    times = [e[1] for e in entries]
    sorted_times = sorted(times)
    n = len(sorted_times)

    for label, key in [("find", None), ("load", None), ("dump", None), ("total", None)]:
        if key is None:
            key = label
        t = totals.get(key, 0.0)
        avg = t / n if n else 0.0
        mn = min(times) if times else 0.0
        mx = max(times) if times else 0.0
        p90 = sorted_times[int(n * 0.9)] if n else 0.0
        p95 = sorted_times[int(n * 0.95)] if n else 0.0
        row = label.ljust(col_w)
        for w, val in [(avg_w, avg), (min_w, mn), (max_w, mx), (p90_w, p90), (p95_w, p95)]:
            row += f"{val:.3f}".rjust(w)
        print(row)

    print("=" * len(header))


class BenchmarkTimer:
    """Context-manager-like timer that tracks multiple named steps."""

    def __init__(self, step_names: list[str]):
        self._steps = {s: 0.0 for s in step_names}
        self._active: str | None = None
        self._start: float = 0.0

    def start(self, step: str) -> None:
        self._active = step
        self._start = time.perf_counter()

    def stop(self) -> float:
        if self._active is None:
            return 0.0
        elapsed = time.perf_counter() - self._start
        self._steps[self._active] += elapsed
        self._active = None
        return elapsed

    @property
    def steps(self) -> dict[str, float]:
        return dict(self._steps)

    @property
    def total(self) -> float:
        return sum(self._steps.values())


def bench_dump(args: argparse.Namespace) -> int:
    """Dump with benchmarking."""
    from logic.reader import BSAReader  # local import to avoid circular

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    print(f"[*] Benchmarking dump: {input_path.name}")
    print("=" * 72)

    timer = BenchmarkTimer(["load", "dump"])

    timer.start("load")
    reader = BSAReader()
    try:
        archive = reader.load(input_path)
    except Exception as e:
        timer.stop()
        print(f"Error reading BSA: {e}", file=sys.stderr)
        return 1
    load_time = timer.stop()

    timer.start("dump")
    output = reader.dump()
    dump_time = timer.stop()

    # Print output
    print(output)

    # Print benchmark results
    print()
    print("=" * 72)
    print("BENCHMARK RESULTS")
    print("=" * 72)
    print(f"  load:   {load_time:.3f}s")
    print(f"  dump:   {dump_time:.3f}s")
    print(f"  total:  {load_time + dump_time:.3f}s")
    print(f"  files:  {len(archive.files)}")
    print(f"  lines:  {len(output.splitlines())}")

    return 0


def bench_unpack(args: argparse.Namespace) -> int:
    """Unpack with benchmarking."""
    from logic.reader import BSAReader  # local import
    from logic.bsa import ArchiveFormat  # local import

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output) if args.output else input_path.parent / input_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Benchmarking unpack: {input_path.name}")
    print(f"    -> {output_dir}")
    print("=" * 72)

    timer = BenchmarkTimer(["load", "extract"])

    # Load
    timer.start("load")
    reader = BSAReader()
    try:
        archive = reader.load(input_path)
    except Exception as e:
        timer.stop()
        print(f"Error reading BSA: {e}", file=sys.stderr)
        return 1
    load_time = timer.stop()

    # Extract
    timer.start("extract")
    extracted = 0
    for entry in archive.files:
        try:
            data = reader.read_file(entry)
        except Exception as e:
            if args.verbose:
                print(f"  Warning: Failed to read {entry.name}: {e}", file=sys.stderr)
            continue

        out_path = output_dir / entry.name.replace("\\", "/")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        extracted += 1

    extract_time = timer.stop()

    print(f"\nExtracted {extracted} files to: {output_dir}")

    # Print benchmark results
    print()
    print("=" * 72)
    print("BENCHMARK RESULTS")
    print("=" * 72)
    print(f"  load:      {load_time:.3f}s")
    print(f"  extract:   {extract_time:.3f}s")
    print(f"  total:     {load_time + extract_time:.3f}s")
    print(f"  files:     {len(archive.files)}")
    print(f"  extracted: {extracted}")

    return 0


def bench_pack(args: argparse.Namespace) -> int:
    """Pack with benchmarking."""
    import os as _os

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
    }
    fmt = format_map.get(args.format.lower(), ArchiveFormat.FO3)

    print(f"[*] Benchmarking pack: {input_dir.name}")
    print(f"    -> {output_path.name}")
    print(f"    format: {fmt.name}, compress: {args.compress}")
    print("=" * 72)

    timer = BenchmarkTimer(["collect", "hash", "write"])

    # Collect files
    timer.start("collect")
    files_data: list[tuple[str, bytes]] = []
    for root, _, files in _os.walk(input_dir):
        for fname in sorted(files):
            full_path = Path(root) / fname
            rel_path = full_path.relative_to(input_dir)
            bsa_name = rel_path.as_posix().replace("/", "\\")
            try:
                with open(full_path, "rb") as f:
                    data = f.read()
                files_data.append((bsa_name, data))
            except Exception as e:
                print(f"  Warning: Failed to read {full_path}: {e}", file=sys.stderr)
    collect_time = timer.stop()

    if not files_data:
        print("Error: No files found in directory", file=sys.stderr)
        return 1

    # Hash + build archive (combined since hasher is inline)
    timer.start("hash")
    from logic.writer import BSAWriter
    writer = BSAWriter.for_format(fmt)
    writer.compress = args.compress
    if args.compress:
        writer.compression_level = args.level

    for bsa_name, data in files_data:
        writer.add_file(bsa_name, data)
    hash_time = timer.stop()

    # Write
    timer.start("write")
    try:
        writer.save(output_path)
    except Exception as e:
        timer.stop()
        print(f"Error writing BSA: {e}", file=sys.stderr)
        return 1
    write_time = timer.stop()

    print(f"\nPacked {len(files_data)} files to: {output_path}")
    if args.verbose:
        print(f"  Format: {fmt.name}")
        print(f"  Compressed: {'yes' if args.compress else 'no'}")
        print(f"  Output size: {output_path.stat().st_size:,} bytes")

    # Print benchmark results
    print()
    print("=" * 72)
    print("BENCHMARK RESULTS")
    print("=" * 72)
    print(f"  collect:  {collect_time:.3f}s")
    print(f"  hash:     {hash_time:.3f}s")
    print(f"  write:    {write_time:.3f}s")
    print(f"  total:    {collect_time + hash_time + write_time:.3f}s")
    print(f"  files:    {len(files_data)}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bench.py",
        description="Benchmark py_bsa CLI commands",
    )
    subparsers = parser.add_subparsers(dest="command")

    # dump
    dump_parser = subparsers.add_parser("dump", help="Benchmark dump command")
    dump_parser.add_argument("input", help="Path to input .bsa file")

    # unpack
    unpack_parser = subparsers.add_parser("unpack", help="Benchmark unpack command")
    unpack_parser.add_argument("input", help="Path to input .bsa file")
    unpack_parser.add_argument("--output", "-o", default=None, help="Output directory")
    unpack_parser.add_argument("--verbose", "-v", action="store_true")

    # pack
    pack_parser = subparsers.add_parser("pack", help="Benchmark pack command")
    pack_parser.add_argument("input", help="Path to input directory")
    pack_parser.add_argument("--output", "-o", default=None, help="Output .bsa path")
    pack_parser.add_argument("--format", "-f", default="fo3", help="BSA format")
    pack_parser.add_argument("--compress", "-c", action="store_true")
    pack_parser.add_argument("--level", type=int, default=9)
    pack_parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "dump":
        return bench_dump(args)
    elif args.command == "unpack":
        return bench_unpack(args)
    elif args.command == "pack":
        return bench_pack(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
