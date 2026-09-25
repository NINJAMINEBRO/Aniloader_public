"""Backup domains for the sites that keep moving, and automatic failover to them.

bs.to and s.to are regularly unreachable - blocked, rate-limited, or simply
down - while the very same catalogue stays online under a second domain
(``burningseries.cx`` and ``serienstream.to``).  Every request the app makes to
those sites therefore goes through here: the primary domain is tried first, and
when it does not answer the request is repeated against the mirror.

Two rules keep the rest of the program unaware that any of this happens:

*Canonical identity.*  A site is always named by its primary hostname.  Settings
keys, cache files, page routing and every stored series URL use ``bs.to`` even
when the bytes came from ``burningseries.cx``, so a cache written today still
matches a link pasted tomorrow, whichever domain happened to be alive on either
day.  Only when a request leaves the app is the host swapped.

*Sticky, self-healing choice.*  A host is tracked in three states - answering,
benched, or not yet tried - and a verdict is remembered, so one request pays for
the discovery instead of each of them rediscovering the outage.  A failed host is
benched rather than dropped: once the bench expires it is tried again, which is
what makes the app return to the primary domain on its own once the site
recovers.  A domain that does not resolve at all sits out far longer than one
that merely erred, because re-probing it costs a DNS timeout and almost never
changes its mind.

The third state is what :func:`live_url` rests on.  Most requests go through
:func:`http_get` or :func:`fetch_text`, which can simply try the next domain when
one fails.  Two callers cannot: the browser that drives bs.to resolution, and the
hoster redirect handed to a provider downloader.  They fetch on their own and
report nothing back, so the URL they receive is the only one they will ever try -
which means it must be checked *before* they get it, not assumed.  Handing those
callers the primary just because nothing had tested it yet is precisely how a
dead domain reaches a downloader with no way to recover.

Only transport-level failures count as "this domain is down" - connection
errors, timeouts, and the statuses in :data:`_DOWN_STATUSES`.  A 404 does not:
it is the site faithfully reporting that one particular page does not exist, and
switching domains over it would turn a missing episode into a hunt across every
mirror that can only end the same way.
"""

import threading
import time
from urllib.parse import urljoin, urlparse, urlunparse

# Every supported site, mapped to the domains that serve it - primary first.
# Sites with no known backup are listed too, so callers can route *all* their
# requests through this module without special-casing.
SITE_MIRRORS: dict[str, tuple[str, ...]] = {
    "aniworld.to": ("aniworld.to",),
    "s.to": ("s.to", "serienstream.to"),
    "bs.to": ("bs.to", "burningseries.cx"),
    "anikototv.to": ("anikototv.to",),
    "hanime.tv": ("hanime.tv",),
    "animepahe.ch": ("animepahe.ch", "animepahe.ng"),
}

# How long a host stays benched after it failed before it is tried again. Long
# enough that a dead domain is not re-probed on every request, short enough that
# a recovered primary is picked back up within one browsing session.
_DOWN_TTL = 900.0  # seconds

# A domain whose name does not resolve at all is not having a bad minute - it
# has been taken down or moved, which is exactly what happened to bs.to and
# s.to.  Re-probing that costs a DNS timeout every time and essentially never
# succeeds, so it is benched for far longer than an ordinary failure.
_HARD_DOWN_TTL = 6 * 3600.0  # seconds

# HTTP statuses meaning "this domain is not serving us", as opposed to a genuine
# answer about the requested page.  403 and 429 are here because that is how
# these sites refuse a whole client, not how they report a missing page.
_DOWN_STATUSES = frozenset({403, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})

# Substrings that identify a name-resolution failure across requests/aiohttp.
_DNS_MARKERS = (
    "nameresolutionerror", "name or service not known", "getaddrinfo failed",
    "nodename nor servname", "temporary failure in name resolution",
    "no address associated with hostname", "cannot connect to host",
)

# How long to wait on a probe. A probe only has to answer "is this domain
# alive", so it is kept short - a slow probe would show up as a stall before
# every download.
_PROBE_TIMEOUT = 8

# Hosts seen answering, and host -> monotonic time at which its bench expires.
# Together they give three states - up, down, and not yet known - which is what
# lets live_url() tell "the primary works" apart from "nobody has checked yet".
_healthy: set[str] = set()
_down_until: dict[str, float] = {}
_lock = threading.Lock()


# ----------------------------------------------------------------------
# Host bookkeeping
# ----------------------------------------------------------------------

def canonical(host: str) -> str | None:
    """The primary hostname for *host*, or None if it is not one of our sites.

    Accepts any mirror as well as the primary itself, with or without ``www.``,
    so a link the user pasted from a mirror is recognised as the site it is.
    """
    host = (host or "").lower().removeprefix("www.")
    for site, hosts in SITE_MIRRORS.items():
        if host in hosts:
            return site
    return None


def all_hosts() -> set[str]:
    """Every hostname that belongs to a supported site, mirrors included."""
    return {host for hosts in SITE_MIRRORS.values() for host in hosts}


def has_mirror(site: str) -> bool:
    """True when *site* has at least one backup domain to fall back to."""
    return len(SITE_MIRRORS.get(site, ())) > 1


def _is_dns_failure(exc: Exception) -> bool:
    """True when *exc* means the hostname does not resolve at all."""
    text = f"{exc}".lower()
    return any(marker in text for marker in _DNS_MARKERS)


def note_failure(host: str, hard: bool = False) -> None:
    """Bench *host*: later requests prefer another domain until it expires.

    *hard* marks a domain that does not resolve, which earns the long bench -
    see :data:`_HARD_DOWN_TTL`.
    """
    with _lock:
        _healthy.discard(host)
        _down_until[host] = time.monotonic() + (_HARD_DOWN_TTL if hard else _DOWN_TTL)


def note_success(host: str) -> None:
    """Record that *host* answered - it is known good from here on."""
    with _lock:
        _healthy.add(host)
        _down_until.pop(host, None)


def is_down(host: str) -> bool:
    """True while *host* is benched."""
    with _lock:
        return time.monotonic() < _down_until.get(host, 0.0)


def is_up(host: str) -> bool:
    """True when *host* has actually answered and is not currently benched."""
    with _lock:
        return host in _healthy and time.monotonic() >= _down_until.get(host, 0.0)


def hosts_for(site: str) -> list[str]:
    """The domains to try for *site*, best first.

    Three tiers, each keeping the declared order within itself: domains known to
    answer, then domains nobody has tried yet, then benched ones.  Benched hosts
    are moved to the back rather than dropped, so a site whose domains are all
    benched is still attempted instead of failing outright.

    The middle tier is the point of the design: an untried primary outranks a
    benched one but not a mirror already known to work, so the app stops
    reaching for a domain it has already watched fail.
    """
    hosts = list(SITE_MIRRORS.get(site, (site,)))
    return ([h for h in hosts if is_up(h)]
            + [h for h in hosts if not is_up(h) and not is_down(h)]
            + [h for h in hosts if is_down(h)])


# ----------------------------------------------------------------------
# URL rewriting
# ----------------------------------------------------------------------

def with_host(url: str, host: str) -> str:
    """*url* pointed at *host*, keeping path, query and fragment untouched."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme or "https", host, parsed.path,
                       parsed.params, parsed.query, parsed.fragment))


def to_canonical(url: str) -> str:
    """*url* rewritten onto its site's primary domain.

    Used on anything stored or compared - cached titles, the ``{url: site}``
    map, the URL the user confirmed - so a link is one single string regardless
    of which mirror it was picked up from.  URLs belonging to no supported site
    are handed back unchanged.
    """
    site = canonical(urlparse(url).hostname or "")
    return with_host(url, site) if site else url


def absolute(site: str, href: str) -> str:
    """An absolute, canonical URL for *href* as found on a page of *site*.

    Scraped hrefs are normally relative, but a mirror sometimes writes its own
    domain into them.  Both forms are folded onto the site's primary domain, so
    a link that gets stored never records which mirror happened to serve the
    page it was scraped from.
    """
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "://" in href:
        return to_canonical(href)
    return urljoin(f"https://{site}/", href)


def candidates(url: str) -> list[str]:
    """*url* rewritten onto each domain of its site, best first.

    A URL belonging to no supported site yields just itself, so callers can feed
    anything through the fetch helpers below.
    """
    site = canonical(_host_of(url))
    if site is None:
        return [url]
    return [with_host(url, host) for host in hosts_for(site)]


def _host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


# ----------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------

def _log_switch(next_url: str, host: str, reason: str) -> None:
    print(f"[mirrors] {host} unavailable ({reason}) - retrying on {_host_of(next_url)}")


def http_get(url: str, **kwargs):
    """:func:`downloaders.common.http_get`, retried on the backup domain.

    Returns the first response from a domain that answered.  When every domain
    failed, the last exception is raised (or the last response returned) -
    exactly what a caller of ``common.http_get`` already handles.
    """
    from downloaders import common

    attempts = candidates(url)
    last_exc: Exception | None = None
    last_resp = None
    for index, attempt in enumerate(attempts):
        host = _host_of(attempt)
        try:
            resp = common.http_get(attempt, **kwargs)
        except Exception as exc:
            last_exc = exc
            note_failure(host, hard=_is_dns_failure(exc))
            if index + 1 < len(attempts):
                _log_switch(attempts[index + 1], host, type(exc).__name__)
            continue
        if resp.status_code in _DOWN_STATUSES:
            last_resp = resp
            note_failure(host)
            if index + 1 < len(attempts):
                _log_switch(attempts[index + 1], host, f"HTTP {resp.status_code}")
            continue
        note_success(host)
        return resp

    if last_resp is not None:
        return last_resp
    raise last_exc


def read_text(url: str, **kwargs) -> str:
    """The page body at *url*, fetched from whichever domain answers."""
    return http_get(url, **kwargs).text


async def fetch_text(session, url: str, **kwargs) -> str:
    """``session.get(url)`` then ``.text()`` for aiohttp, retried on the mirror.

    Mirrors :func:`http_get` for the async scrapers.  The final failure is
    raised rather than swallowed, so the page's error handling still reports an
    unreachable site instead of silently showing an empty season list.
    """
    attempts = candidates(url)
    last_exc: Exception | None = None
    for index, attempt in enumerate(attempts):
        host = _host_of(attempt)
        try:
            async with session.get(attempt, **kwargs) as response:
                if response.status in _DOWN_STATUSES:
                    note_failure(host)
                    last_exc = RuntimeError(f"{host} returned HTTP {response.status}")
                    if index + 1 < len(attempts):
                        _log_switch(attempts[index + 1], host, f"HTTP {response.status}")
                    continue
                text = await response.text()
        except Exception as exc:
            last_exc = exc
            note_failure(host, hard=_is_dns_failure(exc))
            if index + 1 < len(attempts):
                _log_switch(attempts[index + 1], host, type(exc).__name__)
            continue
        note_success(host)
        return text

    raise last_exc if last_exc is not None else RuntimeError(f"could not fetch {url}")


def probe(host: str) -> bool:
    """Ask *host* whether it is alive, and remember the answer.

    Cheap and rarely needed: the result is recorded, so a domain is probed once
    and every later call reads the verdict instead of repeating the request.
    """
    from downloaders import common

    try:
        # retries=0 - this *is* the retry decision, so retrying inside it would
        # only multiply the wait before falling through to the mirror.
        resp = common.http_get(f"https://{host}/", timeout=_PROBE_TIMEOUT, retries=0)
    except Exception as exc:
        note_failure(host, hard=_is_dns_failure(exc))
        return False
    if resp.status_code in _DOWN_STATUSES:
        note_failure(host)
        return False
    note_success(host)
    return True


def live_url(url: str) -> str:
    """*url* on a domain that is actually answering.

    This is the exit from the failover loop: the browser that bs.to resolution
    drives, and the hoster redirects handed to a provider downloader, both fetch
    on their own and report nothing back that could trigger a retry.  Whatever
    URL they are given is the only one they will ever try.

    So this never guesses.  A domain already known to answer is used directly;
    otherwise the candidates are probed in order and the first one that responds
    wins.  Returning the primary merely because nothing had tested it yet is the
    one thing this must not do - that is how a dead domain reaches a downloader
    that cannot fall back.  If every probe fails the best-ranked candidate is
    returned anyway, leaving the caller to fail with a real error rather than a
    silently wrong URL.
    """
    if canonical(_host_of(url)) is None:
        return url                        # a hoster link, not one of our sites
    options = candidates(url)
    for option in options:
        if is_up(_host_of(option)):
            return option
    for option in options:
        if probe(_host_of(option)):
            return option
    return options[0]
