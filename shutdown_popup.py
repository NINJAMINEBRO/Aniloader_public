"""The warning shown when "Shutdown when done" is about to switch the PC off.

The shutdown itself is scheduled with the operating system the moment the
queue drains - see ``DownloadManager._shutdown_pc`` - and this window only
offers the way back out of it.  That split is deliberate: the shutdown goes
ahead exactly as it always did whether the window is closed, ignored, or never
seen at all, and even when Aniloader itself is closed during the countdown.
Only "Cancel shutdown" stops it.

The window has to reach someone who is not looking at Aniloader, typically
because a game is running fullscreen.  So it is made topmost and pulled into
the foreground, which on Windows takes more than asking: an app in the
background is normally only allowed to flash its taskbar button (see
:func:`_bring_to_front`).  A game in exclusive fullscreen gives way to it -
most minimise when they lose the focus - and a borderless one simply has it
drawn on top.  After that it only keeps its place on top while the countdown
runs, without taking the focus again, so someone who deliberately clicks back
into the game can carry on.

Keys are ignored and the button takes no keyboard focus: the window appears in
the middle of whatever the user is typing - a jump on Space, the game menu on
Escape - and a stray key must neither cancel the shutdown nor wave the warning
away.  Both take a deliberate click.
"""

import ctypes
import math
import sys
from time import monotonic

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import tr

# Win32 constants for SetWindowPos.
_HWND_TOPMOST = -1
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040

# user32/kernel32 with argument types declared, loaded on first use.  A private
# WinDLL rather than ctypes.windll, whose function objects are shared with any
# other module in the process that might declare different types for them.
_win32_cache: "tuple | None" = None


def _win32():
    global _win32_cache
    if _win32_cache is None:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        for name in ("BringWindowToTop", "SetForegroundWindow"):
            function = getattr(user32, name)
            function.argtypes = [wintypes.HWND]
            function.restype = wintypes.BOOL
        user32.SetFocus.argtypes = [wintypes.HWND]
        user32.SetFocus.restype = wintypes.HWND
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        _win32_cache = (user32, kernel32, wintypes)
    return _win32_cache


def _make_topmost(widget: QtWidgets.QWidget, activate: bool) -> None:
    """Put *widget* at the very top of the z-order, above other topmost windows.

    The stay-on-top flag alone places a window among the topmost ones, but a
    fullscreen game's window is usually topmost too, and whichever was raised
    last wins.  This raises ours again - without taking the focus unless
    *activate* is set.
    """
    user32, _kernel32, wintypes = _win32()
    flags = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW
    if not activate:
        flags |= _SWP_NOACTIVATE
    user32.SetWindowPos(wintypes.HWND(int(widget.winId())), wintypes.HWND(_HWND_TOPMOST),
                        0, 0, 0, 0, flags)


def _bring_to_front(widget: QtWidgets.QWidget) -> None:
    """Show *widget* above everything else and hand it the keyboard focus.

    Windows only lets the app the user is working in decide which window comes
    to the front; any other app asking gets its taskbar button flashed instead.
    The way round it is the one Qt itself uses when told to always activate:
    attach to the input of the thread that owns the current foreground window
    for the moment it takes to switch, which makes the request count as that
    thread's own.
    """
    if sys.platform != "win32":
        widget.raise_()
        widget.activateWindow()
        return

    try:
        user32, kernel32, wintypes = _win32()
        hwnd = wintypes.HWND(int(widget.winId()))
        _make_topmost(widget, activate=True)

        foreground = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        own_thread = kernel32.GetCurrentThreadId()
        attached = bool(
            foreground_thread and foreground_thread != own_thread
            and user32.AttachThreadInput(foreground_thread, own_thread, True)
        )
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(foreground_thread, own_thread, False)
    except Exception as exc:  # the window is still shown, just maybe not in front
        print(f"[shutdown] could not bring the warning to the front: {exc}")


class ShutdownPopup(QtWidgets.QWidget):
    """A countdown to the scheduled shutdown with a button to call it off.

    Emits :attr:`cancel_requested` when the button is clicked; cancelling is
    the owner's job, since the owner is the one who scheduled the shutdown.
    Closing the window only hides the warning.  It closes itself once the
    countdown has run out.
    """

    cancel_requested = QtCore.Signal()

    def __init__(self, seconds: int):
        # No parent on purpose: a window owned by the main window is hidden
        # along with it when Aniloader is minimised - exactly when the user is
        # busy elsewhere and most needs to see this.
        super().__init__(
            None,
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.CustomizeWindowHint
            | QtCore.Qt.WindowType.WindowTitleHint
            | QtCore.Qt.WindowType.WindowCloseButtonHint,
        )
        self.setWindowTitle(f"Aniloader - {tr('Shutdown when done')}")
        # Counted against the clock rather than by ticks, so the number shown
        # matches the operating system's own countdown however late a tick is.
        self._deadline = monotonic() + seconds

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)

        self._build()

    def _build(self) -> None:
        center = QtCore.Qt.AlignmentFlag.AlignCenter

        heading = QtWidgets.QLabel(tr("All downloads are finished."))
        heading.setAlignment(center)
        heading.setStyleSheet("font-size: 13px;")

        self._countdown = QtWidgets.QLabel()
        self._countdown.setAlignment(center)
        self._countdown.setStyleSheet("font-size: 18px; font-weight: 600; color: #e67e22;")

        cancel_button = QtWidgets.QPushButton(tr("Cancel shutdown"))
        cancel_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        cancel_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        cancel_button.setMinimumSize(220, 38)
        # The green of the ON toggles: the button that keeps things as they are.
        cancel_button.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: 600; color: white;"
            " background-color: #166034; border: 1px solid #27ae60;"
            " border-radius: 4px; padding: 6px 18px; }"
            "QPushButton:hover { background-color: #1d7a43; }"
        )
        cancel_button.clicked.connect(lambda _checked=False: self.cancel_requested.emit())

        self._hint = QtWidgets.QLabel(tr("Closing this window lets the shutdown go ahead."))
        self._hint.setAlignment(center)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: gray; font-size: 11px;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(self._countdown)
        layout.addSpacing(6)
        layout.addWidget(cancel_button, alignment=center)
        layout.addWidget(self._hint)
        self.setMinimumWidth(420)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_on_top(self) -> None:
        """Show the warning in front of everything and start the countdown."""
        self._tick()
        self.adjustSize()
        # Centred on the screen the mouse is on: a game keeps the cursor on its
        # own screen, so that is the one being looked at.
        screen = (QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
                  or QtGui.QGuiApplication.primaryScreen())
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        self.show()
        _bring_to_front(self)
        # Flashes the taskbar button too, in case the switch was refused.
        QtWidgets.QApplication.alert(self)
        self._timer.start()

    def show_cancel_failed(self, command: str) -> None:
        """Say the shutdown could not be cancelled, and how to stop it by hand."""
        self._hint.setText(tr("Could not cancel the shutdown - run {command} to stop it.",
                              command=command))
        self._hint.setStyleSheet("color: #e74c3c; font-size: 11px;")
        # The message can wrap onto more lines than the hint it replaces.
        self.adjustSize()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        remaining = math.ceil(self._deadline - monotonic())
        if remaining <= 0:
            self.close()      # the shutdown is under way
            return
        self._countdown.setText(
            tr("The PC will shut down in 1 second.") if remaining == 1
            else tr("The PC will shut down in {seconds} seconds.", seconds=remaining)
        )
        # Stay above anything raised since - a game re-asserting its own
        # fullscreen window - but leave the focus where the user put it.
        if sys.platform == "win32" and self.isVisible():
            try:
                _make_topmost(self, activate=False)
            except Exception:
                pass

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        # Swallow every key, so nothing typed into the game a moment ago can
        # cancel the shutdown or dismiss the warning - see the module docstring.
        event.accept()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._timer.stop()
        super().closeEvent(event)
