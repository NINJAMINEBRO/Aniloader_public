import asyncio
import threading
from urllib.parse import urljoin, urlsplit

import aiohttp
from PySide6 import QtWidgets, QtCore
from seleniumbase import SB
from bs4 import BeautifulSoup

import anikototv_series
from downloaders import KiwiStream, Vidstream, common
from i18n import tr

# The hostname this page handles (without www.)
HOSTNAME = "anikototv.to"

# Providers this site actually supports.
# settings_manager.get_enabled_providers(settings_state, SUPPORTED_PROVIDERS)
# returns the intersection with the global list in user-configured priority order.
SUPPORTED_PROVIDERS = ["Kiwi-Stream", "Vidstream"]

# Languages this site actually supports, using the global display names as keys.
# settings_manager.get_enabled_languages(settings_state, SUPPORTED_LANGUAGES)
# returns the intersection with the global list in user-configured priority order.
SUPPORTED_LANGUAGES = [
    "English Dub",
    "Japanese · English Sub",
    "Japanese · Portuguese (Brazil) Sub",
    "Japanese · Spanish Sub",
    "Japanese · Spanish (Latin America) Sub",
    "Japanese · German Sub",
    "Japanese · French Sub",
    "Japanese · Indonesian Sub",
    "Japanese · Thai Sub",
    "Japanese · Vietnamese Sub",
]

# Maps global language display names to the site-internal identifiers used when
# picking a download.  anikototv splits both its servers (Vidstream, …) and its
# Kiwi-Stream downloads into a ``"sub"`` (subbed) and a ``"dub"`` (dubbed)
# track.  Sub entries add the subtitle language after a colon - a key of
# downloaders/Vidstream.py's SUBTITLE_LANGUAGES - which Vidstream embeds into
# the download; get_provider_url() splits the two apart.
LANGUAGE_CODES: dict[str, str] = {
    "English Dub": "dub",
    "Japanese · English Sub": "sub:eng",
    "Japanese · Portuguese (Brazil) Sub": "sub:por-br",
    "Japanese · Spanish Sub": "sub:spa",
    "Japanese · Spanish (Latin America) Sub": "sub:spa-la",
    "Japanese · German Sub": "sub:deu",
    "Japanese · French Sub": "sub:fra",
    "Japanese · Indonesian Sub": "sub:ind",
    "Japanese · Thai Sub": "sub:tha",
    "Japanese · Vietnamese Sub": "sub:vie",
}


# ------------------------------------------------------------------
# Watch-page fetching + caching
# ------------------------------------------------------------------
# get_provider_url() is called once per (language, quality, provider) combination
# for the *same* episode, and the watch page is identical across all of them, so
# the fetched HTML is cached per URL.  The server list is filled in by script
# once the page has loaded, so unlike the episode list - which is read straight
# from the endpoint that produces it, see get_seasons() - this one does need a
# real (undetected, headless) browser.  Caching means that browser is spun up at
# most once per episode rather than for every lookup.
_page_cache: dict[str, str] = {}
_page_cache_lock = threading.Lock()


def _fetch_watch_html(url: str) -> str:
    """Return the rendered HTML of an episode watch page (cached per URL)."""
    with _page_cache_lock:
        cached = _page_cache.get(url)
    if cached is not None:
        return cached

    html = ""
    try:
        with SB(uc=True, headless2=True) as sb:
            sb.open(url)
            try:
                # The server list is what we need.  Its entries are filled in
                # by an AJAX call after the page loads, so wait for an actual
                # server rather than just the container.
                sb.wait_for_element("div.servers li[data-link-id]", timeout=15)
            except Exception:
                pass
            html = sb.get_page_source()
    except Exception as exc:
        print(f"[anikototv] watch page fetch failed for {url}: {exc}")

    with _page_cache_lock:
        _page_cache[url] = html
    return html


# ------------------------------------------------------------------
# URL converter  (episode page URL → provider redirect URL)
# ------------------------------------------------------------------

# Vidstream embed URLs keyed by server link id.  The worker asks for the same
# episode once per quality tier, so successful lookups are remembered instead of
# repeating the AJAX call each time.
_server_cache: dict[str, str] = {}


def get_provider_url(episode_url: str, language_code: str, provider: str) -> str | None:
    """Resolve an anikototv episode page URL to the URL a provider downloader takes.

    Fetches the watch page (through a real browser, cached per episode) and
    looks up the server for *provider* in the track named by *language_code*:

    - ``"Kiwi-Stream"`` → the track's download list for ``downloaders/KiwiStream.py``
    - ``"Vidstream"``   → the MegaPlay embed URL for ``downloaders/Vidstream.py``,
      with ``#subtitles=<code>`` appended for sub tracks

    Returns None when the requested track has no such server on this episode,
    when a non-English sub language isn't offered, or when the page can't be
    fetched.

    Parameters
    ----------
    episode_url:
        Full anikototv watch URL, e.g.
        ``https://anikototv.to/watch/sword-art-online-cn0ui/ep-1``.
    language_code:
        Site-internal language code from ``LANGUAGE_CODES`` - ``"dub"`` or
        ``"sub:<subtitle code>"``, e.g. ``"sub:spa"``.
    provider:
        Provider display name from ``SUPPORTED_PROVIDERS``.
    """
    try:
        html = _fetch_watch_html(episode_url)
        if not html:
            return None

        track, _, subtitle = language_code.partition(":")
        soup = BeautifulSoup(html, "lxml")
        if provider == "Kiwi-Stream":
            # animepahe's subs are burned into the video and always English.
            if subtitle not in ("", "eng"):
                return None
            return _kiwi_stream_url(episode_url, soup, track)
        if provider == "Vidstream":
            embed_url = _vidstream_url(episode_url, soup, track)
            if not embed_url or not subtitle:
                return embed_url
            # Other sub languages only count when the episode offers that
            # subtitle track; English sub downloads go ahead regardless.
            if subtitle != "eng" and not Vidstream.subtitle_track(embed_url, subtitle):
                return None
            return f"{embed_url}#subtitles={subtitle}"
        return None

    except Exception as exc:
        print(f"[anikototv] get_provider_url({episode_url!r}, {language_code!r}, {provider!r}): {exc}")
        return None


def _kiwi_stream_url(episode_url: str, soup: BeautifulSoup, language_code: str) -> str | None:
    """Return the Kiwi-Stream download list for a track, or None.

    The site's mapper.js builds its "DL" row from the mapper API, keyed by the
    episode's MAL id, slug and timestamp - attributes of the episode's link in
    the rendered episode list.  The returned URL is that API URL with the track
    as fragment (``…#sub`` / ``…#dub``); ``downloaders/KiwiStream.py`` picks the
    quality from it.  None when the track has no Kiwi-Stream downloads.
    """
    link = None
    for a in soup.select("ul.ep-range li > a[data-mal]"):
        if urljoin(episode_url, a.get("href", "")).rstrip("/") == episode_url.rstrip("/"):
            link = a
            break
    if link is None:
        link = soup.select_one("ul.ep-range li > a.active[data-mal]")
    if link is None:
        return None

    mal, slug, timestamp = (link.get(k) for k in ("data-mal", "data-slug", "data-timestamp"))
    if not (mal and slug and timestamp):
        return None

    downloads_url = f"{KiwiStream.MAPPER_API}{mal}/{slug}/{timestamp}#{language_code}"
    return downloads_url if KiwiStream.track_downloads(downloads_url) else None


def _vidstream_url(episode_url: str, soup: BeautifulSoup, language_code: str) -> str | None:
    """Return the MegaPlay embed URL behind a track's Vidstream server, or None.

    Servers are <li data-link-id="…">Vidstream-2</li> entries inside
    <div class="type" data-type="sub|dub">.  The label's suffix varies, so any
    entry whose name starts with "Vidstream" counts.  The link id is exchanged
    for the embed URL through the same ``ajax/server?get=`` call the site's
    player makes - a plain JSON request, no browser needed.
    """
    link_ids = [
        li["data-link-id"]
        for block in soup.select(f'div.type[data-type="{language_code}"]')
        for li in block.select("li[data-link-id]")
        if li.get_text(strip=True).lower().startswith("vidstream")
    ]
    if not link_ids:
        return None

    parts = urlsplit(episode_url)
    headers = {
        **common.HEADERS,
        "Referer": episode_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    for link_id in link_ids:
        with _page_cache_lock:
            cached = _server_cache.get(link_id)
        if cached:
            return cached

        try:
            data = common.http_get(
                f"{parts.scheme}://{parts.netloc}/ajax/server?get={link_id}",
                headers=headers,
            ).json()
        except Exception:
            continue

        result = data.get("result") if isinstance(data, dict) and data.get("status") == 200 else None
        embed_url = result.get("url") if isinstance(result, dict) else None
        if isinstance(embed_url, str) and embed_url.startswith("http"):
            with _page_cache_lock:
                _server_cache[link_id] = embed_url
            return embed_url

    return None


# ------------------------------------------------------------------
# Series-name extraction
# ------------------------------------------------------------------

def _series_name_from_url(url: str) -> str:
    """Fallback series name derived from an anikototv watch URL.

    anikototv slugs look like ``sword-art-online-cn0ui`` - the title followed by
    a short random hash.  Only used when the page's own title element is missing;
    drops a trailing short alphanumeric hash and title-cases the rest.
    """
    try:
        slug = url.split("/watch/", 1)[1].split("/", 1)[0]
    except IndexError:
        return "Unknown Series"

    head, sep, tail = slug.rpartition("-")
    if sep and head and 0 < len(tail) <= 6 and any(ch.isdigit() for ch in tail):
        slug = head
    slug = slug.replace("-", " ").strip()
    return slug.title() if slug else "Unknown Series"


# ------------------------------------------------------------------
# Background worker
# ------------------------------------------------------------------

class _SeasonFetcher(QtCore.QThread):
    """Runs get_seasons() in a background thread and emits the result."""

    # ([(season_label, [(ep_num, title, url), ...]), ...], series_name)
    data_ready = QtCore.Signal(list, str)
    error = QtCore.Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            seasons, series_name = asyncio.run(get_seasons(self._url))
            self.data_ready.emit(seasons, series_name)
        except Exception as exc:
            self.error.emit(str(exc))


# ------------------------------------------------------------------
# Content widget
# ------------------------------------------------------------------

class AniKotoTVContent(QtWidgets.QWidget):
    """Body widget for anikototv.to series pages.

    Call load(url) whenever the user navigates here; it fires a background
    fetch and populates the season and episode combos when data arrives.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # [(season_label, [(ep_num, title, episode_url), ...]), ...] in the
        # site's own season order.  A list rather than a dict because two
        # seasons of one series can carry the same label ("OVA" twice), and a
        # dict would quietly drop one of them.
        self._seasons_data: list[tuple[str, list[tuple[int, str, str]]]] = []
        self._fetcher: _SeasonFetcher | None = None
        # Watch/series URL most recently loaded + the series name scraped from
        # it - used as the top-level download folder in get_selected_urls().
        self._series_url: str = ""
        self._series_name: str = ""
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

        # Wider than aniworld's season boxes: the site labels its seasons
        # ("Season 4: Part 1", "The Movie") rather than numbering them, so the
        # text needs the room.
        self.season_start = QtWidgets.QComboBox()
        self.season_start.setFixedWidth(190)
        self.season_end = QtWidgets.QComboBox()
        self.season_end.setFixedWidth(190)

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
        # Remember the series URL and seed a provisional name from it so
        # get_selected_urls() always has something even before data arrives.
        self._series_url = url
        self._series_name = _series_name_from_url(url)

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

    def get_selected_urls(self) -> list[tuple]:
        """Return (url, series_name, season_label, ep_num, title) for the range.

        Inclusive of both endpoints, in the site's own season order.  Every
        tuple shares the series name, so all the seasons of one series land in
        a single download folder with a sub-folder each.
        """
        if not self._seasons_data:
            return []

        series_name = self._series_name or _series_name_from_url(self._series_url)
        start_url = self.episode_start.currentData()
        end_url = self.episode_end.currentData()

        results: list[tuple] = []
        collecting = False
        for label, episodes in self._seasons_data:
            for ep_num, title, url in episodes:
                if url == start_url:
                    collecting = True
                if collecting:
                    results.append(
                        (url, series_name, label, ep_num, title or f"Episode {ep_num}")
                    )
                if collecting and url == end_url:
                    return results

        return results  # fallback - should not normally be reached

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

    # ------------------------------------------------------------------
    # Data arrival
    # ------------------------------------------------------------------

    def _on_data_ready(self, seasons: list, series_name: str):
        self.status_label.clear()
        self._seasons_data = [(label, episodes) for label, episodes in seasons]
        if series_name:
            self._series_name = series_name

        if not self._seasons_data:
            self.status_label.setText(tr("No episodes found"))
            self._set_controls_enabled(False)
            return

        # The season is carried as its position in _seasons_data rather than by
        # its label, which is not unique within a series.
        for cb in (self.season_start, self.season_end):
            cb.blockSignals(True)
            for position, (label, _episodes) in enumerate(self._seasons_data):
                cb.addItem(label, userData=position)
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
        position = season_cb.currentData()
        episodes = (
            self._seasons_data[position][1]
            if isinstance(position, int) and 0 <= position < len(self._seasons_data)
            else []
        )
        episode_cb.blockSignals(True)
        episode_cb.clear()
        for ep_num, title, url in episodes:
            episode_cb.addItem(tr("Ep. {number} - {title}", number=ep_num, title=title), userData=url)
        episode_cb.blockSignals(False)

    def _on_error(self, msg: str):
        self.status_label.setText(tr("Error: {message}", message=msg))
        self._set_controls_enabled(False)


# ------------------------------------------------------------------
# Page entry point (consumed by menu.py auto-discovery)
# ------------------------------------------------------------------

def build_content() -> QtWidgets.QWidget:
    """Return the body widget shown below the shared title bar."""
    return AniKotoTVContent()


# ------------------------------------------------------------------
# Scraping
# ------------------------------------------------------------------
# A watch page renders its episode list from ``ajax/episode/list/<id>`` once it
# has loaded, which is why reading it used to mean driving a real browser.  That
# was affordable while a page showed a single season; now that one page covers
# every season of a series - and the catalogue has one with thirty-one - it
# would mean thirty-one browser launches.  The endpoint the site's own player
# calls is a plain JSON request, so it is asked directly and all the seasons are
# fetched at once.

# X-Requested-With is what marks the call as the page's own AJAX; without it the
# site answers with an error document instead of the episode list.
_AJAX_HEADERS = {
    **common.HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"https://{HOSTNAME}/",
}


async def _fetch_json(session, url: str) -> dict:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        payload = await response.json(content_type=None)
    return payload if isinstance(payload, dict) else {}


async def _series_details(session, series_url: str) -> tuple[int | None, str]:
    """The site's numeric id for *series_url*, and the series' display name.

    Both come from the watch page's own markup, which is served without needing
    a browser - it is only the episode list inside it that arrives later.
    Returns ``(None, "")`` when the page cannot be read, leaving the caller to
    carry on without that season rather than failing the whole fetch.
    """
    try:
        async with session.get(
            series_url, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            html = await response.text()
    except Exception as exc:
        print(f"[anikototv] series page fetch failed for {series_url}: {exc}")
        return None, ""

    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("#watch-main[data-id]")
    raw_id = (main.get("data-id") or "").strip() if main is not None else ""
    series_id = int(raw_id) if raw_id.isdigit() else None

    title_el = soup.select_one('[itemprop="name"]') or soup.select_one(".title.d-title")
    return series_id, title_el.get_text(strip=True) if title_el else ""


async def _season_episodes(
        session, series_url: str, series_id: int | None,
) -> list[tuple[int, str, str]]:
    """``[(ep_num, title, episode_url), ...]`` for one season, in episode order.

    The endpoint leaves every ``href`` as ``"#"`` - the site fills them in
    client-side - so each episode URL is rebuilt from its season's URL and its
    number.  That is the same ``…/ep-3`` form the watch page links to and the
    one get_provider_url() is handed when the download starts.
    """
    if series_id is None:
        return []

    try:
        payload = await _fetch_json(session, f"{anikototv_series.EPISODES_API}{series_id}")
    except Exception as exc:
        print(f"[anikototv] episode list failed for {series_url}: {exc}")
        return []

    soup = BeautifulSoup(payload.get("result") or "", "lxml")
    episodes: list[tuple[int, str, str]] = []
    for anchor in soup.select("ul.ep-range li a"):
        number = (anchor.get("data-num") or anchor.get("data-slug") or "").strip()
        if not number.isdigit():
            # Anything the site does not number is not addressable as
            # ``/ep-<n>`` and could not be downloaded, so it is left out.
            continue
        title_el = anchor.select_one(".d-title")
        title = title_el.get_text(strip=True) if title_el else ""
        # Untitled episodes are common on a season that is still airing; naming
        # them here keeps both the picker and the filename readable.
        episodes.append(
            (int(number), title or f"Episode {number}", f"{series_url}/ep-{number}")
        )

    episodes.sort()
    return episodes


async def get_seasons(url: str) -> tuple[list[tuple[str, list]], str]:
    """Fetch every season of the series *url* belongs to, with its episodes.

    Returns ``([(season_label, [(ep_num, title, episode_url), ...]), ...],
    series_name)`` in the site's own season order.

    Which entries make up the series comes from :mod:`anikototv_series`, which
    caches the site's own season strips alongside the title list.  A series the
    index has not heard of - because the catalogue was never fetched, or because
    it was added since - is asked about directly, so the pickers show the real
    seasons either way.

    Intended to be called from a background thread (e.g. _SeasonFetcher).
    """
    url = (url or "").rstrip("/")
    seasons = [
        [label, season_url, series_id]
        for label, season_url, series_id in anikototv_series.seasons_for_url(url)
    ]

    async with aiohttp.ClientSession(headers=_AJAX_HEADERS) as session:
        if not seasons:
            seasons = await _discover_seasons(session, url)

        # The season that names the series is read whatever the index already
        # knew: its page is where the series' own name comes from, and that name
        # is the one folder every season of the group is written into.
        primary = anikototv_series.primary_index(seasons) or 0
        primary_id, series_name = await _series_details(session, seasons[primary][1])
        if seasons[primary][2] is None:
            seasons[primary][2] = primary_id

        # Any remaining ids the index could not supply - a season it saw only as
        # someone else's sibling, or one a failed lookup left blank.
        missing = [
            i for i in range(len(seasons))
            if i != primary and seasons[i][2] is None
        ]
        if missing:
            found = await asyncio.gather(
                *(_series_details(session, seasons[i][1]) for i in missing)
            )
            for i, (series_id, _name) in zip(missing, found):
                seasons[i][2] = series_id

        episode_lists = await asyncio.gather(
            *(_season_episodes(session, season_url, series_id)
              for _label, season_url, series_id in seasons)
        )

    # A season whose episode list came back empty is dropped rather than shown
    # as a pickable range with nothing in it.
    return (
        [(label or "Season 1", episodes)
         for (label, _url, _sid), episodes in zip(seasons, episode_lists)
         if episodes],
        series_name,
    )


async def _discover_seasons(session, url: str) -> list[list]:
    """The season list for *url* asked of the site directly, for a cold index.

    Falls back to the single series that was opened, which is what the page
    showed before it could group seasons at all.
    """
    series_id, _name = await _series_details(session, url)
    strip = (
        await anikototv_series.fetch_season_strip(session, series_id)
        if series_id is not None
        else []
    )
    if len(strip) >= 2:
        # Only the series that was asked about is identified by this call; the
        # others' ids are looked up by get_seasons().
        return [
            [label, season_url, series_id if season_url == url else None]
            for label, season_url, _active in strip
        ]
    return [["Season 1", url, series_id]]
