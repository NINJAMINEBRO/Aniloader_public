Qt for Python (PySide6) - GNU Lesser General Public License v3
==============================================================

What this covers
----------------
Aniloader's whole user interface is built on Qt for Python:

    PySide6    6.11.1
    shiboken6  6.11.1   (PySide6's binding runtime, same licence)

Both are published under "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", with
a separate commercial licence available from The Qt Company.  Aniloader uses
them under the LGPL version 3.

Two licence texts are included because LGPLv3 is not standalone - it is a set
of additional permissions layered on top of GPLv3, and says so in its opening
paragraph:

    LICENSE.LGPLv3.txt   the Lesser GPL itself
    LICENSE.GPLv3.txt    the GPL it incorporates by reference

Relationship to Aniloader
-------------------------
Aniloader imports PySide6 as a library; it contains no Qt source and is not a
modified version of Qt.  Under LGPLv3 that leaves Aniloader's own source under
the Apache License 2.0 - see LICENSE.txt in the repository root - while these
obligations apply to the distribution as a whole:

  - This notice, stating that Qt/PySide6 is used and is covered by the LGPL.
  - The two licence texts above, shipped with the program.
  - A way for a recipient to replace the Qt libraries with their own build.

The last point is met by dynamic linking, which is what LGPLv3 section 4(d)(1)
calls a "suitable shared library mechanism".  Qt is loaded from ordinary DLLs
(Qt6Core.dll, Qt6Gui.dll, Qt6Widgets.dll and the rest); in the PyInstaller
one-file build these are unpacked to a temporary directory at startup and
loaded from there, so a recipient can substitute their own copies.  Nothing in
the build statically links Qt into the executable.

Source code
-----------
  - PySide6 and shiboken6 source:
    https://code.qt.io/cgit/pyside/pyside-setup.git/
    https://pypi.org/project/PySide6/#files  (sdist for the exact version)
  - Qt itself:
    https://code.qt.io/cgit/qt/qtbase.git/
    https://download.qt.io/official_releases/qt/

Anyone rebuilding Aniloader from source gets these through
`pip install -r requirements.txt`, which pins PySide6==6.11.1.

If PySide6 is ever upgraded, update the version numbers above; the licence
terms themselves have been unchanged since Qt 5.
