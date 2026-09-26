from re import compile, search, DOTALL, match
from base64 import b64decode
from bs4 import BeautifulSoup
import json
import threading

from downloaders import common

PATTERNS = [compile(r"'hls': '(?P<url>.+)'"),
            compile(r'prompt\("Node",\s*"(?P<url>[^"]+)"'),
            compile(r"window\.location\.href = '(?P<url>[^']+)'")]

# Per-process caches so the worker's quality loop doesn't re-resolve the same
# VOE page / master playlist once per tier.  Keyed by the provider (redirect)
# URL and the master-playlist URL respectively.  Guarded by a lock because
# downloads run in concurrent QThreads.
_hls_master_cache: dict[str, str | None] = {}
_variants_cache: dict[str, dict[str, str]] = {}
_cache_lock = threading.Lock()


# ------------------------------------------------------------------
# Diagnostics (temporary)
# ------------------------------------------------------------------
# Set _DEBUG = True to enable.  These prints trace exactly what VOE returns
# at each step so a block / rate-limit page can be told apart from a genuine
# parse failure or a legitimately missing quality tier.  Lines are tagged with
# the worker thread id so concurrent episode downloads can be grouped.
_DEBUG = False

# Substrings (lower-cased) that suggest a bot-check / block / rate-limit page
# rather than the real VOE embed.
_BLOCK_MARKERS = (
    "just a moment", "verifying you are human", "attention required",
    "cf-browser-verification", "challenge-platform", "_cf_chl", "cf_chl",
    "captcha", "access denied", "forbidden", "rate limit",
    "too many requests", "blocked",
)


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"[VOE:T{threading.get_ident() % 100000}] {msg}")


def _describe_response(resp) -> str:
    """One-line summary of a response: status, size, final URL, block hints."""
    body = resp.text or ""
    hits = [m for m in _BLOCK_MARKERS if m in body[:4000].lower()]
    note = f", block-markers={hits}" if hits else ""
    interesting = {
        k: resp.headers[k]
        for k in ("Server", "CF-RAY", "Retry-After", "cf-mitigated")
        if k in resp.headers
    }
    hdr = f", headers={interesting}" if interesting else ""
    return f"status={resp.status_code}, len={len(body)}, final_url={resp.url}{note}{hdr}"


def find_script_element_voe_new(raw_html, prefer_hls=False):
    soup = BeautifulSoup(raw_html, "lxml")
    MKGMa_pattern = r'MKGMa="(.*?)"'
    matches = search(MKGMa_pattern, str(soup), DOTALL)
    source_json = None

    if not matches:
        MKGMa_pattern = r'<script type="application/json">.*\[(.*?)\]</script>'
        matches = search(MKGMa_pattern, str(soup), DOTALL)
    if matches:
        raw_MKGMa = matches.group(1)

        def rot13_decode(s: str) -> str:
            result = []
            for c in s:
                if 'A' <= c <= 'Z':
                    result.append(chr((ord(c) - ord('A') + 13) % 26 + ord('A')))
                elif 'a' <= c <= 'z':
                    result.append(chr((ord(c) - ord('a') + 13) % 26 + ord('a')))
                else:
                    result.append(c)
            return ''.join(result)

        def shift_characters(s: str, offset: int) -> str:
            return ''.join(chr(ord(c) - offset) for c in s)

        try:
            step1 = rot13_decode(raw_MKGMa)
            step2 = step1.replace('_', '')
            step3 = b64decode(step2).decode('utf-8')
            step4 = shift_characters(step3, 3)
            step5 = step4[::-1]

            decoded = b64decode(step5).decode('utf-8')
            try:
                parsed_json = json.loads(decoded)

                # When a quality is being selected we want the HLS *master*
                # playlist (it lists every rendition); otherwise keep the
                # original preference for the single direct mp4.
                if prefer_hls:
                    if 'source' in parsed_json:
                        source_json = {"hls": parsed_json['source']}
                    elif 'direct_access_url' in parsed_json:
                        source_json = {"mp4": parsed_json['direct_access_url']}
                else:
                    if 'direct_access_url' in parsed_json:
                        source_json = {"mp4": parsed_json['direct_access_url']}
                    elif 'source' in parsed_json:
                        source_json = {"hls": parsed_json['source']}
            except json.JSONDecodeError:
                pass

            if not source_json:
                mp4_match = search(r'(https?://[^\s"]+\.mp4[^\s"]*)', decoded)
                m3u8_match = search(r'(https?://[^\s"]+\.m3u8[^\s"]*)', decoded)

                if mp4_match:
                    source_json = {"mp4": mp4_match.group(1)}
                elif m3u8_match:
                    source_json = {"hls": m3u8_match.group(1)}
        except Exception:
            pass
        try:
            if "mp4" in source_json:
                link = source_json["mp4"]
                # Check if the link is base64 encoded
                if isinstance(link, str) and (link.startswith("eyJ") or match(r'^[A-Za-z0-9+/=]+$', link)):
                    try:
                        link = b64decode(link).decode("utf-8")
                    except Exception:
                        pass

                # Ensure the link is a complete URL
                if link.startswith("//"):
                    link = "https:" + link
                return link

            elif "hls" in source_json:
                link = source_json["hls"]
                # Check if the link is base64 encoded
                if isinstance(link, str) and (link.startswith("eyJ") or match(r'^[A-Za-z0-9+/=]+$', link)):
                    try:
                        link = b64decode(link).decode("utf-8")
                    except Exception:
                        pass

                # Ensure the link is a complete URL
                if link.startswith("//"):
                    link = "https:" + link
                return link
        except (KeyError, TypeError):
            pass

    try:
        b64_match = search(r"var a168c='([^']+)'", raw_html)
        if b64_match:
            html_page = b64decode(b64_match.group(1)).decode('utf-8')[::-1]
            html_page = json.loads(html_page)
            html_page = html_page["source"]
            return html_page
    except AttributeError:
        pass

    for VOE_PATTERN in PATTERNS:
        matches = VOE_PATTERN.search(raw_html)
        if matches:
            if matches.group(0).startswith("window.location.href"):
                return find_content_url(matches.group(1), prefer_hls=prefer_hls)
            cache_link = matches.group(1)
            cache_link = b64decode(cache_link).decode('utf-8')
            if cache_link and cache_link.startswith("https://"):
                return cache_link

    return None


def find_content_url(url, attempts=0, prefer_hls=False):
    resp = common.http_get(url)
    html_response = resp.text
    _dbg(f"  page fetch ({'hls' if prefer_hls else 'mp4'} pref) -> {_describe_response(resp)}")
    try:
        ## New Version of VOE 2025-05-01
        content_url = find_script_element_voe_new(html_response, prefer_hls=prefer_hls)
    except AttributeError:
        if attempts < 3:
            attempts += 1
            return find_content_url(url, attempts, prefer_hls=prefer_hls)
        else:
            # no content url found
            _dbg(f"  parse raised AttributeError after {attempts + 1} attempts; giving up")
            return None

    if not content_url:
        _dbg("  parse found no stream URL in the page body")
    return content_url


# ------------------------------------------------------------------
# Quality selection (HLS master playlist parsing)
# ------------------------------------------------------------------

def _get_hls_master(provider_url: str) -> str | None:
    """Return the VOE HLS master-playlist URL for *provider_url* (cached).

    Returns ``None`` when VOE only exposes a single (mp4) stream.
    """
    with _cache_lock:
        if provider_url in _hls_master_cache:
            return _hls_master_cache[provider_url]

    link = find_content_url(provider_url, prefer_hls=True)
    master = link if (link and ".m3u8" in link) else None

    if master:
        _dbg(f"  master playlist = {master}")
    else:
        _dbg(f"  no HLS master (resolved link={link!r}) - VOE mp4-only or blocked")

    # Option A: only cache a successful resolution. A None here may be a
    # genuine "VOE offers only mp4" *or* a transient page/parse failure - and
    # we can't tell them apart from the result alone, so we never cache it.
    # That way a re-queue in the same session re-resolves instead of reusing a
    # poisoned negative entry (the "restart fixes it" bug).
    if master:
        with _cache_lock:
            _hls_master_cache[provider_url] = master
    return master


def _get_variants(master_url: str) -> dict[str, str]:
    """Fetch and parse *master_url* into ``{tier: url}`` (cached)."""
    with _cache_lock:
        if master_url in _variants_cache:
            return _variants_cache[master_url]

    variants: dict[str, str] = {}
    try:
        resp = common.http_get(master_url)
        variants = common.parse_hls_master(resp.text, master_url)
        _dbg(f"  variant fetch -> {_describe_response(resp)}; tiers={sorted(variants)}")
    except Exception as exc:
        variants = {}
        _dbg(f"  variant fetch FAILED: {exc!r}")

    # Option A: only cache a non-empty parse.  An empty result is either a
    # transient fetch/parse failure or a single-quality media playlist; in
    # both cases not caching lets the next attempt re-fetch (and the single-
    # quality case resolves on the first tier anyway, so there's nothing to
    # protect by caching it).
    if variants:
        with _cache_lock:
            _variants_cache[master_url] = variants
    return variants


def _resolve_target_url(url: str, quality: str | None) -> str | None:
    """Resolve the exact stream URL to hand ffmpeg for the requested *quality*.

    Returns ``None`` to signal "this quality isn't available from VOE" so the
    caller (the download worker) can fall back to the next lower tier.
    """
    # No specific tier requested → original behaviour (single direct stream).
    if not quality:
        _dbg(f"resolve url={url} quality=<none>")
        return find_content_url(url)

    _dbg(f"resolve url={url} quality={quality}")
    master = _get_hls_master(url)
    if master:
        variants = _get_variants(master)
        if variants:
            # Master playlist with multiple renditions - pick the exact tier.
            target = variants.get(quality)
            if target:
                _dbg(f"  -> selected {quality}")
            else:
                _dbg(f"  -> {quality} not in master (have {sorted(variants)}); worker falls back")
            return target  # None ⇒ tier unavailable, try next
        # m3u8 but a single-quality media playlist → only one stream exists.
        _dbg("  -> single-quality media playlist; handing master to ffmpeg")
        return master

    # VOE only offers one (mp4) stream; quality can't be chosen, so use it.
    target = find_content_url(url)
    _dbg(f"  -> mp4 fallback: {'got URL' if target else 'NOTHING - VOE failed for this episode'}")
    return target


def download(url, download_path, file_name, quality=None):
    target_url = _resolve_target_url(url, quality)
    if not target_url:
        # Either nothing resolved, or the requested quality tier isn't offered
        # for this stream - report failure so the worker tries the next tier.
        _dbg(f"download returning False (no target) quality={quality}")
        return False
    return common.run_ffmpeg(target_url, download_path, file_name)