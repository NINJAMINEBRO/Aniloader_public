from PySide6 import QtCore

from i18n import tr


class FetchStatusTracker(QtCore.QObject):
    """Tracks in-flight title fetches and drives a braille spinner.

    Connect to the ``updated`` signal to receive formatted status strings.
    An empty string signals that all fetches are done (hide the indicator).

    Usage::

        tracker = FetchStatusTracker(parent)
        tracker.updated.connect(my_label_slot)

        tracker.add("aniworld.to")   # starts the spinner
        tracker.remove("aniworld.to")  # stops it when all sites are done
    """

    updated = QtCore.Signal(str)

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sites: set[str] = set()
        self._idx = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)

    def add(self, site: str) -> None:
        """Register *site* as currently fetching."""
        self._sites.add(site)
        self._emit()
        if not self._timer.isActive():
            self._timer.start()

    def remove(self, site: str) -> None:
        """Mark *site*'s fetch as complete."""
        self._sites.discard(site)
        if not self._sites:
            self._timer.stop()
        self._emit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self._emit()

    def _emit(self) -> None:
        if self._sites:
            frame = self._FRAMES[self._idx]
            sites = ", ".join(sorted(self._sites))
            self.updated.emit(f"{frame}  {tr('fetching titles: {sites}', sites=sites)}")
        else:
            self.updated.emit("")
