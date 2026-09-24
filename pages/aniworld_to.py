from PySide6 import QtWidgets, QtCore
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import requests
import threading

import browser_fetch
from i18n import tr

# The hostname this page handles (without www.)
HOSTNAME = "aniworld.to"

# Providers this site actually supports.
SUPPORTED_PROVIDERS = ["VOE", "Vidmoly", "Doodstream", "Filemoon", "Vidoza", "SpeedFiles"]

# Languages this site actually supports.
SUPPORTED_LANGUAGES = ["German Dub", "Japanese · German Sub", "Japanese · English Sub"]

# Maps global language display names → aniworld ``data-lang-key`` values.
# aniworld uses numeric language keys on its hoster <li> elements:
#   1 = German Dub, 2 = Japanese with English subtitles,
#   3 = Japanese with German subtitles.
# (The previous "de"/"des"/"jps" values were bs.to codes and never matched
#  anything on aniworld, so get_provider_url() always returned None and every
#  download was skipped.)
LANGUAGE_CODES: dict[str, str] = {
    "German Dub":             "1",
    "Japanese · English Sub": "2",
    "Japanese · German Sub":  "3",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Per-process cache: episode URL -> fetched page HTML.
# get_provider_url is invoked once per (language, quality, provider) combination
# for the *same* episode page, and the page content is identical across all of
# them.  Caching means we clear Cloudflare at most once per episode instead of
# spinning up a browser for every lookup.
_page_cache: dict[str, str] = {}
_page_cache_lock = threading.Lock()


# ------------------------------------------------------------------
# Cloudflare-aware page fetching
# ------------------------------------------------------------------

def _fetch_episode_html(url: str) -> str:
    """Return the HTML of an episode page, transparently defeating Cloudflare.

    Fast path: a normal ``requests.get``.  Only if that comes back as a
    Cloudflare challenge (or fails) do we fall back to the real-browser path.
    The final HTML is cached per URL so repeated provider/language lookups for
    the same episode never re-fetch.
    """
    with _page_cache_lock:
        cached = _page_cache.get(url)
    if cached is not None:
        return cached

    html = ""
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        if not browser_fetch.looks_like_cloudflare(response.text, response.status_code):
            html = response.text
    except Exception as exc:
        print(f"[aniworld] requests fetch failed for {url}: {exc}")

    # Fast path blocked or errored - use the browser fallback.
    if not html:
        print(f"[aniworld] Cloudflare detected, using browser fallback for {url}")
        html = browser_fetch.fetch(url, "aniworld")

    with _page_cache_lock:
        _page_cache[url] = html
    return html


# ------------------------------------------------------------------
# URL converter  (episode page URL → provider redirect URL)
# ------------------------------------------------------------------

def get_provider_url(episode_url: str, language_code: str, provider: str) -> str | None:
    """Resolve an aniworld episode page URL to a provider redirect URL.

    Fetches the episode page (clearing Cloudflare when necessary), finds the
    hoster ``<li>`` element that matches *language_code* (data-lang-key
    attribute) and *provider* (inner h4 text), and returns the full
    ``https://aniworld.to/redirect/…`` URL.

    Returns ``None`` when the language/provider combination is not available
    for this episode or when the page cannot be fetched.

    Parameters
    ----------
    episode_url:
        Full aniworld episode URL, e.g.
        ``https://aniworld.to/anime/stream/series/staffel-1/episode-1``.
    language_code:
        Site-internal language key from ``LANGUAGE_CODES``, e.g. ``"1"``.
    provider:
        Provider display name as it appears on the site, e.g. ``"VOE"``.
    """
    try:
        html = _fetch_episode_html(episode_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Each hoster button is an <li data-lang-key="…" data-link-target="…">
        # containing an <h4> with the provider name.
        for li in soup.find_all("li", {"data-lang-key": language_code}):
            h4 = li.find("h4")
            if h4 and h4.get_text(strip=True) == provider:
                href = li.get("data-link-target", "")
                if href:
                    return "https://aniworld.to" + href

        return None  # language or provider not available for this episode

    except Exception as exc:
        print(f"[aniworld] get_provider_url({episode_url!r}, {language_code!r}, {provider!r}): {exc}")
        return None


# ------------------------------------------------------------------
# Series-name extraction
# ------------------------------------------------------------------

def _series_name_from_url(series_url: str) -> str:
    """Derive a human-readable series name from an aniworld series/episode URL.

    aniworld URLs are shaped like
    ``https://aniworld.to/anime/stream/<slug>/staffel-1/episode-1`` - the path
    segment right after ``stream/`` is the series slug.  The slug is turned into
    a tidy folder name (hyphens → spaces, title-cased).
    """
    try:
        slug = series_url.split("/anime/stream/", 1)[1].split("/", 1)[0]
    except IndexError:
        slug = ""
    slug = slug.strip()
    if not slug:
        return "Unknown Series"
    return slug.replace("-", " ").title()


# ------------------------------------------------------------------
# Background worker
# ------------------------------------------------------------------

class _SeasonFetcher(QtCore.QThread):
    """Runs get_seasons() in a background thread and emits the result."""

    data_ready = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            self.data_ready.emit(asyncio.run(get_seasons(self._url)))
        except Exception as exc:
            self.error.emit(str(exc))


# ------------------------------------------------------------------
# Content widget
# ------------------------------------------------------------------

class AniWorldContent(QtWidgets.QWidget):
    """Body widget for aniworld.to series pages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seasons_data: dict[str, list[tuple]] = {}
        self._fetcher: _SeasonFetcher | None = None
        # Series page URL of the currently loaded series - used to derive the
        # top-level download folder name in get_selected_urls().
        self._series_url: str = ""
        self._build()

    def _build(self):
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

        self.season_start = QtWidgets.QComboBox()
        self.season_start.setFixedWidth(110)
        self.season_end = QtWidgets.QComboBox()
        self.season_end.setFixedWidth(110)

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
        layout.addLayout(from_row)
        layout.addLayout(to_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, url: str) -> None:
        """Called by menu.py each time the user navigates to this page."""
        # Remember the series URL so we can derive the download folder name.
        self._series_url = url

        if self._fetcher and self._fetcher.isRunning():
            self._fetcher.data_ready.disconnect()
            self._fetcher.error.disconnect()

        self._clear_controls()
        self._set_controls_enabled(False)
        self.status_label.setText(tr("Fetching seasons…"))

        self._fetcher = _SeasonFetcher(url, self)
        self._fetcher.data_ready.connect(self._on_data_ready)
        self._fetcher.error.connect(self._on_error)
        # Built-in finished (after run() returns) deletes the thread so finished
        # or abandoned fetchers don't accumulate over a session.
        self._fetcher.finished.connect(self._cleanup_fetcher)
        self._fetcher.start()

    def _cleanup_fetcher(self):
        """Delete a finished fetcher thread (built-in finished) so it doesn't leak.

        Clears the reference only when this is still the current fetcher, so an
        abandoned earlier fetch cleans itself up without disturbing a newer one.
        """
        fetcher = self.sender()
        if self._fetcher is fetcher:
            self._fetcher = None
        if fetcher is not None:
            fetcher.deleteLater()

    def get_selected_urls(self) -> list[tuple]:
        """Return (url, series_name, season_label, ep_num_in_season, title).

        Inclusive of both endpoints, in natural season/episode order.  The
        series name is shared by every tuple and used as the top-level
        download folder.
        """
        if not self._seasons_data:
            return []

        series_name = _series_name_from_url(self._series_url)
        start_url = self.episode_start.currentData()
        end_url   = self.episode_end.currentData()

        results: list[tuple] = []
        collecting = False

        for season_key, episodes in self._seasons_data.items():
            label = _season_label(season_key)
            for ep_num, title, _overall, url in episodes:
                if url == start_url:
                    collecting = True
                if collecting:
                    results.append((url, series_name, label, ep_num, title))
                if collecting and url == end_url:
                    return results

        return results  # fallback - should not normally be reached

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_controls(self):
        for cb in (self.season_start, self.episode_start,
                   self.season_end, self.episode_end):
            cb.blockSignals(True)
            cb.clear()
            cb.blockSignals(False)
        self._seasons_data = {}

    def _set_controls_enabled(self, enabled: bool):
        for cb in (self.season_start, self.episode_start,
                   self.season_end, self.episode_end):
            cb.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Range auto-correction
    # ------------------------------------------------------------------

    def _on_season_start_changed(self):
        self._populate_episodes(self.season_start, self.episode_start)
        if self.season_start.currentIndex() > self.season_end.currentIndex():
            self.season_end.blockSignals(True)
            self.season_end.setCurrentIndex(self.season_start.currentIndex())
            self.season_end.blockSignals(False)
            self._populate_episodes(self.season_end, self.episode_end)
            self.episode_end.setCurrentIndex(self.episode_end.count() - 1)

    def _on_season_end_changed(self):
        self._populate_episodes(self.season_end, self.episode_end)
        if self.season_end.currentIndex() < self.season_start.currentIndex():
            self.season_start.blockSignals(True)
            self.season_start.setCurrentIndex(self.season_end.currentIndex())
            self.season_start.blockSignals(False)
            self._populate_episodes(self.season_start, self.episode_start)
            self.episode_start.setCurrentIndex(0)

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

    def _on_data_ready(self, raw: dict):
        self.status_label.clear()

        overall = 0
        for season_key in sorted(raw, key=_season_sort_key):
            is_movies = not season_key.split("_", 1)[1].isdigit()
            season_episodes = []
            for ep_key in sorted(raw[season_key], key=lambda k: int(k.split("_")[1])):
                ep_num = int(ep_key.split("_")[1])
                url, title = next(iter(raw[season_key][ep_key].items()))
                if not is_movies:
                    overall += 1
                season_episodes.append((ep_num, title, overall if not is_movies else None, url))
            self._seasons_data[season_key] = season_episodes

        for cb in (self.season_start, self.season_end):
            cb.blockSignals(True)
            for key in self._seasons_data:
                cb.addItem(_season_label(key), userData=key)
            cb.blockSignals(False)

        self.season_end.blockSignals(True)
        self.season_end.setCurrentIndex(self.season_end.count() - 1)
        self.season_end.blockSignals(False)

        self._populate_episodes(self.season_start, self.episode_start)
        self._populate_episodes(self.season_end, self.episode_end)

        self.episode_end.setCurrentIndex(self.episode_end.count() - 1)
        self._set_controls_enabled(True)

    def _populate_episodes(
            self,
            season_cb: QtWidgets.QComboBox,
            episode_cb: QtWidgets.QComboBox,
    ):
        episodes = self._seasons_data.get(season_cb.currentData(), [])
        episode_cb.blockSignals(True)
        episode_cb.clear()
        for ep_num, title, overall, url in episodes:
            text = (
                tr("Ep. {number} - {title}  (Overall: {overall})",
                   number=ep_num, title=title, overall=overall)
                if overall is not None
                else tr("Movie {number} - {title}", number=ep_num, title=title)
            )
            episode_cb.addItem(text, userData=url)
        episode_cb.blockSignals(False)

    def _on_error(self, msg: str):
        self.status_label.setText(tr("Error: {message}", message=msg))
        self._set_controls_enabled(False)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _season_sort_key(key: str) -> int:
    part = key.split("_", 1)[1]
    return -1 if not part.isdigit() else int(part)


def _season_label(key: str) -> str:
    part = key.split("_", 1)[1]
    return "Movies" if not part.isdigit() else f"Season {part}"


# ------------------------------------------------------------------
# Page entry point (consumed by menu.py auto-discovery)
# ------------------------------------------------------------------

def build_content() -> QtWidgets.QWidget:
    return AniWorldContent()


# ------------------------------------------------------------------
# Scraping
# ------------------------------------------------------------------
# Every page is asked for with a plain request first.  One that aniworld refuses
# with HTTP 403 - Cloudflare turning the request away - is loaded again in an
# undetected browser instead (see browser_fetch).  Chrome is only started once a
# page has actually been refused, and one browser serves every refused page of
# the series, so a blocked season list costs a single launch rather than one
# per season.

async def get_seasons(url: str) -> dict:
    """Fetch all seasons and their episodes concurrently."""
    with browser_fetch.Browser("aniworld") as browser:
        async with aiohttp.ClientSession() as session:
            html = await _fetch_page(session, url)
            refused = html is None
            if refused:
                html = _fetch_refused_page(browser, url)

            soup = BeautifulSoup(html, "lxml")
            page_elements = soup.select("div.hosterSiteDirectNav ul li a:not([data-episode-id])")
            if refused and not page_elements:
                raise RuntimeError(tr(
                    "aniworld.to refused the request (HTTP 403) and the browser "
                    "fallback could not get past it either"
                ))

            season_items = [
                (element.text.strip().replace("Filme", "0"), "https://aniworld.to" + element.get("href"))
                for element in page_elements
            ]

            pages = await asyncio.gather(
                *(_fetch_page(session, season_url) for _season, season_url in season_items)
            )

        # Refused season pages are loaded only once every plain request is
        # back: it is one browser, driven one page at a time, and blocking in
        # it mid-gather would stall the requests still in flight.
        results = [
            _parse_episodes(
                page if page is not None else _fetch_refused_page(browser, season_url),
                season,
            )
            for page, (season, season_url) in zip(pages, season_items)
        ]

    return {
        # The films tab is mapped to the sentinel season "0" above; turn only
        # that exact value into the Movies key.  Using str.replace("0", ...)
        # here would corrupt every season number containing a 0 (10, 20, …),
        # relabelling them as extra "Movies" entries.
        ("Season_Movies" if season == "0" else f"Season_{season}"): episodes
        for (season, _), episodes in zip(season_items, results)
    }


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> "str | None":
    """The page at *url*, or None when aniworld refused it with HTTP 403."""
    async with session.get(url) as response:
        if response.status == 403:
            return None
        return await response.text()


def _fetch_refused_page(browser: browser_fetch.Browser, url: str) -> str:
    """Load a page aniworld refused with HTTP 403 through the browser."""
    print(f"[aniworld] {url} refused with HTTP 403 - loading it in the browser instead")
    return browser.fetch(url)


def _parse_episodes(html: str, season_number: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    episodes_dict = {}

    for episode_num, element in enumerate(soup.select(f"tbody#season{season_number} tr"), start=1):
        element_td = element.find("td", class_="seasonEpisodeTitle")
        element_a = element_td.find("a")
        href = element_a.get("href")
        episode_title = element_a.find("span").text.strip()
        # Some episodes append an "[Episode 001]" marker inside the span. It is
        # always at the end, so cut everything from the marker onward so it
        # doesn't leak into the title (and the filename).
        if " [Episode " in episode_title:
            episode_title = episode_title[:episode_title.index(" [Episode ")]
        episodes_dict[f"Episode_{episode_num}"] = {"https://aniworld.to" + href: episode_title}

    return episodes_dict