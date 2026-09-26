"""Grouping anikototv.to's per-season catalogue entries into one series.

anikototv publishes every season as its own entry in the A-Z list: "Attack on
Titan", "Attack on Titan Season 2" and "Attack on Titan: The Final Season Part
3" are three unrelated rows as far as that list is concerned.  The search bar
therefore offered the same show half a dozen times, and the page had no season
to offer at all - it labelled everything "Season 1".

The site itself knows better.  Every watch page pulls a season strip from
``api/seasons/<id>``, and that strip is curated: it lists the seasons of one
series in order, each under the label the site shows ("Season 2", "Season 4:
Part 1", "OVA", "The Movie"), and it leaves spin-offs out - "Attack on Titan:
Junior High" does not appear in Attack on Titan's strip.  That endpoint is taken
as the authority here and nothing is guessed from the titles, because the titles
cannot carry it: the catalogue numbers seasons five different ways at once ("My
Hero Academia 2", "… 5th Season", "… Season 6", "… Final Season") while "My Hero
Academia: Vigilantes" - a different show - is named exactly like a season of it.

The endpoint is keyed by the site's internal numeric id, which the A-Z list does
not carry, so the index is built by sweeping the id range rather than by looking
each series up.  That works out cheaper than it sounds: every call returns the
*whole* group and marks the queried series ``active``, so one pass yields both
the groups and the id of each series in one.  Those ids are what let the page
pull a season's episode list straight from ``ajax/episode/list/<id>`` instead of
loading its watch page first.

The sweep is a few thousand small JSON requests and runs as part of the
catalogue fetch, so it is paid once per cache period rather than once per
search.  When it fails - or has never run - nothing breaks: the search bar
simply lists seasons separately again, and the page falls back to asking the
endpoint about the one series it was handed.
"""

import asyncio
import re

import cache_manager

# Stored next to the ordinary title cache (as ``anikototv_to_seasons.json``),
# the same arrangement hanime.tv's episode index uses.  It is written whenever
# the catalogue is fetched, whether or not title caching is enabled for the
# site, because the page reads it to fill the season pickers.
SEASON_INDEX_SITE = "anikototv.to_seasons"

SEASONS_API = "https://anikototv.to/api/seasons/"
EPISODES_API = "https://anikototv.to/ajax/episode/list/"

# Both endpoints exist to serve the site's own scripts and say so: without the
# header that marks the call as one of those, they answer ``status 500`` and
# "Invalid Request" rather than the season list.  They are sent per request
# instead of being expected of the session, so the sweep works whichever session
# the catalogue fetcher happens to hand it.
AJAX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://anikototv.to/",
}

# How many season lookups may be in flight at once.  The endpoint answers in
# well under a tenth of a second, so this is about being a considerate guest
# rather than about throughput.
_CONCURRENCY = 24

# The id space is swept in blocks and stops once a whole block comes back
# "no such series", which is how the sweep keeps up with a catalogue that grows
# without a hard-coded upper bound baked in here.  The ceiling only exists so a
# site that answered 200 to everything could never spin forever.
_BLOCK = 500
_MAX_ID = 40000

# A season strip that lists only the series itself is not a grouping, and the
# endpoint sends one for plenty of standalone shows.
_MIN_GROUP = 2


# The label the site gives a series' own first season.  "Season 1, Part 2" and
# "Season 1: …" are deliberately not matched: they are halves of that season,
# not the season itself.
_SEASON_ONE = re.compile(r"^\s*season\s*0*1\s*$", re.IGNORECASE)


def primary_index(members, known=None) -> "int | None":
    """Which member of a group names it, as a position in *members*.

    Season 1 is the one that carries the series' plain name - "Jujutsu Kaisen
    (TV)" rather than "Jujutsu Kaisen 0: The Movie" - and the site does not
    always list it first: a prequel film or a recap can open the strip.  So the
    season labelled 1 is preferred, and the site's own first entry is used only
    when no member is labelled that way (a series listed by arc or by era, like
    "Doraemon (2005 Series)").

    Pass *known* - the catalogue's URLs - to ignore members the search bar has
    no title for, so a group is never keyed on a link it could not display.
    Returns None when *members* has nothing usable.
    """
    positions = [
        i for i, member in enumerate(members)
        if known is None or member[1] in known
    ]
    if not positions:
        return None
    for i in positions:
        if _SEASON_ONE.match(members[i][0] or ""):
            return i
    return positions[0]


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def parse_seasons(html: str) -> "list[tuple[str, str, bool]]":
    """Read a season strip into ``[(label, series_url, is_active), ...]``.

    The strip's own order is kept: it is the order the site shows the seasons
    in, which is the one a viewer would expect the range pickers to follow.
    """
    from bs4 import BeautifulSoup

    if not (html or "").strip():
        return []

    soup = BeautifulSoup(html, "lxml")
    seasons: list[tuple[str, str, bool]] = []
    for slide in soup.select("div.season"):
        anchor = slide.select_one("a[href]")
        if anchor is None:
            continue
        url = (anchor.get("href") or "").strip().rstrip("/")
        if not url:
            continue
        name = slide.select_one(".name")
        label = name.get_text(strip=True) if name else ""
        seasons.append((label, url, "active" in (slide.get("class") or [])))
    return seasons


# ----------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------

async def _fetch_group(session, series_id: int, semaphore) -> "tuple[bool, list]":
    """Ask the endpoint about one id.

    Returns ``(exists, seasons)``.  *exists* distinguishes an id the site has no
    series for from one whose series simply has no other seasons - only the
    former is a signal that the sweep has run off the end of the catalogue.
    """
    import aiohttp

    async with semaphore:
        try:
            async with session.get(
                f"{SEASONS_API}{series_id}",
                headers=AJAX_HEADERS,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                payload = await response.json(content_type=None)
        except Exception:
            # A single failed lookup costs one series its grouping, which the
            # page recovers from on its own; it must not abort the sweep.
            return True, []

    if not isinstance(payload, dict):
        return True, []
    # Only "no such series" says the sweep has reached the end of the catalogue.
    # Every other unhappy answer - a refused request, a server error - is this
    # one lookup going wrong, and reading it as the end would stop the sweep
    # dead at the first hiccup.
    if payload.get("status") == 404:
        return False, []
    if payload.get("status") != 200:
        return True, []
    return True, parse_seasons(payload.get("result") or "")


async def fetch_groups(session) -> "list[list[tuple[str, str, int | None]]]":
    """Sweep the season endpoint and return every group it knows.

    Each group is ``[(label, series_url, series_id), ...]`` in the site's own
    order, with *series_id* filled in for the members the sweep saw answering
    for themselves (which is all of them, short of a failed request).

    The same group comes back once per member, so groups are de-duplicated by
    the set of URLs they contain before being returned.
    """
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    # url -> the id that returned it as the *active* season, i.e. its own id.
    ids: dict[str, int] = {}
    # frozenset(urls) -> [(label, url), ...], which drops the duplicates.
    groups: dict[frozenset, list[tuple[str, str]]] = {}

    start = 1
    while start <= _MAX_ID:
        block = range(start, min(start + _BLOCK, _MAX_ID + 1))
        results = await asyncio.gather(
            *(_fetch_group(session, series_id, semaphore) for series_id in block)
        )

        for series_id, (exists, seasons) in zip(block, results):
            if not exists or len(seasons) < _MIN_GROUP:
                continue
            members = [(label, url) for label, url, _active in seasons]
            groups.setdefault(frozenset(url for _l, url in members), members)
            for _label, url, active in seasons:
                if active:
                    ids[url] = series_id

        # Every id in the block was unknown to the site: the catalogue ended.
        if not any(exists for exists, _ in results):
            break
        start += _BLOCK

    if not groups:
        # Never expected: the catalogue has hundreds of grouped series.  Saying
        # so beats leaving the search bar silently ungrouped with no hint why.
        print("[anikototv] season sweep found no groups - endpoint changed?")

    return [
        [(label, url, ids.get(url)) for label, url in members]
        for members in groups.values()
    ]


async def fetch_season_strip(session, series_id: int) -> "list[tuple[str, str, bool]]":
    """The live season strip for one id, used when the index has nothing to say."""
    _exists, seasons = await _fetch_group(session, series_id, asyncio.Semaphore(1))
    return seasons


# ----------------------------------------------------------------------
# Index building and persistence
# ----------------------------------------------------------------------

def build_index(groups, known_urls) -> "dict[str, list]":
    """Key each group by the one entry the search bar will offer for it.

    The entry is the member :func:`primary_index` picks - season 1 where there
    is one - restricted to the seasons the catalogue actually lists.  That
    restriction matters because the season strip occasionally names a season the
    A-Z list does not, and keying a group on a URL the search bar has no title
    for would hide the whole series instead of collapsing it.
    """
    index: dict[str, list] = {}
    for members in groups:
        position = primary_index(members, known_urls)
        if position is None:
            continue
        index[members[position][1]] = [
            [label, url, series_id] for label, url, series_id in members
        ]
    return index


def save_index(index: "dict[str, list]") -> None:
    """Persist *index* so the search bar and the page can both read it back."""
    cache_manager.save_cache(SEASON_INDEX_SITE, index)


def load_index() -> "dict[str, list]":
    """Return the stored index, or ``{}`` when there isn't one yet."""
    payload = cache_manager.load_cache(SEASON_INDEX_SITE)
    if not payload:
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _clean(members) -> "list[tuple[str, str, int | None]]":
    """Read one stored group back, skipping entries a bad write left malformed."""
    cleaned: list[tuple[str, str, int | None]] = []
    for entry in members or []:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            continue
        label, url, series_id = entry
        if not isinstance(url, str) or not url:
            continue
        cleaned.append((
            str(label or ""),
            url,
            series_id if isinstance(series_id, int) else None,
        ))
    return cleaned


def grouped_away(index: "dict[str, list]") -> "set[str]":
    """Every URL the search bar should drop because a group already covers it.

    That is each group's members minus the entry the group is keyed by, so one
    row is offered per series instead of one per season.
    """
    away: set[str] = set()
    for entry, members in index.items():
        away.update(url for _label, url, _sid in _clean(members) if url != entry)
    return away


def seasons_for_url(url: str) -> "list[tuple[str, str, int | None]]":
    """The stored season list of the series *url* belongs to, or ``[]``.

    Any member of a group answers with the whole group, so a link pasted for
    season 3 opens the same series page as one picked from the search bar.
    """
    url = (url or "").rstrip("/")
    if not url:
        return []

    index = load_index()
    members = _clean(index.get(url))
    if members:
        return members

    for entry_members in index.values():
        cleaned = _clean(entry_members)
        if any(member_url == url for _label, member_url, _sid in cleaned):
            return cleaned
    return []
