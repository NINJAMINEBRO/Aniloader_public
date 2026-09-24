"""hanime.tv - catalogue and downloading.

hanime.tv has no concept of a series: every episode is a separate video and the
only thing linking them is the number on the end of the slug.  :mod:`hanime_series`
is what draws that link, and it runs on both sides of this page - the search bar
offers one row per series, and opening one expands it back into its episodes here.

That gives this page the same From/To range the other sites have, with one axis
instead of two: there are no seasons to pick, so the range is over episodes
alone.  Downloads are still filed as ``<series>/Season 1/SxxEyy <title>.mp4`` to
match everything else on disk, with the season fixed at 1 because the site
offers nothing to put there.

Guests are served 720p at best - the site withholds 1080p - so the page says so
rather than letting a 1080p setting look like it failed.  The download itself is
handled by ``downloaders/Hanime.py``; see that module for how the stream URL is
obtained.
"""

from PySide6 import QtWidgets, QtCore

import hanime_series
from i18n import tr

# The hostname this page handles (without www.)
HOSTNAME = "hanime.tv"

# Downloading is wired up: the menu builds the Confirm button for this page.
DOWNLOADS_SUPPORTED = True

# hanime.tv serves its own streams rather than embedding a third-party hoster,
# so there is exactly one "provider" and it is this site itself.
SUPPORTED_PROVIDERS: list[str] = ["Hanime"]

# The site offers no language choice, so this names what the streams actually
# are.  It has to be a language the settings already know about, since the
# worker only runs combinations the user has enabled.
SUPPORTED_LANGUAGES: list[str] = ["Japanese · English Sub"]

# No site-internal language codes: the video URL is passed to the downloader
# unchanged (this page exposes no get_provider_url).
LANGUAGE_CODES: dict[str, str] = {}

# Highest tier a guest is served; shown in the body so the cap isn't mistaken
# for a failed download.
GUEST_MAX_QUALITY = "720p"

# Seasons don't exist on this site, but the rest of the app writes downloads as
# <series>/<season>/SxxEyy <title>.mp4; naming it season 1 keeps hanime
# downloads shaped like everything else on disk.
SEASON_LABEL = "Season 1"


class HanimeTvContent(QtWidgets.QWidget):
    """Body widget for hanime.tv pages.

    Shows the series that was opened and lets the user pick an inclusive range
    of its episodes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # [(episode_number, slug)] for the loaded series, in episode order.
        self._episodes: list[tuple[int, str]] = []
        self._series_slug: str = ""
        self._build()

    def _build(self):
        self.title_label = QtWidgets.QLabel()
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")

        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")

        from_label = QtWidgets.QLabel(tr("From:"))
        to_label = QtWidgets.QLabel(tr("To:"))
        # At least the 35px the English labels had, more when a translation
        # needs it.
        label_width = max(35, from_label.sizeHint().width(), to_label.sizeHint().width())
        from_label.setFixedWidth(label_width)
        to_label.setFixedWidth(label_width)

        self.episode_start = QtWidgets.QComboBox()
        self.episode_start.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.episode_end = QtWidgets.QComboBox()
        self.episode_end.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.episode_start.currentIndexChanged.connect(self._on_episode_start_changed)
        self.episode_end.currentIndexChanged.connect(self._on_episode_end_changed)

        from_row = QtWidgets.QHBoxLayout()
        from_row.setSpacing(8)
        from_row.addWidget(from_label)
        from_row.addWidget(self.episode_start)

        to_row = QtWidgets.QHBoxLayout()
        to_row.setSpacing(8)
        to_row.addWidget(to_label)
        to_row.addWidget(self.episode_end)

        self.range_widget = QtWidgets.QWidget()
        range_layout = QtWidgets.QVBoxLayout(self.range_widget)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(10)
        range_layout.addLayout(from_row)
        range_layout.addLayout(to_row)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.range_widget)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, url: str) -> None:
        """Called by the main menu whenever the user navigates here."""
        slug = hanime_series.slug_from_url(url)
        if not slug:
            self._episodes = []
            self._series_slug = ""
            self._clear_controls()
            self.range_widget.setVisible(False)
            self.title_label.setText("")
            self.status_label.setText(tr("This doesn't look like a hanime.tv video link."))
            return

        self._series_slug, _ = hanime_series.split_slug(slug)
        # Falls back to the single opened video when the catalogue hasn't been
        # fetched yet, so the page still offers that episode rather than nothing.
        self._episodes = hanime_series.episodes_for_url(url)

        self.title_label.setText(hanime_series.title_from_slug(self._series_slug))
        count = len(self._episodes)
        episodes = (tr("{count} episode", count=count) if count == 1
                    else tr("{count} episodes", count=count))
        self.status_label.setText(
            f"{episodes} · "
            + tr("up to {quality} (hanime.tv doesn't serve 1080p without an account)",
                 quality=GUEST_MAX_QUALITY)
        )

        self._populate_episodes()
        # A one-episode series has no range to choose, so the pickers would only
        # be two boxes that cannot be changed.
        self.range_widget.setVisible(count > 1)

    def get_selected_urls(self) -> list[tuple]:
        """Return ``(url, series_name, season_label, ep_num, title)`` per episode.

        Inclusive of both endpoints, in episode order.  The series name is
        shared by every tuple and used as the top-level download folder.
        """
        if not self._episodes:
            return []

        start = self.episode_start.currentIndex()
        end = self.episode_end.currentIndex()
        if start < 0 or end < 0:
            return []
        if start > end:
            start, end = end, start

        series_name = hanime_series.title_from_slug(self._series_slug)
        return [
            (
                hanime_series.url_for_slug(slug),
                series_name,
                SEASON_LABEL,
                number,
                hanime_series.title_from_slug(slug),
            )
            for number, slug in self._episodes[start:end + 1]
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_controls(self):
        for combo in (self.episode_start, self.episode_end):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)

    def _populate_episodes(self):
        """Fill both pickers with the loaded series' episodes, spanning it all."""
        for combo in (self.episode_start, self.episode_end):
            combo.blockSignals(True)
            combo.clear()
            for number, slug in self._episodes:
                combo.addItem(tr("Episode {number}", number=number), slug)
            combo.blockSignals(False)

        # Default to the whole series: the common case is wanting all of it.
        self.episode_start.setCurrentIndex(0)
        self.episode_end.setCurrentIndex(len(self._episodes) - 1)

    # ------------------------------------------------------------------
    # Range auto-correction
    # ------------------------------------------------------------------

    def _on_episode_start_changed(self):
        if self.episode_start.currentIndex() > self.episode_end.currentIndex():
            self.episode_end.blockSignals(True)
            self.episode_end.setCurrentIndex(self.episode_start.currentIndex())
            self.episode_end.blockSignals(False)

    def _on_episode_end_changed(self):
        if self.episode_end.currentIndex() < self.episode_start.currentIndex():
            self.episode_start.blockSignals(True)
            self.episode_start.setCurrentIndex(self.episode_end.currentIndex())
            self.episode_start.blockSignals(False)


def build_content() -> QtWidgets.QWidget:
    """Return the body widget shown below the shared title bar."""
    return HanimeTvContent()
