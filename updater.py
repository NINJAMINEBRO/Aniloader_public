"""Self-update against the public GitHub repo.

Three steps, each usable on its own:

1. :class:`UpdateChecker` reads ``latest_version.txt`` from the public repo and
   compares it with :data:`version.BUILD`. The main window shows its update
   button when the remote number is higher.
2. :class:`UpdateDownloader` pulls the ``.exe`` attached to the newest release.
3. :func:`apply_update` swaps the new build in and relaunches it.

The published build is a single PyInstaller ``.exe`` (see the .spec - there is
no COLLECT step), so an update is one file replacing one file. ffmpeg.exe,
ffprobe.exe, the .crx and settings.json sit *next to* the exe and are never
touched, which is what keeps this simple.

The swap works around the one hard rule on Windows: a running ``.exe`` cannot be
deleted, but it *can* be renamed, and the running process follows the rename.
So the old build is renamed aside, the new one takes its place, and the old file
is deleted by the next launch - by then nothing is running from it. Deleting it
any earlier cannot work, because the process doing the deleting is the very
thing keeping the file alive.

The new build is started with PyInstaller's ``_PYI_*`` markers stripped from its
environment. Inherited, they make a onefile build mistake itself for this one's
second stage and abort before Python starts - see :func:`_child_environment`.
"""

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
from PySide6 import QtCore

import version
from i18n import tr

REPO = "NINJAMINEBRO/Aniloader_public"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/main/latest_version.txt"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

_TIMEOUT = 15
_HEADERS = {"User-Agent": f"Aniloader/{version.BUILD}"}

# Suffixes for the two transient files that live beside the exe mid-update.
_NEW_SUFFIX = ".new"
_OLD_SUFFIX = ".old"

# How long a freshly started build is watched before it is trusted to be up,
# and how often it is checked in that window.  A build that fails in its
# bootloader is gone in milliseconds, so this only has to outlast the launch
# itself - not the unpacking that follows it, during which the new process is
# very much alive.
_LAUNCH_WATCH_SECONDS = 2.0
_LAUNCH_POLL_SECONDS = 0.1


class UpdateError(Exception):
    """Anything that stops an update, with a message fit to show the user."""


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

def is_frozen() -> bool:
    """True when running as the packaged .exe rather than from source.

    Only a frozen build can replace itself - from source there is no single
    file to swap - so the UI offers the download page instead.
    """
    return getattr(sys, "frozen", False)


def current_exe() -> Path:
    """Absolute path of the running executable."""
    return Path(sys.executable).resolve()


def _sibling(exe: Path, marker: str) -> Path:
    """``Aniloader by NMB.exe`` + ``.old`` -> ``Aniloader by NMB.old.exe``.

    Keeping the real extension last means the staged download is still a
    runnable .exe, so a half-finished update can be salvaged by hand.
    """
    return exe.with_name(f"{exe.stem}{marker}{exe.suffix}")


# ----------------------------------------------------------------------
# Version check
# ----------------------------------------------------------------------

def parse_build(text: str) -> int | None:
    """First run of digits in *text*, or None if there is none.

    Tolerates a trailing newline, a ``v`` prefix or a stray comment, so the
    published file can gain a note later without breaking older clients.
    """
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


def fetch_latest_build() -> int | None:
    """Read the published build number from the public repo."""
    response = requests.get(VERSION_URL, headers=_HEADERS, timeout=_TIMEOUT)
    response.raise_for_status()
    return parse_build(response.text)


class UpdateChecker(QtCore.QThread):
    """Fetches the published build number in the background.

    Emits ``result_ready`` with that number, or 0 when the check failed - an
    offline start or a GitHub outage must not surface as an error, it just
    means no update button this session.
    """

    result_ready = QtCore.Signal(int)

    def run(self):
        build = 0
        try:
            build = fetch_latest_build() or 0
        except Exception as exc:
            print(f"[update] Check failed: {exc}")
        self.result_ready.emit(build)


# ----------------------------------------------------------------------
# Download
# ----------------------------------------------------------------------

def find_release_asset() -> tuple[str, str]:
    """URL and filename of the .exe attached to the newest release.

    Raises :class:`UpdateError` with a readable reason when there is nothing to
    download - no release published yet, or one published without a build
    attached, both of which are normal states for a fresh repo.
    """
    response = requests.get(LATEST_RELEASE_API, headers=_HEADERS, timeout=_TIMEOUT)
    if response.status_code == 404:
        raise UpdateError(
            tr("No release has been published yet.") + "\n\n"
            + tr("The version file lists a newer build, but there is no release "
                 "to download from.")
        )
    response.raise_for_status()

    assets = response.json().get("assets") or []
    executables = [a for a in assets if a.get("name", "").lower().endswith(".exe")]
    if not executables:
        raise UpdateError(
            tr("The newest release has no .exe attached, so there is nothing to "
               "install.")
        )
    asset = executables[0]
    return asset["browser_download_url"], asset["name"]


def download_asset(url: str, destination: Path, on_progress=None) -> None:
    """Stream *url* to *destination*, reporting percent complete.

    Downloads to a ``.part`` file and renames on success, so an interrupted
    download can never be mistaken for a finished build.
    """
    part = destination.with_suffix(destination.suffix + ".part")
    part.unlink(missing_ok=True)

    try:
        with requests.get(
            url, headers=_HEADERS, timeout=_TIMEOUT, stream=True
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            written = 0
            with part.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    if on_progress:
                        on_progress(int(written * 100 / total) if total else -1)

        # A server that closes cleanly mid-file leaves no exception behind, so
        # the length is checked explicitly too.
        if total and written != total:
            raise UpdateError(
                tr("The download ended early - check your connection and try again.")
            )
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except requests.RequestException as exc:
        # Dropped connections surface from inside iter_content, so the cleanup
        # has to sit here rather than after the loop.
        part.unlink(missing_ok=True)
        raise UpdateError(
            tr("The download failed - check your connection and try again.")
            + f"\n\n{exc}"
        ) from exc
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise UpdateError(f"{tr('Could not save the download:')}\n{exc}") from exc

    destination.unlink(missing_ok=True)
    os.replace(part, destination)


class UpdateDownloader(QtCore.QThread):
    """Finds the newest release's .exe and downloads it next to the current one.

    Emits ``progress`` (percent, or -1 when the size is unknown) and then
    ``done(ok, payload)`` - *payload* is the downloaded path on success, or a
    user-facing error message on failure.
    """

    progress = QtCore.Signal(int)
    done = QtCore.Signal(bool, str)

    def run(self):
        try:
            url, name = find_release_asset()
            print(f"[update] Downloading {name}")
            destination = _sibling(current_exe(), _NEW_SUFFIX)
            download_asset(url, destination, self.progress.emit)
            self.done.emit(True, str(destination))
        except UpdateError as exc:
            self.done.emit(False, str(exc))
        except Exception as exc:
            self.done.emit(False, f"{tr('Could not download the update:')}\n{exc}")


# ----------------------------------------------------------------------
# Swap + relaunch
# ----------------------------------------------------------------------

def apply_update(downloaded: Path) -> None:
    """Put *downloaded* in place of the running exe and start it.

    The caller quits straight after: the new process is already running, and
    this one still holds the old file open until it exits.

    Rolls back to the old build if the new one cannot be moved into place, so a
    failure here leaves a working install rather than no install at all.
    """
    exe = current_exe()
    old = _sibling(exe, _OLD_SUFFIX)

    # A leftover from a previous update would block the rename below.
    _delete_with_retries(old, attempts=3, pause=0.2)
    if old.exists():
        raise UpdateError(
            f"{tr('Could not clear the previous build at:')}\n{old}\n\n"
            + tr("Delete that file and try again.")
        )

    try:
        os.replace(exe, old)          # allowed while running; the process follows
    except OSError as exc:
        raise UpdateError(
            f"{tr('Could not move the current build aside:')}\n{exc}\n\n"
            + tr("Updating needs write access to the app's folder.")
        ) from exc

    try:
        os.replace(downloaded, exe)
    except OSError as exc:
        os.replace(old, exe)          # put the working build back
        raise UpdateError(
            f"{tr('Could not install the new build:')}\n{exc}"
        ) from exc

    try:
        process = subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            close_fds=True,
            env=_child_environment(),
        )
    except OSError as exc:
        raise UpdateError(
            f"{tr('The update installed but would not start:')}\n{exc}\n\n"
            f"{tr('Start it yourself from:')}\n{exe}"
        ) from exc

    _wait_until_running(process, exe)
    print(f"[update] Installed build; restarting from {exe}")


def _child_environment() -> dict[str, str]:
    """This process's environment minus PyInstaller's own bootloader markers.

    A onefile build's bootloader stamps ``_PYI_*`` into its environment (older
    releases used ``_MEIPASS2``).  A child that inherits them takes itself for
    *this* app's second stage: it reuses our unpacked folder instead of its own
    and checks that its parent is the same executable.  Mid-update it is not -
    our exe is the build being replaced - so it aborts with a "Security
    validation failure" before Python starts, leaving the update installed but
    nothing running.  A clean environment makes it bootstrap itself normally.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("_PYI") and key != "_MEIPASS2"
    }


def _wait_until_running(process: subprocess.Popen, exe: Path) -> None:
    """Raise if the build just started dies straight back out again.

    Popen only reports that the process was *created*.  A build that quits in
    its first moments would otherwise leave the user with no window and no
    error at all, because this process closes right afterwards and takes the
    last piece of UI with it.  Watching it for a moment turns that silence into
    a message saying where the installed build is.
    """
    deadline = time.monotonic() + _LAUNCH_WATCH_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise UpdateError(
                tr("The update installed but stopped immediately after starting "
                   "(exit code {code}).", code=process.returncode)
                + f"\n\n{tr('Start it yourself from:')}\n{exe}"
            )
        time.sleep(_LAUNCH_POLL_SECONDS)


# ----------------------------------------------------------------------
# Cleanup of the previous build
# ----------------------------------------------------------------------

def _delete_with_retries(path: Path, attempts: int = 40, pause: float = 0.25) -> bool:
    """Try to delete *path*, tolerating it still being locked for a moment."""
    for _ in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            time.sleep(pause)
    return False


def cleanup_previous_build() -> None:
    """Delete the build this one replaced, once it has finished exiting.

    Called at startup. The old process is usually still alive for a moment -
    it launched us and then quit - and Windows holds its file until it is gone,
    so this retries in the background instead of blocking the window from
    opening.  Giving up is harmless: the next launch tries again.
    """
    if not is_frozen():
        return
    old = _sibling(current_exe(), _OLD_SUFFIX)
    if not old.exists():
        return

    def worker() -> None:
        if _delete_with_retries(old):
            print(f"[update] Removed previous build: {old.name}")
        else:
            print(f"[update] Could not remove {old.name} yet; will retry next start")

    threading.Thread(target=worker, name="update-cleanup", daemon=True).start()
