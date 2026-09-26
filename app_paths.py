"""Filesystem locations that work both from source and as a PyInstaller exe.

When frozen, the app and its sidecar files (ffmpeg.exe, ffprobe.exe and the
recaptcha-solver.crx) live next to the .exe, and settings/downloads are written
there too. From source, everything is rooted at the project folder (where this
file lives). Centralising this here means no other module has to special-case
the frozen build.
"""

import sys
from pathlib import Path


def base_dir() -> Path:
    """Folder the app treats as its home.

    - Frozen (PyInstaller): the directory containing the running ``.exe``.
    - From source: this file's directory (the project root).

    ``sys.executable`` is the exe path when frozen, so its parent is the folder
    the user dropped the app and its sidecar files into - used instead of the
    working directory, which is not the exe's folder when launched via a
    shortcut or from a terminal in another location.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent