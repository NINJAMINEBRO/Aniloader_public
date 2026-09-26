"""Kiwi-Stream (anikototv, animepahe) downloader.

anikototv offers Kiwi-Stream (animepahe) downloads through a "DL" row that its
mapper.js builds from the mapper API
(``https://mapper.nekostream.site/api/mal/<mal id>/<episode>/<timestamp>``).
The API lists one link per track and quality::

    {"Kiwi": {"sub": {"download": {"360p": "https://pahe.nekostream.site/xeNZA", …}},
              "dub": {"download": {…}}}}

``pages/anikototv_to.py`` hands this module that API URL with the track as a
fragment (``…#sub`` / ``…#dub``).  From there it walks the chain a human would:

    API JSON    →  the pahe link for the requested quality
    pahe link   →  its "Download" button forwards to a Cloudflare worker, which
                   redirects to the kwik page (resolved with plain HTTP)
    kwik page   →  submit the form  →  the browser downloads the finished MP4

animepahe.ch skips the first two steps: the download box on its episode pages
links the kwik page (``https://kwik.cx/f/<id>``) directly, labelled with its
quality.  ``pages/animepahe_ch.py`` hands over such a kwik URL, with the
episode's kwik links listed by quality in the fragment
(``…#720p=<kwik url>``), and the flow starts at the kwik page.

Unlike the HLS hosters (VOE, Vidmoly, …) there is no stream to mux: kwik serves
a complete MP4, so the browser downloads the file directly and we simply move
it into place.  ffmpeg is never involved here.

The kwik step runs in an undetected headless browser (SeleniumBase ``uc`` mode)
because kwik sits behind a Cloudflare challenge.  Each call downloads into its
own throw-away directory - set per browser instance through DevTools once the
page is open (see :func:`_route_downloads`) - so any number of episodes can
download at once without their files colliding.  When that isn't possible the
code falls back to SeleniumBase's shared downloads folder and serialises those
(rare) downloads so the finished file is still identified unambiguously.

Quality handling mirrors every other provider: :func:`download` attempts the
exact tier it is asked for and returns ``False`` when the track has no link for
it, so ``EpisodeDownloadWorker`` falls back to the next-lower tier.
"""

import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import parse_qs, urlsplit

from seleniumbase import SB

from downloaders import common


MAPPER_API = "https://mapper.nekostream.site/api/mal/"

# Source keys the mapper API may use for Kiwi-Stream; mapper.js treats them alike.
_SOURCE_NAMES = ("kiwi", "kiwi-stream", "animepahe")

# Where a pahe link's "Download" button sends the browser (``<worker>/<id>``).
# Read from the pahe page's script when possible; this is the fallback.
_DEFAULT_WORKER = "https://proud-dew-d754.download992.workers.dev/"
_WORKER_PATTERN = re.compile(r'["\'](https://[^"\']+/)["\']\s*\+\s*id\b')

# Filename suffixes Chrome uses while a download is still in flight.
_PARTIAL_SUFFIXES = (".crdownload", ".tmp", ".part")

# kwik only renders its download form once the Cloudflare challenge has passed,
# which can take a while.
_FORM_TIMEOUT = 45.0
# After the form is submitted the download must actually begin within this many
# seconds (kwik occasionally serves an error page instead of the file).  Once
# bytes start arriving this no longer applies.
_START_TIMEOUT = 90.0
# If an in-progress file's size stops growing for this long, treat it as stalled
# and fail so the worker can fall back to another tier/provider.
_STALL_TIMEOUT = 180.0

# Only used for the fallback path (shared SeleniumBase downloads folder, when
# the per-instance DevTools route fails): serialises those downloads so the new
# completed file can be attributed unambiguously.  The normal temp-dir path is
# already exclusive and never touches this lock.
_shared_lock = threading.Lock()

# Per-process caches so the worker's quality loop doesn't refetch the same API
# response / re-resolve the same kwik redirect once per tier.
_mapper_cache: dict[str, dict] = {}
_kwik_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


# ----------------------------------------------------------------------
# Public entry points
# ----------------------------------------------------------------------

def download(url: str, download_path: str, file_name: str, quality: str | None = None) -> bool:
    """Download one episode from its download-list *url*.

    *url* is either a mapper API URL with the track as fragment (``…#sub``,
    anikototv) or a kwik page URL (animepahe) - see :func:`track_downloads`.
    Returns True on success and False on any failure - including when there is
    no link for *quality*, which lets the worker retry at a lower tier.
    """
    try:
        return _download(url, download_path, file_name, quality)
    except Exception as exc:  # never let a provider crash the worker
        print(f"[KiwiStream] error for {url}: {exc}")
        return False


def track_downloads(downloads_url: str) -> dict[str, str]:
    """Return ``{label: link}`` for the episode named in *downloads_url*.

    Labels are normally the quality (``"1080p"``).  *downloads_url* is one of:

    - a mapper API URL with the track as fragment (``…#sub``); the links are
      the track's pahe pages, as the API lists them
    - a kwik page URL, which carries its own links: the fragment lists the
      episode's kwik pages by quality (``…#720p=<kwik url>``), and without one
      the URL itself is the only link, of unknown quality

    Empty when there are no Kiwi-Stream downloads or the API can't be reached.
    """
    api_url, _, track = downloads_url.partition("#")
    if _is_kwik(api_url):
        return _listed_kwik_links(api_url, track)

    links: dict[str, str] = {}
    for source, tracks in _mapper_data(api_url).items():
        if source.lower() not in _SOURCE_NAMES or not isinstance(tracks, dict):
            continue
        entry = tracks.get(track)
        found = entry.get("download") if isinstance(entry, dict) else None
        if not isinstance(found, dict):
            continue
        for label, link in found.items():
            if isinstance(link, str) and link.startswith("http"):
                links.setdefault(str(label), link)
    return links


# ----------------------------------------------------------------------
# Core flow
# ----------------------------------------------------------------------

def _download(downloads_url: str, download_path: str, file_name: str, quality: str | None) -> bool:
    if common.is_cancelled():
        return False

    # Resolve everything that doesn't need a browser first, so an unavailable
    # tier costs a cached lookup rather than a browser launch.
    pahe_url = _pick_download(track_downloads(downloads_url), quality)
    if not pahe_url:
        return False
    kwik_url = _kwik_url(pahe_url)
    if not kwik_url:
        return False

    tmp_dir = tempfile.mkdtemp(prefix="kiwi_dl_")
    holding_shared_lock = False
    try:
        with SB(uc=True, headless2=True) as sb:
            sb.open(kwik_url)

            # Route this browser's downloads into our private temp dir so
            # concurrent episodes never see each other's files.
            target_dir = tmp_dir
            preexisting: set[str] = set()
            if not _route_downloads(sb, tmp_dir):
                # Not possible - fall back to SeleniumBase's shared downloads
                # folder.  Serialise so the new finished file is ours, and
                # snapshot what's already there to ignore it.
                _shared_lock.acquire()
                holding_shared_lock = True
                target_dir = sb.get_downloads_folder()
                preexisting = (
                    set(os.listdir(target_dir)) if os.path.isdir(target_dir) else set()
                )

            # 1) kwik page → submit the form, which starts the browser download.
            if not _submit_form(sb):
                return False

            # 2) wait for the file to finish downloading.
            finished = _wait_for_download(target_dir, preexisting)
            if not finished:
                return False

            # 3) move it into place under the worker-chosen name.
            return _finalise(target_dir, finished, download_path, file_name)
    finally:
        if holding_shared_lock:
            _shared_lock.release()
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ----------------------------------------------------------------------
# Link resolution
# ----------------------------------------------------------------------

def _mapper_data(api_url: str) -> dict:
    """Fetch the mapper API response for an episode (cached on success)."""
    with _cache_lock:
        if api_url in _mapper_cache:
            return _mapper_cache[api_url]

    data: dict = {}
    try:
        resp = common.http_get(
            api_url, headers={**common.HEADERS, "Referer": "https://anikototv.to/"}
        )
        if resp.status_code == 200:
            parsed = resp.json()
            if isinstance(parsed, dict):
                data = parsed
    except Exception:
        data = {}

    if data:
        with _cache_lock:
            _mapper_cache[api_url] = data
    return data


def _is_kwik(url: str) -> bool:
    """True when *url* is a kwik page rather than a link that leads to one."""
    return "kwik." in urlsplit(url).netloc


def _listed_kwik_links(kwik_url: str, fragment: str) -> dict[str, str]:
    """``{label: kwik URL}`` from a kwik URL and its ``label=link`` fragment.

    A fragment that lists nothing usable leaves *kwik_url* as the one link,
    unlabelled, which :func:`_pick_download` takes whatever tier is asked for.
    """
    links = {
        label: urls[0]
        for label, urls in parse_qs(fragment).items()
        if urls and urls[0].startswith("http") and _is_kwik(urls[0])
    }
    return links or {"": kwik_url}


def _label_height(label: str) -> int | None:
    """Pixel height named by a download label (``"1080p"`` → 1080), or None."""
    low = label.lower()
    if "4k" in low:
        return 2160
    m = re.search(r"(\d{3,4})\s*p?\b", low)
    return int(m.group(1)) if m else None


def _pick_download(links: dict[str, str], quality: str | None) -> str | None:
    """Pick the pahe link for *quality* (or the best one when None)."""
    tiers: dict[str, str] = {}
    unlabelled: list[str] = []
    for label, link in links.items():
        height = _label_height(label)
        if height:
            tiers.setdefault(common.height_to_tier(height), link)
        else:
            unlabelled.append(link)

    if quality is None:
        if tiers:
            order = [tier for tier, _min_h in common.QUALITY_TIERS]
            return tiers[min(tiers, key=order.index)]
        return unlabelled[0] if unlabelled else None
    if quality in tiers:
        return tiers[quality]
    # A lone link without a quality label: take it rather than never downloading.
    if not tiers and unlabelled:
        return unlabelled[0]
    return None


def _kwik_url(pahe_url: str) -> str | None:
    """Follow a pahe link's "Download" redirect to its kwik page URL (cached).

    The pahe page's button sends the browser to ``<worker>/<id>``, which answers
    with a redirect to kwik.  kwik itself refuses plain HTTP (Cloudflare), but
    the redirect target is all that's needed here.
    """
    with _cache_lock:
        if pahe_url in _kwik_cache:
            return _kwik_cache[pahe_url]

    kwik = None
    try:
        if _is_kwik(pahe_url):
            kwik = pahe_url
        else:
            worker = _DEFAULT_WORKER
            page = common.http_get(pahe_url)
            if page.status_code == 200:
                m = _WORKER_PATTERN.search(page.text)
                if m:
                    worker = m.group(1)
            link_id = urlsplit(pahe_url).path.rstrip("/").rsplit("/", 1)[-1]
            worker_url = worker + link_id
            resp = common.http_get(
                worker_url, headers={**common.HEADERS, "Referer": pahe_url}
            )
            if resp.history and urlsplit(resp.url).netloc != urlsplit(worker_url).netloc:
                kwik = resp.url
    except Exception:
        kwik = None

    if kwik:
        with _cache_lock:
            _kwik_cache[pahe_url] = kwik
    return kwik


def _route_downloads(sb, folder: str) -> bool:
    """Send this browser's downloads to *folder*; False if that isn't possible.

    In UC mode ``sb.open()`` switches SeleniumBase into CDP Mode, which
    disconnects WebDriver.  A download path set through WebDriver's DevTools
    session before that is silently dropped and the file lands in
    SeleniumBase's shared downloads folder instead, so the path is set on the
    CDP-Mode tab after the page is open.  WebDriver's DevTools is only used
    when CDP Mode isn't active (WebDriver is then still connected).
    """
    cdp = getattr(sb, "cdp", None)
    if cdp is not None and hasattr(cdp, "page") and hasattr(cdp, "loop"):
        try:
            cdp.loop.run_until_complete(cdp.page.set_download_path(Path(folder)))
            return True
        except Exception:
            return False
    try:
        sb.execute_cdp_cmd(
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": folder},
        )
        return True
    except Exception:
        return False


def _submit_form(sb) -> bool:
    """Submit the kwik download form, which triggers the browser download.

    Waits for the form to appear (kwik renders it after its Cloudflare check),
    then submits it.  Returns False if no form ever appears.
    """
    find_form = (
        "return document.querySelector('form[action*=\"/d/\"]')"
        " || document.querySelector('form')"
    )
    deadline = monotonic() + _FORM_TIMEOUT
    while monotonic() < deadline:
        if common.is_cancelled():
            return False
        try:
            has_form = sb.execute_script(f"return !!(function(){{ {find_form} }})()")
        except Exception:
            has_form = False
        if has_form:
            try:
                sb.execute_script(f"(function(){{ {find_form} }})().submit()")
                return True
            except Exception:
                return False
        sb.sleep(2)
    return False


# ----------------------------------------------------------------------
# Download wait + finalise
# ----------------------------------------------------------------------

def _file_size(folder: str, name: str) -> int:
    try:
        return os.path.getsize(os.path.join(folder, name))
    except OSError:
        return 0


def _file_mtime(folder: str, name: str) -> float:
    try:
        return os.path.getmtime(os.path.join(folder, name))
    except OSError:
        return 0.0


def _wait_for_download(folder: str, preexisting: set[str]) -> str | None:
    """Block until a new download in *folder* finishes; return its filename.

    *preexisting* are filenames already present before the download started and
    are ignored (empty for the private temp-dir path).  Returns None on
    cancellation, if the download never starts, or if it stalls.
    """
    started = False
    last_size = -1
    last_change = monotonic()
    start_deadline = monotonic() + _START_TIMEOUT

    while True:
        if common.is_cancelled():
            return None

        try:
            entries = set(os.listdir(folder))
        except OSError:
            entries = set()
        new = entries - preexisting
        partials = [f for f in new if f.endswith(_PARTIAL_SUFFIXES)]
        completed = [f for f in new
                     if not f.endswith(_PARTIAL_SUFFIXES) and _file_size(folder, f) > 0]

        # A finished, non-empty file with nothing still downloading → done.
        if completed and not partials:
            return max(completed, key=lambda f: _file_mtime(folder, f))

        if partials:
            started = True
            size = max(_file_size(folder, f) for f in partials)
            if size != last_size:
                last_size = size
                last_change = monotonic()
            elif monotonic() - last_change > _STALL_TIMEOUT:
                return None
        elif not started and monotonic() > start_deadline:
            return None

        sleep(1)


def _finalise(folder: str, filename: str, download_path: str, target_name: str) -> bool:
    """Move the finished *filename* out of *folder* to ``download_path/target_name``."""
    src = os.path.join(folder, filename)
    try:
        os.makedirs(download_path, exist_ok=True)
    except OSError:
        pass
    dst = os.path.join(download_path, target_name)
    try:
        shutil.move(src, dst)
    except Exception as exc:
        print(f"[KiwiStream] could not move {src!r} -> {dst!r}: {exc}")
        return False
    return True
