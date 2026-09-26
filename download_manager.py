"""Download queue, worker pool, status panels, and shutdown-when-done.

A self-contained widget that owns the pending/active download lifecycle and
renders the side-by-side "Downloading" / "Pending" panels.  The main window
hands it episodes via :meth:`enqueue` and drops the widget into its layout;
everything else - spawning workers up to the simultaneous-downloads limit,
spacing those starts out by the configured download delay, sending failed
episodes to the back of the queue for another attempt, updating the panels,
and optionally shutting the machine down once the queue drains, with a
warning window to cancel it (see shutdown_popup) - happens internally.
"""

import sys
import subprocess
import time
from collections import deque

from PySide6 import QtWidgets, QtCore, QtGui

from download_worker import EpisodeDownloadWorker, episode_code, is_already_downloaded
from i18n import tr
from shutdown_popup import ShutdownPopup

# Seconds between scheduling the shutdown-when-done and the PC switching off -
# the time the warning window gives to cancel it.
_SHUTDOWN_DELAY = 60


class _FullWidthDelegate(QtWidgets.QStyledItemDelegate):
    """Item delegate that sizes every row to the widest label in its panel.

    Both panels keep ``setUniformItemSizes(True)`` for the pending list's
    performance, which makes Qt reuse a single size hint for every row.
    Reporting the *widest* label's width here means the longest entry still
    fits, so no line has to be elided - the panel scrolls sideways instead.
    """

    _PADDING = 12          # breathing room right of the longest label
    # Only the longest few strings are actually measured: character count is a
    # good enough proxy to shortlist candidates, and measuring a thousand
    # pending labels on every queue change would not be.
    _MEASURE_CANDIDATES = 25

    def __init__(self, parent=None):
        super().__init__(parent)
        self._width = 0

    def update_width(self, labels: list[str], font_metrics: QtGui.QFontMetrics) -> None:
        """Recompute the row width from *labels*; call before repopulating."""
        widest = 0
        for text in sorted(labels, key=len, reverse=True)[: self._MEASURE_CANDIDATES]:
            widest = max(widest, font_metrics.horizontalAdvance(text))
        self._width = widest + self._PADDING

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QtCore.QSize(max(hint.width(), self._width), hint.height())


class DownloadManager(QtWidgets.QWidget):
    """Owns the download queue + workers and shows the two status panels.

    Parameters
    ----------
    settings_state : dict
        Shared mutable settings dict (read for ``simultaneous_downloads``,
        ``download_delay``, ``failed_retries`` and ``shutdown_when_done``).
        Held by reference so live changes are seen.
    """

    def __init__(self, settings_state: dict, parent=None):
        super().__init__(parent)
        self._settings = settings_state

        # Download queue (pending episodes).  Each entry:
        #   (url, series_name, season_label, ep_num, title, sp, sl, lc, uc)
        # A deque gives O(1) popleft, which matters when 1000+ are queued.
        self._download_queue: deque = deque()
        # Active download workers keyed by episode URL
        self._active_workers: dict[str, EpisodeDownloadWorker] = {}
        # url -> one-line label / latest status string for the panels
        self._active_labels: dict[str, str] = {}
        self._active_status: dict[str, str] = {}
        # url -> the queue entry a running worker came from, kept so a failed
        # episode can be put back on the queue without rebuilding it.
        self._active_items: dict[str, tuple] = {}
        # url -> retries already spent on it.  Entries only live here between
        # the first failure and either a success or the retry limit.
        self._retry_counts: dict[str, int] = {}
        # Ensures the shutdown-when-done action fires at most once - until it
        # is cancelled, which re-arms it for the next batch.
        self._shutdown_initiated: bool = False
        # The warning window of a scheduled shutdown, while there is one.
        self._shutdown_popup: ShutdownPopup | None = None

        # time.monotonic() of the most recent worker start, or None while
        # nothing has started yet.  The download delay is measured from here.
        self._last_start: float | None = None
        # Re-runs the launch loop once the delay has elapsed.  Single-shot and
        # reused, so re-starting it just moves the one pending wake-up rather
        # than stacking timers.
        self._launch_timer = QtCore.QTimer(self)
        self._launch_timer.setSingleShot(True)
        self._launch_timer.timeout.connect(self._try_launch_downloads)

        self._build_panels()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_panels(self) -> None:
        """Build the side-by-side 'Downloading' and 'Pending' list panels.

        Both use a QListView backed by a QStringListModel.  QListView only
        renders the rows currently visible and, with uniform item sizes,
        stays responsive even when the pending list holds well over a
        thousand entries.
        """
        self._active_model = QtCore.QStringListModel(self)
        self._pending_model = QtCore.QStringListModel(self)

        self._active_header = QtWidgets.QLabel(f"⬇  {tr('Downloading ({count})', count=0)}")
        self._active_header.setStyleSheet("font-size: 11px; font-weight: 600;")
        self._pending_header = QtWidgets.QLabel(f"⏳  {tr('Pending ({count})', count=0)}")
        self._pending_header.setStyleSheet("font-size: 11px; font-weight: 600;")

        self._active_view = QtWidgets.QListView()
        self._active_view.setModel(self._active_model)
        self._pending_view = QtWidgets.QListView()
        self._pending_view.setModel(self._pending_model)

        # Rows are never shortened with "…": the delegate widens every row to
        # the longest label and the view scrolls horizontally instead, so the
        # full series/season/episode/status line stays readable.
        self._active_delegate = _FullWidthDelegate(self._active_view)
        self._pending_delegate = _FullWidthDelegate(self._pending_view)
        self._active_view.setItemDelegate(self._active_delegate)
        self._pending_view.setItemDelegate(self._pending_delegate)

        for view in (self._active_view, self._pending_view):
            view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
            view.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            view.setUniformItemSizes(True)   # big perf win for long pending lists
            view.setWordWrap(False)
            view.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
            view.setHorizontalScrollMode(
                QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
            )
            view.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            view.setMinimumHeight(120)
            view.setStyleSheet(
                "QListView {"
                " background-color: palette(base);"
                " border: 1px solid palette(mid);"
                " border-radius: 6px; padding: 2px; }"
            )

        active_col = QtWidgets.QVBoxLayout()
        active_col.setSpacing(4)
        active_col.addWidget(self._active_header)
        active_col.addWidget(self._active_view)

        pending_col = QtWidgets.QVBoxLayout()
        pending_col.setSpacing(4)
        pending_col.addWidget(self._pending_header)
        pending_col.addWidget(self._pending_view)

        panels = QtWidgets.QHBoxLayout(self)
        panels.setContentsMargins(0, 0, 0, 0)
        panels.setSpacing(12)
        panels.addLayout(active_col)
        panels.addLayout(pending_col)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        episodes: list[tuple],
        supported_providers: list[str],
        supported_languages: list[str],
        language_codes: dict,
        url_converter,
    ) -> None:
        """Queue every episode that isn't already downloaded, running, or pending.

        *episodes* is the ``(url, series_name, season_label, ep_num, title)``
        list produced by a site page's ``get_selected_urls()``.  The remaining
        arguments are the site's provider/language context, stored alongside
        each queued entry for the worker that eventually runs it.
        """
        # Skip episodes whose file already exists, or that are already running
        # or queued, so nothing re-downloads or clutters the Pending panel.
        existing = set(self._active_workers) | {item[0] for item in self._download_queue}
        queued = 0
        skipped = 0
        for url, series_name, season_label, ep_num, title in episodes:
            if url in existing:
                continue
            if is_already_downloaded(
                self._settings, series_name, season_label, ep_num, title
            ):
                skipped += 1
                continue
            self._download_queue.append(
                (url, series_name, season_label, ep_num, title,
                 supported_providers, supported_languages,
                 language_codes, url_converter)
            )
            existing.add(url)
            queued += 1

        if skipped:
            print(f"[download] Skipped {skipped} already-downloaded episode(s)")
        print(f"[download] Queued {queued} episode(s)…")
        self._try_launch_downloads()

    def pending_work(self) -> tuple[int, int]:
        """``(downloading, queued)`` - what would be lost by quitting now.

        Exposed for the update flow, which restarts the app and so has to warn
        before throwing away downloads that are part-finished.
        """
        return len(self._active_workers), len(self._download_queue)

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def _download_delay(self) -> float:
        """Seconds to leave between two download starts, from the settings.

        Hosts that rate limit react to how fast requests arrive, not to how
        many run at once, so the queue spaces its starts out even when the
        concurrency limit would allow several at the same moment.  A junk value
        in a hand-edited settings file falls back to the default rather than
        stalling the queue forever.
        """
        try:
            return max(0.0, float(self._settings.get("download_delay", 2)))
        except (TypeError, ValueError):
            return 2.0

    def _failed_retry_limit(self) -> int:
        """How often a completely failed episode may be retried, from the settings.

        Clamped to the 0-5 the Settings page offers, so a hand-edited settings
        file cannot make the queue cycle a dead episode indefinitely.
        """
        try:
            return max(0, min(5, int(self._settings.get("failed_retries", 1))))
        except (TypeError, ValueError):
            return 1

    def _try_launch_downloads(self) -> None:
        """Spawn new EpisodeDownloadWorkers up to the simultaneous-downloads limit.

        Starts are additionally spaced by the download delay: when the next one
        would come too soon it is left queued and a timer re-enters this method
        once enough time has passed.
        """
        max_concurrent = self._settings.get("simultaneous_downloads", 3)
        delay = self._download_delay()

        while len(self._active_workers) < max_concurrent and self._download_queue:
            if self._last_start is not None:
                remaining = delay - (time.monotonic() - self._last_start)
                if remaining > 0:
                    # Come back when this slot is allowed to start.
                    self._launch_timer.start(int(remaining * 1000) + 1)
                    break
            if self._start_next():
                self._last_start = time.monotonic()

        self._update_active_view()
        self._update_pending_view()

    def _start_next(self) -> bool:
        """Pop the head of the queue and start a worker for it.

        Returns True when a worker was actually started; a duplicate entry for
        an already-running episode is dropped and returns False, so it does not
        consume a delay slot.
        """
        item = self._download_queue.popleft()
        url, series_name, season_label, ep_num, title, sp, sl, lc, uc = item

        if url in self._active_workers:
            return False  # already running (duplicate queue entry guard)

        label = self._queue_label(item)
        print(f"[download] Starting  {title!r}  ({season_label} E{episode_code(ep_num)})")
        worker = EpisodeDownloadWorker(
            url, series_name, season_label, ep_num, title,
            self._settings, sp, sl,
            language_codes=lc,
            url_converter=uc,
            parent=self,
        )
        worker.progress.connect(self._on_download_progress)
        worker.download_finished.connect(self._on_worker_finished)
        # Delete the QThread object once it has truly finished (built-in
        # finished, fired after run() returns) so completed workers don't
        # pile up as children for the life of the session.
        worker.finished.connect(worker.deleteLater)
        self._active_workers[url] = worker
        self._active_labels[url] = label
        self._active_status[url] = ""
        self._active_items[url] = item
        worker.start()
        return True

    def _on_worker_finished(self, url: str, success: bool, combo: str) -> None:
        """Slot called in the main thread when an EpisodeDownloadWorker finishes."""
        worker = self._active_workers.pop(url, None)
        item = self._active_items.pop(url, None)
        self._active_labels.pop(url, None)
        self._active_status.pop(url, None)
        if success:
            print(f"[download] ✓ {url} via {combo}")
            self._retry_counts.pop(url, None)
        elif not self._requeue_failed(url, item, worker):
            print(f"[download] ✗ {url} - no working combination found")
            self._retry_counts.pop(url, None)
        self._try_launch_downloads()
        self._maybe_shutdown()

    def _requeue_failed(self, url: str, item: tuple | None, worker) -> bool:
        """Put a failed episode back on the queue, if it has retries left.

        The entry goes on the *back* rather than straight back into a worker
        slot: whatever made it fail - a provider having a bad minute, a host
        rate limiting us - is most likely to have passed by the time the rest
        of the queue has been worked through.  Returns True when the episode
        was requeued, so the caller knows not to report it as finally failed.
        """
        if item is None:
            return False
        if worker is not None and worker.isInterruptionRequested():
            # Cancelled on app close, not a genuine failure - and requeueing
            # here would only refill a queue that is being torn down.
            return False

        limit = self._failed_retry_limit()
        used = self._retry_counts.get(url, 0)
        if used >= limit:
            return False

        self._retry_counts[url] = used + 1
        self._download_queue.append(item)
        print(f"[download] ✗ {url} - failed, retry {used + 1}/{limit} queued at the back")
        return True

    def _on_download_progress(self, url: str, message: str) -> None:
        print(f"[download] {message} ({url})")
        if url in self._active_status:
            self._active_status[url] = message.strip()
            self._update_active_view()

    # ------------------------------------------------------------------
    # Panel updates
    # ------------------------------------------------------------------

    def _queue_label(self, item: tuple) -> str:
        """One-line label for a queued or active episode.

        An episode that is only in the queue again because it failed carries a
        ``(retry n/m)`` marker, so the panels show why a title the user watched
        finish is back in the list.
        """
        url, series, season_label, ep_num, title, *_rest = item
        label = f"{series} - {season_label} E{episode_code(ep_num)} - {title}"
        retries = self._retry_counts.get(url, 0)
        if retries:
            label += "  " + tr("(retry {count}/{limit})",
                               count=retries, limit=self._failed_retry_limit())
        return label

    def _update_active_view(self) -> None:
        items = []
        for url in self._active_workers:
            label = self._active_labels.get(url, url)
            status = self._active_status.get(url, "")
            items.append(f"{label} · {status}" if status else label)
        self._active_delegate.update_width(items, self._active_view.fontMetrics())
        self._active_model.setStringList(items)
        self._active_header.setText(f"⬇ {tr('Downloading ({count})', count=len(items))}")

    def _update_pending_view(self) -> None:
        labels = [self._queue_label(item) for item in self._download_queue]
        self._pending_delegate.update_width(labels, self._pending_view.fontMetrics())
        self._pending_model.setStringList(labels)
        self._pending_header.setText(f"⏳  {tr('Pending ({count})', count=len(labels))}")

    # ------------------------------------------------------------------
    # Shutdown-when-done
    # ------------------------------------------------------------------

    def _maybe_shutdown(self) -> None:
        """Shut the PC down once everything has finished, if the user enabled it."""
        if self._active_workers or self._download_queue:
            return
        if not self._settings.get("shutdown_when_done", False):
            return
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True
        if self._shutdown_pc():
            self._show_shutdown_popup()

    @staticmethod
    def _shutdown_pc() -> bool:
        """Schedule the shutdown; True when it is now counting down and can be cancelled.

        The countdown is the operating system's own, so the PC shuts down on
        time whatever happens to the warning window - or to Aniloader.
        """
        print("[download] All downloads finished - initiating system shutdown.")
        try:
            if sys.platform.startswith("win"):
                print(f"[download] Shutting down in {_SHUTDOWN_DELAY}s. Cancel with:  shutdown /a")
                return _run_quietly(["shutdown", "/s", "/t", str(_SHUTDOWN_DELAY)])
            if sys.platform == "darwin":
                # Immediate: there is no countdown left to cancel.
                subprocess.Popen(
                    ["osascript", "-e",
                     'tell application "System Events" to shut down']
                )
                return False
            minutes = max(1, round(_SHUTDOWN_DELAY / 60))
            print(f"[download] Shutting down in {minutes} minute(s). Cancel with:  shutdown -c")
            return _run_quietly(["shutdown", "-h", f"+{minutes}"])
        except Exception as exc:
            print(f"[download] Could not initiate shutdown: {exc}")
            return False

    @staticmethod
    def _cancel_command() -> list[str]:
        """The command that calls off the shutdown _shutdown_pc() scheduled."""
        return ["shutdown", "/a"] if sys.platform.startswith("win") else ["shutdown", "-c"]

    def _show_shutdown_popup(self) -> None:
        """Warn about the scheduled shutdown, with a way to cancel it."""
        self._shutdown_popup = ShutdownPopup(_SHUTDOWN_DELAY)
        self._shutdown_popup.cancel_requested.connect(self._on_shutdown_cancel_requested)
        self._shutdown_popup.show_on_top()

    def _on_shutdown_cancel_requested(self) -> None:
        """Call the shutdown off - the warning's Cancel button."""
        popup = self._shutdown_popup
        try:
            cancelled = _run_quietly(self._cancel_command())
        except Exception as exc:
            print(f"[download] Could not cancel the shutdown: {exc}")
            cancelled = False

        if not cancelled:
            if popup is not None:
                popup.show_cancel_failed(" ".join(self._cancel_command()))
            return

        print("[download] Shutdown cancelled.")
        # Re-armed: the setting is still on, so the next batch that finishes
        # may shut the PC down again - with the same warning to cancel it.
        self._shutdown_initiated = False
        if popup is not None:
            popup.close()
        self._shutdown_popup = None


def _run_quietly(command: list[str]) -> bool:
    """Run *command* to completion without a console window; True on success.

    A failure is printed with the command's own message - the shutdown command
    says why it refused - so the console shows more than a bare error code.
    """
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    result = subprocess.run(command, capture_output=True, timeout=15, creationflags=flags)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or b"").decode(errors="replace").strip()
        print(f"[download] {' '.join(command)} failed ({result.returncode}): {output}")
    return result.returncode == 0