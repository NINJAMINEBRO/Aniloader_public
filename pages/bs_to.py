from PySide6 import QtWidgets, QtCore
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import os
import tempfile
import threading
from zipfile import ZipFile

import site_mirrors
from app_paths import base_dir
from i18n import tr

# The hostname this page handles (without www.)
HOSTNAME = "bs.to"

# Providers this site actually supports.
# settings_manager.get_enabled_providers(settings_state, SUPPORTED_PROVIDERS)
# returns the intersection with the global list in user-configured priority order.
SUPPORTED_PROVIDERS = ["VOE", "Vidmoly", "Doodstream"]

# Languages this site actually supports, using the global display names as keys.
# settings_manager.get_enabled_languages(settings_state, SUPPORTED_LANGUAGES)
# returns the intersection with the global list in user-configured priority order.
SUPPORTED_LANGUAGES = ["German Dub", "English Dub", "Japanese · German Sub", "Japanese · English Sub"]

# Maps global language display names to bs.to's language path segment used on
# its per-season language pages (…/serie/<name>/<season>/<code>).
LANGUAGE_CODES: dict[str, str] = {
    "German Dub": "de",
    "English Dub": "en",
    "Japanese · German Sub": "des",
    "Japanese · English Sub": "jps",
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

class BsToContent(QtWidgets.QWidget):
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
    return BsToContent()


# ------------------------------------------------------------------
# Series-name extraction + URL converter (episode → hoster stream URL)
# ------------------------------------------------------------------
#
# bs.to is the heavy site: the playable hoster link only appears after a real
# browser clicks through the compliance gate and the player, so resolution runs
# through seleniumbase with the bundled ``recaptcha-solver.crx`` extension
# (assumed present in the working directory).  Results are cached per
# (episode, language, provider) so the worker's quality loop launches a browser
# at most once per combination rather than once per quality tier.
#
# NOTE: this path needs Chrome installed and cannot be exercised headlessly in
# CI; it follows the original program's flow and may need live tweaks.

_provider_url_cache: dict[tuple, str | None] = {}
_listing_cache: dict[str, str] = {}
_bs_lock = threading.Lock()


def _series_name_from_url(series_url: str) -> str:
    """Derive a tidy series name from a bs.to series/episode URL.

    bs.to URLs look like ``https://bs.to/serie/<slug>/<season>/<episode>``.
    """
    try:
        slug = series_url.split("/serie/", 1)[1].split("/", 1)[0]
    except IndexError:
        slug = ""
    slug = slug.strip()
    if not slug:
        return "Unknown Series"
    return slug.replace("-", " ").title()


def _parse_bs_url(episode_url: str) -> tuple[str, str, str]:
    """Split a bs.to episode URL into ``(name, season, episode)``."""
    try:
        parts = episode_url.split("/serie/", 1)[1].split("/")
    except IndexError:
        return "", "", ""
    name = parts[0] if parts else ""
    season = parts[1] if len(parts) > 1 else ""
    episode = parts[2] if len(parts) > 2 else ""
    episode = episode.split("-", 1)[0]  # strip any "-lang" suffix
    return name, season, episode


def _crx_extension_dir() -> str:
    """Unpack the bundled recaptcha-solver.crx and return the unpacked dir.

    The .crx ships next to the exe (base_dir); from source it's in the project
    folder. It's unpacked into a temp dir - always writable, and exactly what
    seleniumbase's ``extension_dir`` expects (an unpacked extension folder).
    """
    crx = base_dir() / "recaptcha-solver.crx"
    out = os.path.join(tempfile.gettempdir(), "aniloader_recaptcha_solver")
    try:
        os.makedirs(out, exist_ok=True)
        with ZipFile(crx, "r") as zip_ref:
            zip_ref.extractall(out)
    except Exception as exc:
        print(f"[bs.to] could not unpack recaptcha-solver.crx: {exc}")
    return out


def _find_episode_hoster_href(name: str, season: str, episode: str,
                              language_code: str, provider: str) -> str | None:
    """Find the episode's hoster link for *provider* on the season language page."""
    listing_url = f"https://{HOSTNAME}/serie/{name}/{season}/{language_code}"
    with _bs_lock:
        html = _listing_cache.get(listing_url)
    if html is None:
        try:
            # Through site_mirrors: burningseries.cx serves this listing when
            # bs.to does not.  The cache stays keyed on the canonical URL, so a
            # domain switch mid-session does not orphan what was already read.
            html = site_mirrors.read_text(listing_url)
        except Exception:
            html = ""
        with _bs_lock:
            _listing_cache[listing_url] = html

    soup = BeautifulSoup(html, "lxml")
    for icon in soup.find_all("i", class_="hoster"):
        anchor = icon.parent
        href = str(anchor.get("href", "")) if anchor else ""
        if f"{season}/{episode}-" in href and href.split("/")[-1] == provider:
            return site_mirrors.absolute(HOSTNAME, href)
    return None


def _resolve_with_browser(url: str, provider: str) -> str | None:
    """Open the hoster page in a real browser and read the playable stream URL."""
    from seleniumbase import SB  # imported lazily - heavy and browser-dependent

    content_link = None
    try:
        with SB(uc=True, headless2=True, extension_dir=_crx_extension_dir()) as sb:
            # The browser does its own fetching, so it cannot fall back the way
            # site_mirrors' HTTP path does - it is pointed at the domain the
            # requests so far have shown to be up.
            sb.open(site_mirrors.live_url(url))
            try:
                sb.click('.cc-compliance a')   # accept the compliance gate
            except Exception:
                pass
            sb.click('.hoster-player .play')

            if provider == "VOE":
                content_link = sb.wait_for_element_visible(
                    '.hoster-player a', timeout=120).get_attribute("href")
            elif provider == "Doodstream":
                sb.switch_to_tab(1, timeout=120)
                iframe = BeautifulSoup(sb.get_page_source(), "lxml").find("iframe")
                if iframe:
                    src = iframe.get("src", "")
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://dood.li" + src
                    content_link = src
            else:
                # Vidoza / Vidmoly / Streamtape etc. embed via an iframe.
                content_link = sb.wait_for_element_visible(
                    '.hoster-player iframe', timeout=120).get_attribute("src")
    except Exception as exc:
        if "Chrome not found" in str(exc):
            print("[bs.to] Chrome must be installed for bs.to downloads.")
        else:
            print(f"[bs.to] browser resolution failed for {url}: {exc}")
    return content_link


def get_provider_url(episode_url: str, language_code: str, provider: str) -> str | None:
    """Resolve a bs.to episode to a playable hoster URL for *provider*.

    Returns ``None`` when the language/provider isn't available.  The returned
    URL is handed straight to the matching provider downloader, which performs
    stream extraction and quality selection just like on the other sites.
    """
    key = (episode_url, language_code, provider)
    with _bs_lock:
        if key in _provider_url_cache:
            return _provider_url_cache[key]

    result = None
    try:
        name, season, episode = _parse_bs_url(episode_url)
        if name and season and episode:
            hoster_page = _find_episode_hoster_href(
                name, season, episode, language_code, provider
            )
            if hoster_page:
                result = _resolve_with_browser(hoster_page, provider)
    except Exception as exc:
        print(f"[bs.to] get_provider_url({episode_url!r}, {language_code!r}, {provider!r}): {exc}")
        result = None

    with _bs_lock:
        _provider_url_cache[key] = result
    return result


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
        page_elements = soup.select("div#seasons ul li a")

        season_items = [
            (element.text.strip().replace("Specials", "0"),
             site_mirrors.absolute(HOSTNAME, element.get("href")))
            for element in page_elements
        ]

        # 2. Fetch all season episode pages concurrently
        tasks = [_get_episodes(season_url, season, session) for season, season_url in season_items]
        results = await asyncio.gather(*tasks)

    return {
        # "Specials" is mapped to the sentinel season "0" above; turn only that
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
    episodes_dict = {}

    page_elements = soup.select(f"tr td a:has(strong)")

    for episode_num, element in enumerate(page_elements, start=1):
        href = element.get("href")
        episode_title = element.get("title")

        episodes_dict[f"Episode_{episode_num}"] = {
            site_mirrors.absolute(HOSTNAME, href): episode_title
        }

    return episodes_dict