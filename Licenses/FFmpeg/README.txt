FFmpeg - GNU General Public License v3
======================================

What this covers
----------------
The two binaries shipped in the root of this repository and inside the
released .exe:

    ffmpeg.exe    version 8.0-essentials_build-www.gyan.dev
    ffprobe.exe   version 8.1.1-essentials_build-www.gyan.dev

Both are pre-built Windows binaries from the "essentials" series published at
https://www.gyan.dev/ffmpeg/builds/ .  Run either with -version to confirm the
build string above.

Why GPLv3 and not LGPL
----------------------
These builds are configured with --enable-gpl --enable-version3, which pulls in
GPL-licensed components (x264, x265, libvidstab and others).  That makes the
binaries GPL version 3, not the LGPL that a default FFmpeg build carries.  The
full licence text is in COPYING.GPLv3.txt next to this file.

Relationship to Aniloader
-------------------------
Aniloader does not link against libavcodec or any other FFmpeg library.  It
runs ffmpeg.exe and ffprobe.exe as separate processes and talks to them over
the command line and their exit status (see downloaders/common.py, which builds
its command as `cmd = [_tool_path("ffmpeg")]`).  FFmpeg is therefore
distributed alongside Aniloader rather than built into it, and Aniloader's own
source stays under the Apache License 2.0 - see LICENSE.txt in the repository
root.

This separation only holds while FFmpeg is invoked as a process.  Switching to
a binding that links the libraries directly (PyAV, ffmpeg-python and the like)
would create a combined work and put the whole program under the GPL.

Corresponding source
--------------------
GPLv3 section 6 requires that the source for these binaries be available to
anyone who receives them:

  - Build origin, including its own source and build-script links:
    https://www.gyan.dev/ffmpeg/builds/
  - Release archives for these builds:
    https://github.com/GyanD/codexffmpeg/releases
  - Upstream FFmpeg source:
    https://github.com/FFmpeg/FFmpeg  and  https://git.ffmpeg.org/ffmpeg.git

If the binaries are ever replaced, update the version strings above and check
the new build's configuration line - an "essentials" or "full" build is GPL, a
"shared/LGPL" build is not.
