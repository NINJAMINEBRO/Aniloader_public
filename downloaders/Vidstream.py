"""Vidstream (anikototv, animepahe) downloader.

anikototv's "Vidstream" server plays through a MegaPlay embed
(``https://megaplay.buzz/stream/s-2/<id>/<sub|dub>``), and so do most of
animepahe.ch's episode pages.  ``pages/anikototv_to.py`` and
``pages/animepahe_ch.py`` resolve an episode page to that embed URL for the
requested language and hand it here.  MegaPlay only serves the embed to a
request that looks like it came from a site embedding it, so animepahe's URLs
name their site in the fragment (``#referer=https://animepahe.ch/``); anikototv's
carry none and get anikototv's.

From the embed this module walks the same chain the player does:

    embed page       →  ``data-id`` of the ``#megaplay-player`` element
    getSources?id=…  →  JSON with the subtitle ``tracks`` and an AES-CBC
                        encrypted ``enc`` field
    decrypt ``enc``  →  ``{"file": ".../master.m3u8"}``

The master playlist itself is gated behind a signed ``?token=`` that the player
generates in obfuscated code, but the rendition playlists next to it only need a
MegaPlay ``Referer``.  So the master is tried first (in case it is ever served
openly) and, when it is refused, the renditions are enumerated directly -
``index-f1.m3u8``, ``index-f2.m3u8``, … on multi-quality uploads and
``index-f1-v1-a1.m3u8`` on single-quality ones - and bucketed into quality tiers
by probing the height of each one's first segment with ffprobe.

The segment CDNs answer bursts with ``429 Too Many Requests``.  ffmpeg's HLS
demuxer skips a segment it can't fetch and still exits successfully, leaving a
silently truncated file, so the segments are downloaded here with a patient
retry instead and only the finished transport stream is remuxed by ffmpeg.

Sub videos carry no burned-in subtitles - the player overlays the WebVTT
``tracks`` instead.  Each sub language entry ("Japanese · Spanish Sub", …) makes
the page append ``#subtitles=<code>`` to the embed URL.  That subtitle track is
embedded into the file as the default subtitle stream, and also saved as an
``.srt`` with the episode's name next to it: many players (Windows' Media Player
among them) ignore subtitle tracks inside an MP4 but load a same-named .srt.
Which languages an episode has depends on where MegaPlay sourced it - anything
from English alone to a dozen Crunchyroll tracks - so a page asks
:func:`subtitle_track` before offering a language.
"""

import base64
import codecs
import json
import os
import re
import threading
from time import monotonic, sleep
from urllib.parse import parse_qs, urljoin, urlsplit

from Crypto.Cipher import AES

from downloaders import common

# Key/IV MegaPlay's player uses for the getSources ``enc`` payload.  The player
# zero-pads the 16-character key to 32 bytes (AES-256), so do the same.
_AES_KEY = b"i?LMTAx0Q6,:}50U".ljust(32, b"\0")
_AES_IV = b"W0;27ToaUpl_P%'c"

# The embed page is only served normally when it looks like it was opened from a
# site embedding it.  anikototv's is the default; a URL whose fragment names
# another site (``referer=…``) uses that one instead.
_SITE_REFERER = "https://anikototv.to/"

_PLAYER_ID_PATTERN = re.compile(r'id="megaplay-player"[^>]*?\bdata-id="(?P<id>\d+)"')

# Renditions sit next to the master, highest quality first.
_MAX_RENDITIONS = 6
_RENDITION_NAMES = ("index-f{n}.m3u8", "index-f{n}-v1-a1.m3u8")

# Segment download retries: rate-limited (429) and transient server errors are
# retried with a doubling wait, honouring Retry-After when the CDN sends one.
_SEGMENT_ATTEMPTS = 8
_SEGMENT_BACKOFF = 2.0
_SEGMENT_BACKOFF_MAX = 60.0
_SEGMENT_TIMEOUT = 30

# Subtitle codes used in the LANGUAGE_CODES of pages/anikototv_to.py and
# pages/animepahe_ch.py.  Each maps to the ISO 639-2 code and track name written
# into the file, and a test for MegaPlay's track labels.  Those come in two
# styles depending on the source: "English", "Indonesian", "Thai",
# "Portuguese (- Portuguese(Brazil))", "Spanish (- Spanish(Latin America))", or
# Crunchyroll's "French (- CR)", "Portuguese (- Brazilian CR)",
# "Spanish (- Latin America CR)" - so every test keys on how the label starts.
SUBTITLE_LANGUAGES = {
    "eng": ("eng", "English", lambda label: label.startswith("english")),
    "por-br": (
        "por", "Portuguese (Brazil)",
        lambda label: label.startswith("portuguese")
        and "portugal" not in label and "europe" not in label,
    ),
    "spa": ("spa", "Spanish", lambda label: label.startswith("spanish") and "latin" not in label),
    "spa-la": ("spa", "Spanish (Latin America)",
               lambda label: label.startswith("spanish") and "latin" in label),
    "deu": ("deu", "German", lambda label: label.startswith("german")),
    "fra": ("fra", "French", lambda label: label.startswith("french")),
    "ind": ("ind", "Indonesian", lambda label: label.startswith("indonesian")),
    "tha": ("tha", "Thai", lambda label: label.startswith("thai")),
    "vie": ("vie", "Vietnamese", lambda label: label.startswith("vietnamese")),
}

# Per-process caches so the worker's quality loop doesn't re-resolve the same
# embed / re-probe the same renditions once per tier.
_sources_cache: dict[str, tuple[str, list[dict]]] = {}
_variants_cache: dict[str, dict[str, str]] = {}
_cache_lock = threading.Lock()


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def _headers(referer: str) -> dict:
    return {**common.HEADERS, "Referer": referer}


def _split_url(url: str) -> tuple[str, str | None, str]:
    """Split the page's ``embed#subtitles=<code>&referer=<site>`` URL.

    Returns ``(embed_url, subtitle_code, site_referer)``; both fragment keys
    are optional.
    """
    embed_url, _, fragment = url.partition("#")
    params = parse_qs(fragment)
    codes = params.get("subtitles")
    referers = params.get("referer")
    return (embed_url, codes[0] if codes else None,
            referers[0] if referers else _SITE_REFERER)


# ----------------------------------------------------------------------
# Embed → master playlist + subtitle tracks
# ----------------------------------------------------------------------

def _decrypt_enc(enc: str) -> dict | None:
    """Decrypt a getSources ``enc`` payload into its JSON object, or None."""
    try:
        data = base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4))
        plain = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(data)
        pad = plain[-1]
        if 1 <= pad <= AES.block_size:
            plain = plain[:-pad]
        return json.loads(plain.decode("utf-8"))
    except Exception:
        return None


def _source_file(payload: dict) -> str | None:
    """Pull the playlist URL out of a getSources response.

    Handles both a plain ``sources`` field and the encrypted ``enc`` field the
    endpoint currently returns.
    """
    sources = payload.get("sources")
    file = None
    if isinstance(sources, dict):
        file = sources.get("file")
    elif isinstance(sources, list) and sources and isinstance(sources[0], dict):
        file = sources[0].get("file")

    if not file and isinstance(payload.get("enc"), str):
        decrypted = _decrypt_enc(payload["enc"])
        if isinstance(decrypted, dict):
            file = decrypted.get("file")

    if isinstance(file, str) and file.startswith("http"):
        return file
    return None


def _get_sources(embed_url: str, site_referer: str = _SITE_REFERER) -> tuple[str | None, list[dict]]:
    """Return ``(master_playlist_url, subtitle_tracks)`` for *embed_url* (cached).

    *site_referer* is the site the player is embedded on, which MegaPlay wants
    to see before it serves the embed page.
    """
    with _cache_lock:
        if embed_url in _sources_cache:
            return _sources_cache[embed_url]

    master, tracks = None, []
    try:
        html = common.http_get(embed_url, headers=_headers(site_referer)).text
        m = _PLAYER_ID_PATTERN.search(html)
        if m:
            payload = common.http_get(
                f"{_origin(embed_url)}stream/getSources?id={m.group('id')}",
                headers={**_headers(embed_url), "X-Requested-With": "XMLHttpRequest"},
            ).json()
            master = _source_file(payload)
            tracks = [
                t for t in payload.get("tracks") or []
                if isinstance(t, dict) and t.get("kind") in ("captions", "subtitles")
                and isinstance(t.get("file"), str) and t["file"].startswith("http")
            ]
    except Exception:
        master, tracks = None, []

    # Only cache a successful resolution so a transient failure isn't
    # remembered for the rest of the session.
    if master:
        with _cache_lock:
            _sources_cache[embed_url] = (master, tracks)
    return master, tracks


def subtitle_track(embed_url: str, code: str) -> str | None:
    """Return the WebVTT URL of the *code* subtitle track on *embed_url*, or None.

    *embed_url* may carry the ``#referer=<site>`` fragment the pages build.
    When several tracks fit one language the shortest label (the plain variant,
    e.g. "English" over "English (- SDH)") wins.
    """
    language = SUBTITLE_LANGUAGES.get(code)
    if language is None:
        return None
    _iso, _name, matches = language
    bare_url, _code, site_referer = _split_url(embed_url)
    _master, tracks = _get_sources(bare_url, site_referer)
    candidates = [t for t in tracks if matches(str(t.get("label", "")).strip().lower())]
    if not candidates:
        return None
    return min(candidates, key=lambda t: len(str(t.get("label", ""))))["file"]


# ----------------------------------------------------------------------
# Master → quality tiers
# ----------------------------------------------------------------------

def _playlist_segments(playlist_url: str, referer: str) -> list[str] | None:
    """Return the absolute segment URLs of a media playlist.

    Returns None when the playlist isn't served (or isn't a media playlist), and
    an empty list when it uses encryption this module can't handle.
    """
    try:
        resp = common.http_get(playlist_url, headers=_headers(referer), retries=1)
    except Exception:
        return None
    if resp.status_code != 200 or "#EXTINF" not in resp.text:
        return None
    if re.search(r"#EXT-X-KEY:.*METHOD=(?!NONE)", resp.text):
        return []
    return [
        urljoin(playlist_url, ln.strip())
        for ln in resp.text.splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def _probe_rendition(playlist_url: str, referer: str) -> tuple[bool, str | None]:
    """Check a media playlist and bucket it into a quality tier.

    Returns ``(exists, tier)``: *exists* is False when the playlist isn't served
    at all, and *tier* is None when it exists but its height couldn't be
    determined (or it can't be downloaded).
    """
    segments = _playlist_segments(playlist_url, referer)
    if segments is None:
        return False, None
    if not segments:
        return True, None
    height = common.ffprobe_height(segments[0], referer=referer)
    return True, common.height_to_tier(height) if height else None


def _get_variants(master_url: str, referer: str) -> dict[str, str]:
    """Return ``{tier: media_playlist_url}`` for *master_url* (cached)."""
    with _cache_lock:
        if master_url in _variants_cache:
            return _variants_cache[master_url]

    variants: dict[str, str] = {}
    master_is_media = False
    try:
        resp = common.http_get(master_url, headers=_headers(referer))
        if resp.status_code == 200:
            variants = common.parse_hls_master(resp.text, master_url)
            master_is_media = not variants and "#EXTINF" in resp.text
    except Exception:
        variants = {}

    if not variants:
        if master_is_media:
            slots = [[master_url]]
        else:
            # Master refused (token-gated): walk the sibling renditions.
            base = master_url.rsplit("/", 1)[0]
            slots = [
                [f"{base}/{name.format(n=n)}" for name in _RENDITION_NAMES]
                for n in range(1, _MAX_RENDITIONS + 1)
            ]
        for candidates in slots:
            found = False
            for candidate in candidates:
                if common.is_cancelled():
                    break
                found, tier = _probe_rendition(candidate, referer)
                if found:
                    if tier:
                        # Highest quality comes first; keep the first per tier.
                        variants.setdefault(tier, candidate)
                    break
            if not found:
                break

    if variants:
        with _cache_lock:
            _variants_cache[master_url] = variants
    return variants


def _resolve_target_url(url: str, quality: str | None, referer: str,
                        site_referer: str = _SITE_REFERER) -> str | None:
    master, _tracks = _get_sources(url, site_referer)
    if not master:
        return None
    variants = _get_variants(master, referer)
    if not variants:
        return None
    if quality:
        return variants.get(quality)  # None ⇒ tier unavailable, try next
    order = [tier for tier, _min_h in common.QUALITY_TIERS]
    return variants[min(variants, key=order.index)]


# ----------------------------------------------------------------------
# Subtitles
# ----------------------------------------------------------------------

def _download_subtitle(embed_url: str, code: str, download_path: str,
                       file_name: str, referer: str) -> str | None:
    """Save the *code* subtitle track next to the download; return its path.

    *embed_url* is the URL the page handed over, fragment and all, so the
    track lookup is made as the right site.  None when the episode has no such
    track or it fails to download - the episode is then saved without subtitles
    rather than failing.
    """
    vtt_url = subtitle_track(embed_url, code)
    if not vtt_url:
        return None
    try:
        resp = common.http_get(vtt_url, headers=_headers(referer))
    except Exception:
        resp = None
    if resp is None or resp.status_code != 200 or not resp.content.strip():
        print(f"[Vidstream] could not download {code} subtitles for {file_name}")
        return None
    path = os.path.join(download_path, f"{file_name}.{code}.vtt")
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


def _subtitle_output_args(code: str) -> list[str]:
    """ffmpeg output options that embed input 1 as the default mov_text track."""
    iso, name, _matches = SUBTITLE_LANGUAGES[code]
    return [
        "-map", "0:v", "-map", "0:a?", "-map", "1:0",
        "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={iso}",
        # MP4 players read the track name from the handler name.  (A "title"
        # tag would be written as a malformed udta box some players reject.)
        "-metadata:s:s:0", f"handler_name={name}",
        "-disposition:s:0", "default",
    ]


def _write_sidecar_srt(subtitle_path: str, download_path: str, file_name: str) -> bool:
    """Save the subtitles as ``<episode>.srt`` next to the video.

    Many players - Windows' Media Player among them - ignore subtitle tracks
    embedded in an MP4 but load an .srt with the same name.  It is written as
    UTF-8 with a BOM so Windows players don't garble accented characters.
    """
    srt_name = os.path.splitext(file_name)[0] + ".srt"
    srt_path = os.path.join(download_path, srt_name)
    # A leftover .srt would make ffmpeg refuse to write the new one.
    try:
        os.remove(srt_path)
    except OSError:
        pass

    if not common.run_ffmpeg(subtitle_path, download_path, srt_name,
                             attempts=1, output_args=["-c:s", "srt"]):
        print(f"[Vidstream] could not save subtitles as {srt_name}")
        return False
    try:
        with open(srt_path, "rb") as f:
            data = f.read()
        if not data.startswith(codecs.BOM_UTF8):
            with open(srt_path, "wb") as f:
                f.write(codecs.BOM_UTF8 + data)
    except OSError:
        return False
    return True


# ----------------------------------------------------------------------
# Segment download
# ----------------------------------------------------------------------

def _wait(seconds: float) -> bool:
    """Sleep up to *seconds*, waking early on cancellation.  False if cancelled."""
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        if common.is_cancelled():
            return False
        sleep(min(0.5, max(0.0, deadline - monotonic())))
    return not common.is_cancelled()


def _fetch_segment(url: str, referer: str) -> bytes | None:
    """Download one segment, riding out rate limiting.  None on failure."""
    delay = _SEGMENT_BACKOFF
    for _attempt in range(_SEGMENT_ATTEMPTS):
        if common.is_cancelled():
            return None
        try:
            resp = common.http_get(
                url, headers=_headers(referer), timeout=_SEGMENT_TIMEOUT, retries=0
            )
        except Exception:
            resp = None

        if resp is not None:
            if resp.status_code == 200 and resp.content:
                return resp.content
            if resp.status_code not in (429, 500, 502, 503, 504):
                return None  # 403/404 etc. won't fix themselves

        wait = delay
        retry_after = resp.headers.get("Retry-After", "") if resp is not None else ""
        if retry_after.strip().isdigit():
            wait = max(wait, float(retry_after))
        if not _wait(min(wait, _SEGMENT_BACKOFF_MAX)):
            return None
        delay *= 2
    return None


def download(url, download_path, file_name, quality=None):
    """Download one episode from its MegaPlay embed *url*.

    *url* may carry ``#subtitles=<code>``, naming the subtitle track to embed
    (and save as a same-named .srt), and ``referer=<site>``, naming the site the
    player was embedded on.  Returns True on success and False on any failure -
    including when *quality* isn't offered, which lets the worker retry at a
    lower tier.
    """
    try:
        embed_url, subtitle_code, site_referer = _split_url(url)
        referer = _origin(embed_url)
        target = _resolve_target_url(embed_url, quality, referer, site_referer)
        if not target:
            return False
        segments = _playlist_segments(target, referer)
        if not segments:
            return False

        os.makedirs(download_path, exist_ok=True)
        part_path = os.path.join(download_path, file_name + ".part.ts")
        subtitle_path = None
        try:
            # MPEG-TS segments concatenate into one valid transport stream.
            with open(part_path, "wb") as part:
                for segment in segments:
                    data = _fetch_segment(segment, referer)
                    if data is None:
                        return False
                    part.write(data)

            if subtitle_code in SUBTITLE_LANGUAGES:
                subtitle_path = _download_subtitle(
                    url, subtitle_code, download_path, file_name, referer
                )

            embedded = bool(subtitle_path) and common.run_ffmpeg(
                part_path, download_path, file_name,
                extra_inputs=[subtitle_path],
                output_args=_subtitle_output_args(subtitle_code),
            )
            if subtitle_path and not embedded:
                if common.is_cancelled():
                    return False
                # Don't lose the episode over a subtitle file ffmpeg rejects.
                print(f"[Vidstream] embedding subtitles failed for {file_name}; "
                      f"saving without them")
            if not embedded and not common.run_ffmpeg(part_path, download_path, file_name):
                return False

            if subtitle_path:
                _write_sidecar_srt(subtitle_path, download_path, file_name)
            return True
        finally:
            for path in (part_path, subtitle_path):
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
    except Exception as exc:  # never let a provider crash the worker
        print(f"[Vidstream] error for {url}: {exc}")
        return False
