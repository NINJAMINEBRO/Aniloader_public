from PySide6 import QtWidgets, QtCore
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import threading

import site_mirrors
from i18n import tr

# The hostname this page handles (without www.)
HOSTNAME = "s.to"

# Providers this site actually supports.
# settings_manager.get_enabled_providers(settings_state, SUPPORTED_PROVIDERS)
# returns the intersection with the global list in user-configured priority order.
SUPPORTED_PROVIDERS = ["VOE", "Doodstream", "Vidoza"]

# Languages this site actually supports, using the global display names as keys.
# settings_manager.get_enabled_languages(settings_state, SUPPORTED_LANGUAGES)
# returns the intersection with the global list in user-configured priority order.
SUPPORTED_LANGUAGES = ["German Dub", "English Dub", "Japanese · German Sub"]

# Maps global language display names to s.to's ``data-language-label`` values
# on the hoster buttons.  These are the exact strings the site writes into the
# markup - "Englisch", not "English" - so they are matched literally and a near
# miss silently costs the user that whole language.
LANGUAGE_CODES: dict[str, str] = {
    "German Dub": "Deutsch",
    "English Dub": "Englisch",
    "Japanese · German Sub": "Ger-Sub",
}


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

class SToContent(QtWidgets.QWidget):
    """Body widget for s.to series pages.

    Call load(url) whenever the user navigates here; it fires a background
    fetch and populates the four selection combos when data arrives.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # season_key -> [(ep_num_in_season, title, overall_num, url), ...]
        self._seasons_data: dict[str, list[tuple]] = {}
        self._fetcher: _SeasonFetcher | None = None
        # Series page URL of the currently loaded series (for the download folder).
        self._series_url: str = ""
        self._build()

    def _build(self):
        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")

        # "From:" / "To:" labels - identical width keeps the columns aligned
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
        self._series_url = url

        if self._fetcher and self._fetcher.isRunning():
            # Abandon the previous fetch - its signal is disconnected so any
            # late result will be silently dropped.
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

        Inclusive of both endpoints, in natural season/episode order.
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

        return results # fallback - should not normally be reached

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

        # Build internal structure, computing a running overall episode number.
        # Movie seasons are excluded from the overall count.
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

        # Populate season combos (signals still blocked per-combo below)
        for cb in (self.season_start, self.season_end):
            cb.blockSignals(True)
            for key in self._seasons_data:
                cb.addItem(_season_label(key), userData=key)
            cb.blockSignals(False)

        # season_end defaults to the last season
        self.season_end.blockSignals(True)
        self.season_end.setCurrentIndex(self.season_end.count() - 1)
        self.season_end.blockSignals(False)

        # Populate episode combos based on current season selections
        self._populate_episodes(self.season_start, self.episode_start)
        self._populate_episodes(self.season_end, self.episode_end)

        # episode_end defaults to the last episode of the last season
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
    """Sort seasons numerically; non-numeric suffixes (e.g. 'Filme') sort first."""
    part = key.split("_", 1)[1]
    return -1 if not part.isdigit() else int(part)


def _season_label(key: str) -> str:
    part = key.split("_", 1)[1]
    return "Movies" if not part.isdigit() else f"Season {part}"


# ------------------------------------------------------------------
# Page entry point (consumed by menu.py auto-discovery)
# ------------------------------------------------------------------

def build_content() -> QtWidgets.QWidget:
    """Return the body widget shown below the shared title bar."""
    return SToContent()


# ------------------------------------------------------------------
# Series-name extraction + URL converter (episode page → hoster redirect)
# ------------------------------------------------------------------

def _series_name_from_url(series_url: str) -> str:
    """Derive a tidy series name from an s.to series/episode URL.

    s.to URLs look like ``https://s.to/serie/<slug>/staffel-1/episode-1``.
    """
    try:
        slug = series_url.split("/serie/", 1)[1].split("/", 1)[0]
    except IndexError:
        slug = ""
    slug = slug.strip()
    if not slug:
        return "Unknown Series"
    return slug.replace("-", " ").title()


# The worker asks for one (language, quality, provider) combination at a time,
# so a single episode is resolved dozens of times over.  The page behind all of
# those calls is the same one, so it is fetched once and reused.
_page_cache: dict[str, BeautifulSoup | None] = {}
# Episodes whose available combinations have already been listed, so a run of
# unavailable combos reports the page's contents once instead of per attempt.
_reported: set[str] = set()
_page_lock = threading.Lock()


def _episode_page(episode_url: str) -> BeautifulSoup | None:
    """The parsed episode page, fetched once per episode.

    None means the page could not be fetched from any of the site's domains -
    reported here, so the caller can treat None purely as "no URL".
    """
    with _page_lock:
        if episode_url in _page_cache:
            return _page_cache[episode_url]

    try:
        # Read through site_mirrors so serienstream.to answers when s.to will not.
        soup = BeautifulSoup(site_mirrors.read_text(episode_url), "lxml")
    except Exception as exc:
        print(f"[s.to] could not load {episode_url}: {exc}")
        soup = None

    with _page_lock:
        _page_cache[episode_url] = soup
    return soup


def _report_missing(episode_url: str, soup: BeautifulSoup,
                    language_code: str, provider: str) -> None:
    """Say what the episode *does* offer when the asked-for combination is absent.

    Without this, "not available" is indistinguishable from a site that could
    not be reached at all - the two have very different fixes, and guessing
    which one applies wastes a lot of time.  Printed once per episode, since the
    worker asks about many combinations in a row.
    """
    with _page_lock:
        if episode_url in _reported:
            return
        _reported.add(episode_url)

    offered = sorted({
        f"{b.get('data-language-label')} / {b.get('data-provider-name')}"
        for b in soup.find_all("button")
        if b.get("data-language-label") and b.get("data-provider-name")
    })
    print(f"[s.to] {episode_url} offers: {', '.join(offered) or 'nothing'} "
          f"(asked for {language_code} / {provider})")


def get_provider_url(episode_url: str, language_code: str, provider: str) -> str | None:
    """Resolve an s.to episode page to a provider redirect URL.

    Each hoster on an s.to episode page is a ``<button>`` carrying
    ``data-language-label``, ``data-provider-name`` and ``data-play-url``.
    We match the language + provider and return the absolute play URL, or
    ``None`` when that combination isn't offered for this episode.
    """
    soup = _episode_page(episode_url)
    if soup is None:
        return None # unreachable - _episode_page reported it

    button = soup.find(
        "button",
        {"data-language-label": language_code, "data-provider-name": provider},
    )
    if not button:
        _report_missing(episode_url, soup, language_code, provider)
        return None
    href = button.get("data-play-url", "")
    if not href:
        return None
    # The provider downloader fetches this redirect itself, outside this
    # module's retry loop, so it is handed the domain currently known to be
    # up rather than the canonical one.
    return site_mirrors.live_url(site_mirrors.absolute(HOSTNAME, href))


# ------------------------------------------------------------------
# Scraping
# ------------------------------------------------------------------

# seasons = asyncio.run(get_seasons(url)) must be run like this
async def get_seasons(url: str) -> dict:
    """Fetches all seasons and their episodes concurrently.
    Movies are listed under Season_0.
    """
    async with aiohttp.ClientSession() as session:
        # 1. Fetch the series page to discover all season links
        html = await site_mirrors.fetch_text(session, url)

        soup = BeautifulSoup(html, "lxml")
        page_elements = soup.select("nav.mb-2 ul li a")

        season_items = [
            (element.text.strip().replace("Filme", "0"),
             site_mirrors.absolute(HOSTNAME, element.get("href")))
            for element in page_elements
        ]

        # 2. Fetch all season episode pages concurrently
        tasks = [_get_episodes(season_url, season, session) for season, season_url in season_items]
        results = await asyncio.gather(*tasks)

    return {
        # "Filme" is mapped to the sentinel season "0" above; turn only that
        # exact value into the Movies key.  str.replace("0", ...) here would
        # corrupt every season number containing a 0 (10, 20, …), relabelling
        # them as extra "Movies" entries and hiding those seasons.
        ("Season_Movies" if season == "0" else f"Season_{season}"): episodes
        for (season, _), episodes in zip(season_items, results)
    }


async def _get_episodes(url: str, season_number: str, session: aiohttp.ClientSession) -> dict:
    """Fetches and parses one season page, returning its episodes dict."""
    html = await site_mirrors.fetch_text(session, url)

    soup = BeautifulSoup(html, "lxml")
    page_elements = soup.select(f"tbody tr")
    episodes_dict = {}

    for episode_num, element in enumerate(page_elements, start=1):
        onclick_text = element.get("onclick")
        href = onclick_text.split("'")[1]

        element_td = element.find("td", class_="fw-medium episode-title-cell")
        episode_title = element_td.find("span").text.strip()

        episodes_dict[f"Episode_{episode_num}"] = {
            site_mirrors.absolute(HOSTNAME, href): episode_title
        }

    return episodes_dict