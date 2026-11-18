"""Shared utilities for game_tests scripts."""

import os
import subprocess
import sys
from pathlib import Path


BSARCH_DOWNLOAD_URL = "https://github.com/TES5Edit/TES5Edit"


def check_bsarch_exe(bsarch_exe_win: str) -> None:
    """Validate that BSArch.exe exists and is accessible via wine.

    Prints a user-friendly error and exits with code 1 if the executable
    is missing or cannot be resolved through winepath.
    """
    if not os.path.exists(bsarch_exe_win):
        print("BSArch.exe is missing.")
        print(f'Please set the environment variable "BSARCH_EXE_WIN=Z:/path/to/BSArch.exe", '
              f"you can download BSArch from {BSARCH_DOWNLOAD_URL}")
        sys.exit(1)

    result = subprocess.run(
        ["winepath", "-u", bsarch_exe_win],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print("BSArch.exe is missing.")
        print(f'Please set the environment variable "BSARCH_EXE_WIN=Z:/path/to/BSArch.exe", '
              f"you can download BSArch from {BSARCH_DOWNLOAD_URL}")
        sys.exit(1)

    linux_path = result.stdout.strip()
    if not linux_path or not Path(linux_path).exists():
        print("BSArch.exe is missing.")
        print(f'Please set the environment variable "BSARCH_EXE_WIN=Z:/path/to/BSArch.exe", '
              f"you can download BSArch from {BSARCH_DOWNLOAD_URL}")
        sys.exit(1)
