"""Round the corners of dropdown / completion popups.

A QComboBox dropdown - and a QCompleter completion list - is a separate
top-level popup window. A CSS ``border-radius`` only rounds the *painted*
border inside that window; the window rectangle itself stays square, so square
corners show through. The fix is to clip the popup window with a ``QBitmap``
mask, which physically removes the corners regardless of platform compositor
support, and to round the painted border to match.

:func:`round_popup` applies this to any popup item view; :func:`round_combo_popup`
is a thin convenience wrapper for QComboBoxes (the season/episode range pickers
and the theme, neon-colour and quality selectors). The same helper rounds the
search-bar completer popup so every dropdown in the app matches.
"""

from PySide6 import QtCore, QtGui, QtWidgets


class _PopupRounder(QtCore.QObject):
    """Masks a popup's window to a rounded rect on every Show/Resize.

    Installed on the popup *view*; the mask is applied to the view's top-level
    window (the dropdown container), which is what actually shows the corners.
    Reapplying on Show and Resize keeps the clip in sync with the popup's
    auto-adjusted size as the item list changes.
    """

    def __init__(self, radius: int = 8, parent=None):
        super().__init__(parent)
        self._radius = radius

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() in (QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Resize):
            win = obj.window()
            size = win.size()
            if not size.isEmpty():
                bm = QtGui.QBitmap(size)
                bm.fill(QtCore.Qt.GlobalColor.color0)        # transparent everywhere
                p = QtGui.QPainter(bm)
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(QtCore.Qt.GlobalColor.color1)     # opaque inside rounded rect
                p.drawRoundedRect(bm.rect(), self._radius, self._radius)
                p.end()
                win.setMask(bm)
        return False


def round_popup(view: QtWidgets.QAbstractItemView, radius: int = 8) -> None:
    """Give a popup item *view* rounded corners.

    Works for any popup-style item view - a QComboBox dropdown or a QCompleter
    completion popup. Clips the view's top-level window to a rounded rect
    (removing the square corners) and rounds the painted border/background to
    match.  Only the radius and a little padding are set inline so the border
    colour and background keep coming from the active theme.

    The event filter is parented to *view* so it lives as long as the widget.
    """
    if view is None:
        return

    rounder = _PopupRounder(radius, parent=view)
    view.installEventFilter(rounder)
    view.setStyleSheet(
        f"QListView, QAbstractItemView {{ border-radius: {radius}px; padding: 4px; }}"
    )


def round_combo_popup(combo: QtWidgets.QComboBox, radius: int = 8) -> None:
    """Give *combo*'s dropdown popup rounded corners.  Call once per combo at build time."""
    round_popup(combo.view(), radius)