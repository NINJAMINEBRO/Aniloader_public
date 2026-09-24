"""Browsing and downloading page for animepahe.ch.

Shows the seasons of one series and lets a range be picked across them, the way
every other site page does.  How an episode is then downloaded depends on which
of the site's two page layouts it has; see :func:`get_provider_url`.

What is different about animepahe is that its catalogue is full of holes.  It
carries whichever seasons and episodes it happens to have - Rent-a-Girlfriend
starts at season 4, Yamishibai at season 14, Fire Force is missing both seasons
before the one it lists - so the pickers are built to *show* the holes rather
than paper over them.  Seasons are offered under their real numbers, and the
ones the site does not have are listed too, greyed out and unpickable.
Episodes are left to speak for themselves: a season jumping from 7 to 9 is
visible in the numbers, and spelling out the gaps as rows would mean a thousand
of them for a series like One Piece, which lists only its most recent stretch.
"""

import asyncio
import base64
import binascii
import math
import re
import threading
from html import unescape
from time import monotonic
from typing import NamedTuple
from urllib.parse import urlencode, urlsplit

import aiohttp
from PySide6 import QtWidgets, QtCore, QtGui
from bs4 import BeautifulSoup

import animepahe_series
import settings_manager
import site_mirrors
from downloaders import Vidstream
from i18n import tr

# The hostname this page handles (without www.)
HOSTNAME = "animepahe.ch"

# Downloading is wired up: the menu builds the Confirm button for this page.
DOWNLOADS_SUPPORTED = True

# Providers this site actually supports.  Which one an episode can use depends
# on its page layout - see get_provider_url():
#   Vidstream   - the MegaPlay player most episodes embed (downloaders/Vidstream.py)
#   Kiwi-Stream - the kwik link in the download box under a Blogger player
#   Blogger     - that Blogger player itself (downloaders/Blogger.py)
SUPPORTED_PROVIDERS = ["Vidstream", "Kiwi-Stream", "Blogger"]

# animepahe subtitles everything and dubs a small part of it.  Sub and dub are
# never separate rows in the range picker: they are the same season, and which
# one a season is taken from is decided here, by the user's language order in
# Settings -> Languages, the same way every other site decides it.
#
# Every sub language beyond English comes from the MegaPlay player, which lays
# each language over the video as a track of its own; how many it has depends
# on where the episode was sourced, from English alone to a dozen Crunchyroll
# tracks.  A language is only downloaded when the episode really has that track.
SUPPORTED_LANGUAGES = [
    "Japanese · English Sub",
    "English Dub",
    "Japanese · German Sub",
    "Japanese · French Sub",
    "Japanese · Indonesian Sub",
    "Japanese · Thai Sub",
    "Japanese · Vietnamese Sub",
    "Japanese · Portuguese (Brazil) Sub",
    "Japanese · Spanish Sub",
    "Japanese · Spanish (Latin America) Sub",
]

# Global display name -> the site-internal identifier used when picking a
# download, in the form anikototv uses too: the audio track
# (animepahe_series.SUB / DUB), and for sub entries the subtitle language after a
# colon - a key of downloaders/Vidstream.py's SUBTITLE_LANGUAGES.
LANGUAGE_CODES: dict[str, str] = {
    "Japanese · English Sub": f"{animepahe_series.SUB}:eng",
    "English Dub": animepahe_series.DUB,
    "Japanese · German Sub": f"{animepahe_series.SUB}:deu",
    "Japanese · French Sub": f"{animepahe_series.SUB}:fra",
    "Japanese · Indonesian Sub": f"{animepahe_series.SUB}:ind",
    "Japanese · Thai Sub": f"{animepahe_series.SUB}:tha",
    "Japanese · Vietnamese Sub": f"{animepahe_series.SUB}:vie",
    "Japanese · Portuguese (Brazil) Sub": f"{animepahe_series.SUB}:por-br",
    "Japanese · Spanish Sub": f"{animepahe_series.SUB}:spa",
    "Japanese · Spanish (Latin America) Sub": f"{animepahe_series.SUB}:spa-la",
}

# How each audio track is named in the page, for saying which one was used -
# English keys, translated where they are shown.
_TRACK_NAMES = {
    animepahe_series.SUB: "Japanese · Sub",
    animepahe_series.DUB: "English Dub",
}


def _preferred_languages(settings: dict) -> list[str]:
    """The audio tracks to try, most-wanted first, from the language settings.

    Every sub language is the same subbed season, so they collapse into one
    entry at the position of the first of them.  Falls back to subtitles when
    the user has none of animepahe's languages switched on - the page still
    shows what is there rather than going blank, and _update_gap_notice() says
    the setting matched nothing.
    """
    enabled = settings_manager.get_enabled_languages(settings, SUPPORTED_LANGUAGES)
    tracks = [LANGUAGE_CODES[name].partition(":")[0] for name in enabled]
    return list(dict.fromkeys(tracks))


# ------------------------------------------------------------------
# Series-name extraction
# ------------------------------------------------------------------

def _title_from_url(url: str) -> str:
    """An animepahe series URL's slug read as a title, or "" when it has none.

    animepahe slugs are the plain title ("rent-a-girlfriend-season-4"), so the
    slug reads well enough on its own.
    """
    try:
        slug = url.split("/series/", 1)[1].strip("/").split("/", 1)[0]
    except IndexError:
        return ""
    return slug.replace("-", " ").title()


def _series_name_from_url(url: str) -> str:
    """Fallback series name derived from an animepahe series URL.

    The slug's title, once the season marker is taken off by
    :mod:`animepahe_series`.
    """
    title = _title_from_url(url)
    if not title:
        return "Unknown Series"
    base, _season, _part, _qualifier = animepahe_series.parse_title(title)
    return base or title


# ------------------------------------------------------------------
# Background worker
# ------------------------------------------------------------------

class _SeasonFetcher(QtCore.QThread):
    """Runs get_seasons() in a background thread and emits the result."""

    # ([(label, available, language, episodes), ...], series_name, notice,
    #  unavailable_reason)
    data_ready = QtCore.Signal(list, str, str, str)
    error = QtCore.Signal(str)

    def __init__(self, url: str, languages: list, parent=None):
        super().__init__(parent)
        self._url = url
        self._languages = languages

    def run(self):
        try:
            seasons, series_name, notice, reason = asyncio.run(
                get_seasons(self._url, self._languages)
            )
            self.data_ready.emit(seasons, series_name, notice, reason)
        except Exception as exc:
            self.error.emit(str(exc))


# ------------------------------------------------------------------
# Content widget
# ------------------------------------------------------------------

class AnimepaheContent(QtWidgets.QWidget):
    """Body widget for animepahe.ch series pages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # [(label, available, language, [(ep_num, title, episode_url), ...]), ...]
        # in season order, including the seasons the site does not have in the
        # chosen language (which carry no episodes and are shown disabled).
        self._seasons_data: list[tuple[str, bool, str, list]] = []
        # The audio tracks the language settings asked for, most-wanted first.
        self._languages: list[str] = []
        self._fetcher: _SeasonFetcher | None = None
        self._series_url: str = ""
        self._series_name: str = ""
        self._notice: str = ""
        self._build()

    def _build(self):
        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")

        # Says what the site is missing, so the gaps are stated as well as drawn
        # in the season list.  Warmer than the status colour because it is the
        # one thing on this page a user is likely to be surprised by.
        self.gap_label = QtWidgets.QLabel()
        self.gap_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.gap_label.setWordWrap(True)
        self.gap_label.setStyleSheet("color: #c8963c; font-size: 11px;")
        self.gap_label.hide()

        from_label = QtWidgets.QLabel(tr("From:"))
        to_label = QtWidgets.QLabel(tr("To:"))
        # At least the 35px the English labels had, more when a translation
        # needs it.
        label_width = max(35, from_label.sizeHint().width(), to_label.sizeHint().width())
        from_label.setFixedWidth(label_width)
        to_label.setFixedWidth(label_width)

        # Wide enough for "Seasons 1-13 - not on animepahe".
        self.season_start = QtWidgets.QComboBox()
        self.season_start.setFixedWidth(240)
        self.season_end = QtWidgets.QComboBox()
        self.season_end.setFixedWidth(240)

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

        self.season_start.currentIndexChanged.connect(self._on_season_start_changed)
        self.season_end.currentIndexChanged.connect(self._on_season_end_changed)
        self.episode_start.currentIndexChanged.connect(self._on_episode_start_changed)
        self.episode_end.currentIndexChanged.connect(self._on_episode_end_changed)

        from_row = QtWidgets.QHBoxLayout()
        from_row.setSpacing(8)
        from_row.addWidget(from_label)
        from_row.addWidget(self.season_start)
        from_row.addWidget(self.episode_start)

        to_row = QtWidgets.QHBoxLayout()
        to_row.setSpacing(8)
        to_row.addWidget(to_label)
        to_row.addWidget(self.season_end)
        to_row.addWidget(self.episode_end)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        layout.addWidget(self.status_label)
        layout.addWidget(self.gap_label)
        layout.addLayout(from_row)
        layout.addLayout(to_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, url: str) -> None:
        """Called by menu.py each time the user navigates to this page."""
        self._series_url = url
        self._series_name = _series_name_from_url(url)

        if self._fetcher and self._fetcher.isRunning():
            self._fetcher.data_ready.disconnect()
            self._fetcher.error.disconnect()

        self._clear_controls()
        self._set_controls_enabled(False)
        self.gap_label.hide()
        self.status_label.setText(tr("Fetching seasons…"))

        # Read afresh on every navigation, so changing Settings -> Languages
        # and coming back here takes effect without a restart.
        self._languages = _preferred_languages(settings_manager.load())

        self._fetcher = _SeasonFetcher(url, self._languages, self)
        self._fetcher.data_ready.connect(self._on_data_ready)
        self._fetcher.error.connect(self._on_error)
        self._fetcher.finished.connect(self._cleanup_fetcher)
        self._fetcher.start()

    def get_selected_urls(self) -> list[tuple]:
        """Return (url, series_name, season_label, ep_num, title) for the range.

        Inclusive of both endpoints, in season then episode order, skipping the
        seasons the site does not have.  Every tuple shares the series name, so
        all the seasons of one series land in a single download folder.
        """
        if not self._seasons_data:
            return []

        series_name = self._series_name or _series_name_from_url(self._series_url)
        start_url = self.episode_start.currentData()
        end_url = self.episode_end.currentData()

        results: list[tuple] = []
        collecting = False
        for label, available, _language, episodes in self._seasons_data:
            if not available:
                continue
            for ep_num, title, url in episodes:
                if url == start_url:
                    collecting = True
                if collecting:
                    results.append(
                        (url, series_name, label, _episode_number(ep_num), title)
                    )
                if collecting and url == end_url:
                    return results
        return results

    def _cleanup_fetcher(self):
        """Delete a finished fetcher thread so abandoned fetches don't accumulate."""
        fetcher = self.sender()
        if self._fetcher is fetcher:
            self._fetcher = None
        if fetcher is not None:
            fetcher.deleteLater()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_controls(self):
        for cb in (self.season_start, self.episode_start,
                   self.season_end, self.episode_end):
            cb.blockSignals(True)
            cb.clear()
            cb.blockSignals(False)
        self._seasons_data = []

    def _set_controls_enabled(self, enabled: bool):
        for cb in (self.season_start, self.episode_start,
                   self.season_end, self.episode_end):
            cb.setEnabled(enabled)

    def _available_positions(self) -> list[int]:
        return [i for i, (_l, available, _lang, _e) in enumerate(self._seasons_data) if available]

    def _nearest_available(self, position: int) -> int:
        """The closest season row that can actually be picked.

        The picker's disabled rows cannot be reached with the mouse or keyboard,
        but the From/To correction below moves the other box programmatically,
        which Qt will happily park on one.
        """
        available = self._available_positions()
        if not available:
            return position
        return min(available, key=lambda i: (abs(i - position), i))

    # ------------------------------------------------------------------
    # Range auto-correction
    # ------------------------------------------------------------------

    def _snap(self, combo: QtWidgets.QComboBox) -> None:
        position = combo.currentIndex()
        if 0 <= position < len(self._seasons_data) and not self._seasons_data[position][1]:
            combo.blockSignals(True)
            combo.setCurrentIndex(self._nearest_available(position))
            combo.blockSignals(False)

    def _on_season_start_changed(self):
        self._snap(self.season_start)
        self._populate_episodes(self.season_start, self.episode_start)
        if self.season_start.currentIndex() > self.season_end.currentIndex():
            self.season_end.blockSignals(True)
            self.season_end.setCurrentIndex(self.season_start.currentIndex())
            self.season_end.blockSignals(False)
            self._populate_episodes(self.season_end, self.episode_end)
            self.episode_end.setCurrentIndex(self.episode_end.count() - 1)
        self._update_gap_notice()

    def _on_season_end_changed(self):
        self._snap(self.season_end)
        self._populate_episodes(self.season_end, self.episode_end)
        if self.season_end.currentIndex() < self.season_start.currentIndex():
            self.season_start.blockSignals(True)
            self.season_start.setCurrentIndex(self.season_end.currentIndex())
            self.season_start.blockSignals(False)
            self._populate_episodes(self.season_start, self.episode_start)
            self.episode_start.setCurrentIndex(0)
        self._update_gap_notice()

    def _on_episode_start_changed(self):
        if (self.season_start.currentIndex() == self.season_end.currentIndex()
                and self.episode_start.currentIndex() > self.episode_end.currentIndex()):
            self.episode_end.blockSignals(True)
            self.episode_end.setCurrentIndex(self.episode_start.currentIndex())
            self.episode_end.blockSignals(False)

    def _on_episode_end_changed(self):
        if (self.season_start.currentIndex() == self.season_end.currentIndex()
                and self.episode_end.currentIndex() < self.episode_start.currentIndex()):
            self.episode_start.blockSignals(True)
            self.episode_start.setCurrentIndex(self.episode_end.currentIndex())
            self.episode_start.blockSignals(False)

    # ------------------------------------------------------------------
    # Data arrival
    # ------------------------------------------------------------------

    def _on_data_ready(self, seasons: list, series_name: str, notice: str,
                       unavailable_reason: str):
        self.status_label.clear()
        self._seasons_data = [(label, bool(available), language or "", episodes)
                              for label, available, language, episodes in seasons]
        self._notice = notice
        if series_name:
            self._series_name = series_name

        if not self._available_positions():
            self.status_label.setText(unavailable_reason or tr("No episodes found"))
            self._set_controls_enabled(False)
            return

        for cb in (self.season_start, self.season_end):
            cb.blockSignals(True)
            for position, (label, available, _language, _episodes) in enumerate(self._seasons_data):
                cb.addItem(label, userData=position)
                if not available:
                    self._disable_item(cb, position)
            cb.blockSignals(False)

        available = self._available_positions()
        for cb, position in ((self.season_start, available[0]),
                             (self.season_end, available[-1])):
            cb.blockSignals(True)
            cb.setCurrentIndex(position)
            cb.blockSignals(False)

        self._populate_episodes(self.season_start, self.episode_start)
        self._populate_episodes(self.season_end, self.episode_end)
        self.episode_end.setCurrentIndex(self.episode_end.count() - 1)

        self._set_controls_enabled(True)
        self._update_gap_notice()

    @staticmethod
    def _disable_item(combo: QtWidgets.QComboBox, position: int) -> None:
        """Grey one row out so a season the site lacks cannot be picked.

        Qt skips a row without ItemIsEnabled for both the mouse and the keyboard
        and draws it in the disabled colour, which is exactly the "you can see
        it is missing, you cannot choose it" behaviour wanted here.
        """
        model = combo.model()
        item = model.item(position) if hasattr(model, "item") else None
        if item is not None:
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)

    def _populate_episodes(
            self,
            season_cb: QtWidgets.QComboBox,
            episode_cb: QtWidgets.QComboBox,
    ):
        position = season_cb.currentData()
        episodes = (
            self._seasons_data[position][3]
            if isinstance(position, int) and 0 <= position < len(self._seasons_data)
            else []
        )
        episode_cb.blockSignals(True)
        episode_cb.clear()
        for ep_num, title, url in episodes:
            episode_cb.addItem(tr("Ep. {number} - {title}", number=ep_num, title=title),
                               userData=url)
        episode_cb.blockSignals(False)

    def _update_gap_notice(self) -> None:
        """Say which language is in use, what the site lacks, and any episode gap."""
        parts = []

        if not self._languages:
            parts.append(tr(
                "No animepahe language enabled - showing subtitles. "
                "Pick one in Settings → Languages"
            ))
        else:
            used = {lang for _l, available, lang, _e in self._seasons_data
                    if available and lang}
            names = [
                tr(_TRACK_NAMES[code]) for code in self._languages
                if code in used
            ]
            if names:
                parts.append(tr("Language: {names}", names=" + ".join(names)))

        if self._notice:
            parts.append(self._notice)

        for combo in (self.season_start, self.season_end):
            position = combo.currentData()
            if not isinstance(position, int) or not (0 <= position < len(self._seasons_data)):
                continue
            label, available, _language, episodes = self._seasons_data[position]
            if not available:
                continue
            gap = _episode_gap_notice(label, episodes)
            if gap and gap not in parts:
                parts.append(gap)

        text = "   ·   ".join(parts)
        self.gap_label.setText(text)
        self.gap_label.setVisible(bool(text))

    def _on_error(self, msg: str):
        self.status_label.setText(tr("Error: {message}", message=msg))
        self._set_controls_enabled(False)


def _episode_gap_notice(label: str, episodes: list) -> str:
    """"<season>: missing episode 8", or "" when its numbering is unbroken.

    Only whole numbers count: animepahe numbers recaps and specials .5, and
    their absence between two ordinary episodes is not a hole.  A season the
    site only carries the tail of - One Piece starts at episode 1100 - is
    reported as starting late rather than as a thousand missing episodes.
    """
    numbers = sorted({
        int(float(ep_num)) for ep_num, _t, _u in episodes
        if _is_number(ep_num) and float(ep_num).is_integer()
    })
    if not numbers:
        return ""

    notices = []
    if numbers[0] > 1:
        notices.append(tr("starts at episode {number}", number=numbers[0]))

    missing = [n for n in range(numbers[0], numbers[-1] + 1) if n not in numbers]
    if missing:
        listed = ", ".join(str(n) for n in missing[:6])
        if len(missing) > 6:
            listed += ", " + tr("+{count} more", count=len(missing) - 6)
        notices.append(tr("missing episode {numbers}", numbers=listed) if len(missing) == 1
                       else tr("missing episodes {numbers}", numbers=listed))

    # Clauses joined by a comma rather than worded into one sentence, so each
    # translates on its own.
    return f"{label}: {', '.join(notices)}" if notices else ""


def _is_number(text: str) -> bool:
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def _episode_number(text: str) -> "int | float":
    """An episode's number as the file name wants it: ``"7"`` → 7.

    animepahe numbers its recaps and specials between the episodes they follow
    (``"12.5"``); those stay fractional so their file sorts after episode 12
    instead of overwriting it.  Anything that is no number at all becomes 0,
    the same fallback a season with no number gets.
    """
    number = float(text) if _is_number(text) else 0.0
    if not math.isfinite(number):
        return 0
    return int(number) if number.is_integer() else number


# ------------------------------------------------------------------
# Page entry point (consumed by menu.py auto-discovery)
# ------------------------------------------------------------------

def build_content() -> QtWidgets.QWidget:
    """Return the body widget shown below the shared title bar."""
    return AnimepaheContent()


# ------------------------------------------------------------------
# Scraping
# ------------------------------------------------------------------

async def _season_episodes(session, series_url: str) -> "tuple[list, str]":
    """``([(ep_num, title, episode_url), ...], series title)`` for one season page.

    Episodes come back in ascending order; the site lists them newest first.
    The episode title on the list is always "<series> Episode <n> English
    Subbed", which says nothing the picker does not already show, so only the
    part after the series name is kept - and when that is all there is, the
    episode is named by its number alone.
    """
    try:
        html = await site_mirrors.fetch_text(session, series_url)
    except Exception as exc:
        print(f"[animepahe] season page fetch failed for {series_url}: {exc}")
        return [], ""

    soup = BeautifulSoup(html, "lxml")
    heading = soup.select_one("h1")
    series_title = heading.get_text(strip=True) if heading else ""

    episodes = []
    for item in soup.select(".eplister ul li"):
        anchor = item.find("a")
        if anchor is None or not anchor.get("href"):
            continue
        number_el = item.select_one(".epl-num")
        number = number_el.get_text(strip=True) if number_el else ""
        if not number:
            continue
        title_el = item.select_one(".epl-title")
        title = title_el.get_text(strip=True) if title_el else ""
        # Folded onto animepahe.ch even when the mirror served the page, so an
        # episode is one URL whichever domain it was listed from - that is what
        # the queue compares to spot an episode that is already queued.
        episodes.append((number, _tidy_episode_title(title, number),
                         site_mirrors.absolute(HOSTNAME, anchor["href"])))

    episodes.reverse()
    return episodes, series_title


def _lone_member(url: str, title: str) -> list:
    """A one-entry season group for a series the season index doesn't hold.

    Most such series are alone in the catalogue, and a lone entry is often a
    later season: "Link Click Season 3" is the only Link Click the site has.
    Reading its number off the title - the page's heading, else the URL's slug
    - keeps it season 3 in the picker and in the ``S03E..`` file names, with
    the seasons before it listed as missing, the same as for a grouped series.
    A title that names no season is season 1.
    """
    title = title or _title_from_url(url)
    _base, season, part, qualifier = animepahe_series.parse_title(title)
    return [season if season is not None else 1, part, qualifier, url, title]


def _tidy_episode_title(title: str, number: str) -> str:
    """Strip the boilerplate animepahe puts in every episode title."""
    text = (title or "").strip()
    for suffix in (" English Subbed", " English Dubbed", " Subbed", " Dubbed"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    marker = f"Episode {number}"
    if marker in text:
        text = text.split(marker, 1)[1].strip(" -:--")
    return text or f"Episode {number}"


async def get_seasons(url: str, languages=None) -> "tuple[list, str, str, str]":
    """Fetch every season of the series *url* belongs to.

    Returns ``([(label, available, language, episodes), ...], series_name,
    notice, unavailable_reason)`` in season order.  *languages* is the user's
    preferred audio tracks (:data:`animepahe_series.SUB` / ``DUB``) in priority
    order; each season is taken from the first of those the site has for it,
    and the row says which.  Rows the site cannot serve - a season it does not
    carry at all, or one it has only in a language that is switched off - come
    back with ``available = False`` and no episodes.  *unavailable_reason* is
    set when no row at all can be picked for that last reason, and says which
    language to switch on.

    Which entries make up the series comes from :mod:`animepahe_series`, which
    derives it from the catalogue and caches it next to the title list.  A URL
    the index has not heard of - a series the catalogue has a single entry for,
    or a link opened before the catalogue was ever fetched - is shown on its
    own, but still as the season its title names: see :func:`_lone_member`.

    Intended to be called from a background thread (e.g. _SeasonFetcher).
    """
    url = (url or "").rstrip("/")
    wanted = list(languages) if languages else [animepahe_series.SUB]

    async with aiohttp.ClientSession() as session:
        # Season pages already read while working out the group.
        by_url: dict = {}
        members = animepahe_series.seasons_for_url(url)
        if not members:
            by_url[url] = await _season_episodes(session, url)
            members = [_lone_member(url, by_url[url][1])]

        slots = animepahe_series.season_slots(members, wanted)
        notice = animepahe_series.missing_summary(members)
        series_name = animepahe_series.base_name(members)

        fetchable = [slot for slot in slots
                     if slot[3] and slot[1] and slot[1] not in by_url]
        fetched = await asyncio.gather(
            *(_season_episodes(session, slot[1]) for slot in fetchable)
        )
    by_url.update({slot[1]: result for slot, result in zip(fetchable, fetched)})

    seasons = []
    for label, season_url, _title, available, language, _version, has in slots:
        if not available:
            # Name the language when that is the reason, so the row explains
            # itself rather than reading like the season is missing outright.
            if has:
                missing_in = _TRACK_NAMES.get(
                    wanted[0] if wanted else animepahe_series.SUB, "this language"
                )
                label = f"{label} - {tr('no {language}', language=tr(missing_in))}"
            seasons.append((label, False, "", []))
            continue
        episodes, _series_title = by_url.get(season_url, ([], ""))
        # A season the site lists but serves no episodes for would be a dead
        # entry in the picker, so it is shown as missing instead.
        seasons.append((label, bool(episodes), language or "", episodes))

    if not series_name:
        first = next((title for _episodes, title in by_url.values() if title), "")
        base, _s, _p, _q = animepahe_series.parse_title(first) if first else ("", None, None, "")
        series_name = base or _series_name_from_url(url)

    # Nothing pickable, but the site does have the series in a language that is
    # switched off - typically a dub animepahe lists under its English name.
    # Saying so beats a bare "No episodes found" for a series that has them.
    unavailable_reason = ""
    if not any(available for _label, available, _language, _episodes in seasons):
        offered = [code for code in (animepahe_series.SUB, animepahe_series.DUB)
                   if any(code in slot[6] for slot in slots) and code not in wanted]
        if offered:
            unavailable_reason = tr(
                "Only available as {languages} - switch it on in Settings → Languages",
                languages=" / ".join(tr(_TRACK_NAMES[code]) for code in offered),
            )

    return seasons, series_name, notice, unavailable_reason


# ------------------------------------------------------------------
# URL converter  (episode page URL → provider URL)
# ------------------------------------------------------------------
# An animepahe episode page comes in one of two layouts, and which one a show
# gets depends on where the site sourced it, not on anything the page says:
#
# * A MegaPlay player - "Agents of the Four Seasons: Dance of Spring", and most
#   of the catalogue.  The page's "Select Video Server" menu lists it (each
#   option a base64-encoded <iframe>) and the player box shows the first one.
#   MegaPlay is the player behind anikototv's Vidstream server too, so
#   downloaders/Vidstream.py downloads it - and it is where every subtitle
#   language comes from: the video carries none of its own, each language is a
#   separate track, and the download embeds the one that was asked for.
# * A Blogger player with a download box under it - "Link Click Season 3".
#   There is no server menu.  The box links the file on kwik (Kiwi-Stream) and
#   on gofile, and the player streams the same video from Google's servers
#   (downloaders/Blogger.py).  These videos have English subtitles burned in,
#   so they can serve English subs and nothing else.
#
# The box's labels can't be trusted - its "Gofiles" row links kwik as often as
# gofile - so links are sorted by where they point.  gofile is left out: its API
# refuses guest accounts, and the same file is always on Blogger as well.  The
# other embed hosts seen on the site (embtaku, s3taku, gogoanime.org.es, megaup,
# megacloud) no longer answer, and a few episode pages carry no video at all;
# those simply offer nothing, and the worker reports them as unavailable.

# Named as the embedding site in MegaPlay URLs - see downloaders/Vidstream.py.
_REFERER = f"https://{HOSTNAME}/"

# How long a page that failed to load is remembered as failed.  Long enough that
# the worker's run through every language/quality/provider combination does not
# reload it once per combination, short enough that the queue's later retry of
# the episode fetches it afresh.
_FAILED_PAGE_TTL = 120.0


class _EpisodePage(NamedTuple):
    """What one episode page offers to download."""

    track: str              # animepahe_series.SUB or DUB - the page's audio
    megaplay: list[str]     # MegaPlay embed URLs, in the page's order
    blogger: list[str]      # Blogger player URLs
    kwik: dict[str, str]    # {"720p": kwik page URL, ...} from the download box


# The worker asks about one (language, quality, provider) combination at a time,
# so the same episode page is consulted dozens of times; it is fetched once.
_episode_pages: dict[str, _EpisodePage] = {}
_failed_pages: dict[str, float] = {}   # episode URL -> monotonic() of the failure
_episode_lock = threading.Lock()


def _absolute(url: str) -> str:
    """A player/link URL as found in the page, made absolute and unescaped."""
    url = unescape(url or "").strip()
    return "https:" + url if url.startswith("//") else url


def _embed_urls(soup: BeautifulSoup) -> list[str]:
    """Every player the page offers: its player box, then its server menu."""
    found = []
    iframe = soup.select_one("#pembed iframe[src]")
    if iframe is not None:
        found.append(iframe["src"])
    for option in soup.select("select.mirror option[value]"):
        value = (option.get("value") or "").strip()
        if not value:
            continue
        try:
            decoded = base64.b64decode(value).decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            continue
        match = re.search(r"""src\s*=\s*["']([^"']+)""", decoded, re.IGNORECASE)
        if match:
            found.append(match.group(1))
    return list(dict.fromkeys(_absolute(url) for url in found if url))


def _is_megaplay(url: str) -> bool:
    parts = urlsplit(url)
    return "megaplay." in parts.netloc and parts.path.startswith("/stream/")


def _is_blogger(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.netloc.endswith("blogger.com") and parts.path == "/video.g"
            and "token=" in parts.query)


def _kwik_links(soup: BeautifulSoup) -> dict[str, str]:
    """``{quality label: kwik URL}`` from the page's download box."""
    links: dict[str, str] = {}
    for row in soup.select("div.dlbox li"):
        anchor = row.select_one("span.e a[href]")
        if anchor is None:
            continue
        url = _absolute(anchor["href"])
        if "kwik." not in urlsplit(url).netloc:
            continue
        quality = row.select_one("span.w")
        digits = re.sub(r"\D", "", quality.get_text()) if quality else ""
        links.setdefault(f"{digits}p" if digits else "unknown", url)
    return links


def _page_track(soup: BeautifulSoup, episode_url: str) -> str:
    """Whether the page is the subbed or the dubbed version of the episode.

    The page marks it itself (``<span class="lg">Sub</span>``); the URL is the
    fallback, since only a dub entry's episodes have "dub" in their slug.
    """
    marker = soup.select_one(".lm .lg") or soup.select_one("span.lg")
    text = marker.get_text(strip=True).lower() if marker else ""
    if text in (animepahe_series.SUB, animepahe_series.DUB):
        return text
    slug = episode_url.rstrip("/").rsplit("/", 1)[-1].lower()
    return animepahe_series.DUB if "-dub-" in f"-{slug}-" else animepahe_series.SUB


def _parse_episode_page(page_html: str, episode_url: str) -> _EpisodePage:
    soup = BeautifulSoup(page_html, "lxml")
    embeds = _embed_urls(soup)
    return _EpisodePage(
        track=_page_track(soup, episode_url),
        megaplay=[url for url in embeds if _is_megaplay(url)],
        blogger=[url for url in embeds if _is_blogger(url)],
        kwik=_kwik_links(soup),
    )


def _episode_page(episode_url: str) -> "_EpisodePage | None":
    """The parsed episode page, fetched once per episode.

    None means the page could not be loaded from any of the site's domains -
    reported here, so the caller can treat None purely as "no URL".
    """
    with _episode_lock:
        page = _episode_pages.get(episode_url)
        failed_at = _failed_pages.get(episode_url)
    if page is not None:
        return page
    if failed_at is not None and monotonic() - failed_at < _FAILED_PAGE_TTL:
        return None

    try:
        # Through site_mirrors, so animepahe.ng answers when animepahe.ch won't.
        page = _parse_episode_page(site_mirrors.read_text(episode_url), episode_url)
    except Exception as exc:
        print(f"[animepahe] could not load {episode_url}: {exc}")
        with _episode_lock:
            _failed_pages[episode_url] = monotonic()
        return None

    with _episode_lock:
        _episode_pages[episode_url] = page
        _failed_pages.pop(episode_url, None)
    return page


def _vidstream_url(page: _EpisodePage, subtitle: str) -> str | None:
    """The first MegaPlay embed that can serve *subtitle*, as Vidstream takes it.

    English goes ahead even when the episode lists no English track, as it does
    on anikototv: some MegaPlay uploads have their subtitles burned in, and
    turning those away would lose the episode for nothing.  Any other language
    only counts when the episode really has that track, so the worker moves on
    to the next language instead of saving one with the wrong subtitles.
    """
    for embed in page.megaplay:
        if (subtitle and subtitle != "eng" and not Vidstream.subtitle_track(
                f"{embed}#{urlencode({'referer': _REFERER})}", subtitle)):
            continue
        params = {"subtitles": subtitle} if subtitle else {}
        return f"{embed}#{urlencode({**params, 'referer': _REFERER})}"
    return None


def _kiwi_stream_url(page: _EpisodePage) -> str | None:
    """The download box's kwik page, with all of its kwik links by quality.

    downloaders/KiwiStream.py picks the one for the tier being tried out of
    the fragment, the way it picks from anikototv's per-quality list.
    """
    if not page.kwik:
        return None
    first = next(iter(page.kwik.values()))
    return f"{first}#{urlencode(page.kwik)}"


def get_provider_url(episode_url: str, language_code: str, provider: str) -> str | None:
    """Resolve an animepahe episode page to the URL a provider downloader takes.

    - ``"Vidstream"``   → the MegaPlay embed URL for ``downloaders/Vidstream.py``,
      with ``#subtitles=<code>`` for sub languages and the site as referer
    - ``"Kiwi-Stream"`` → the download box's kwik page for
      ``downloaders/KiwiStream.py``, its kwik links listed in the fragment
    - ``"Blogger"``     → the Blogger player URL for ``downloaders/Blogger.py``

    Returns None when the page does not offer *provider*, when the page is the
    other audio track (a dub page for a sub language, or the reverse), when the
    subtitle language can't be had - MegaPlay without that track, or kwik and
    Blogger, whose subtitles are burned-in English - or when the page can't be
    fetched.

    Parameters
    ----------
    episode_url:
        Full animepahe episode URL, e.g.
        ``https://animepahe.ch/link-click-season-3-episode-1-english-subbed/``.
    language_code:
        Site-internal language code from ``LANGUAGE_CODES`` - ``"dub"`` or
        ``"sub:<subtitle code>"``, e.g. ``"sub:fra"``.
    provider:
        Provider display name from ``SUPPORTED_PROVIDERS``.
    """
    try:
        page = _episode_page(episode_url)
        track, _, subtitle = language_code.partition(":")
        if page is None or page.track != track:
            return None
        if provider == "Vidstream":
            return _vidstream_url(page, subtitle)
        if subtitle not in ("", "eng"):
            return None
        if provider == "Kiwi-Stream":
            return _kiwi_stream_url(page)
        if provider == "Blogger":
            return page.blogger[0] if page.blogger else None
        return None

    except Exception as exc:
        print(f"[animepahe] get_provider_url({episode_url!r}, {language_code!r}, {provider!r}): {exc}")
        return None
