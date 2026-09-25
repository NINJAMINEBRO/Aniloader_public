from bs4 import BeautifulSoup
from urllib.error import HTTPError
from urllib.request import urlopen
import aiohttp
import asyncio
import gzip
import requests
from xml.etree import ElementTree

import anikototv_series
import animepahe_series
import browser_fetch
import site_mirrors

# Sent with the API request; the endpoint is picky about default agents.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


async def fetch_html(url, session):
    """Fetches HTML content using a shared aiohttp session."""
    async with session.get(url) as response:
        return await response.text()


async def process_page(page_url, session, results):
    """Fetches a specific page_url and extracts the target <a> elements."""
    try:
        html = await fetch_html(page_url, session)
        soup = BeautifulSoup(html, "lxml")

        # Find all <a class="name d-title"> tags
        title_elements = soup.find_all("a", class_="name d-title")

        for el in title_elements:
            # Trailing slash trimmed along with the "/ep-1": the season index is
            # keyed on these URLs and the site writes them both ways.
            href = el.get("href", "").strip().replace("/ep-1", "").rstrip("/")
            alt_title = el.get("data-jp", "").strip()
            title = el.text.strip()

            if href:
                results[href] = [title, alt_title]
    except Exception as e:
        print(f"Error scraping url {page_url}: {e}")


# titles = asyncio.run(get_anikototv_titles()) must be run like this
async def get_anikototv_titles():
    url = "https://anikototv.to/az-list"
    # 1. Make an initial synchronous request to find the max page number
    html_response = requests.get(url).text
    soup = BeautifulSoup(html_response, "lxml")

    page_link_elements = soup.find_all("a", class_="page-link")
    page_numbers = [
        int(num.text.strip())
        for num in page_link_elements
        if num.text.strip().isdigit()
    ]

    # Fallback to 1 if no pagination elements are found
    highest_page = max(page_numbers) if page_numbers else 1

    # This shared dictionary will hold our final {href: title} mappings
    titles_dict = {}

    # 2. Concurrently fetch all pages from 1 to highest_page
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_page(f"{url}?page={page}", session, titles_dict)
            for page in range(1, highest_page + 1)
        ]
        # Run all page extraction tasks simultaneously
        await asyncio.gather(*tasks)

        # 3. Collapse the seasons of one series into a single row.  The A-Z list
        #    has an entry per season, so "Attack on Titan" occupies six of them;
        #    anikototv_series asks the site which entries belong together, and
        #    only the one naming the series stays searchable - the page expands
        #    it back into the full season list.
        #    A failed sweep costs the grouping, not the catalogue: the titles
        #    are still returned, just one row per season as before.
        #
        #    A collapsed season keeps its entry but loses its titles rather than
        #    being removed outright.  A row with no title is not offered as a
        #    search result, which is the point, but the URL stays a link the app
        #    knows: pasting a season's own address still opens its series, and
        #    url_autocorrect still recognises it instead of "repairing" it into
        #    the nearest surviving slug - which, for sequels that differ by one
        #    digit, would mean quietly opening the wrong season.
        try:
            groups = await anikototv_series.fetch_groups(session)
            index = anikototv_series.build_index(groups, titles_dict)
            anikototv_series.save_index(index)
            for href in anikototv_series.grouped_away(index):
                if href in titles_dict:
                    titles_dict[href] = []
        except Exception as exc:
            print(f"[anikototv] season grouping unavailable: {exc}")

    return titles_dict


_ANIWORLD_INDEX = "https://aniworld.to/animes"


def get_aniworld_titles():
    via_browser = False
    try:
        html_response = urlopen(_ANIWORLD_INDEX)
    except HTTPError as exc:
        # A 403 is Cloudflare turning the plain request away, which an
        # undetected browser can get past.  It is only started then - a browser
        # takes seconds where the request takes milliseconds - and any other
        # error is a genuine failure, raised as before.
        if exc.code != 403:
            raise
        print("[aniworld] title list refused with HTTP 403 - loading it in the browser instead")
        html_response = browser_fetch.fetch(_ANIWORLD_INDEX, "aniworld")
        via_browser = True
    soup = BeautifulSoup(html_response, "lxml")
    titles_dict = {}

    page_link_elements = soup.select("li a[data-alternative-title]")

    for el in page_link_elements:
        href = el.get("href", "").strip()
        alt_title = el.get("data-alternative-title", "").strip()
        title = el.text.strip()

        if href and title:
            titles_dict["https://aniworld.to" + href] = [title, alt_title]

    if via_browser and not titles_dict:
        raise RuntimeError("HTTP 403, and the browser fallback could not get past it either")
    return titles_dict


def get_s_titles():
    # Fetched through site_mirrors: when s.to does not answer, the identical
    # index on serienstream.to is scraped instead.  The URLs stored below stay
    # on s.to either way, so a cache written from the mirror still matches the
    # links the rest of the app builds and compares.
    html_response = site_mirrors.read_text("https://s.to/serien")
    soup = BeautifulSoup(html_response, "lxml")
    titles_dict = {}

    # Target the wrapper <li> elements
    page_link_elements = soup.find_all("li", class_="series-item")

    for el in page_link_elements:
        # 1. Grab the alt title from the <li>
        alt_title = el.get("data-search", "").strip()

        # 2. Find the <a> tag inside this specific <li>
        a_tag = el.find("a")

        # 3. Always check if the <a> tag actually exists before pulling from it!
        if a_tag:
            href = a_tag.get("href", "").strip()
            title = a_tag.text.strip()

            # Only add to dictionary if both href and a visible title exist
            if href and title:
                titles_dict[site_mirrors.absolute("s.to", href)] = [title, alt_title]

    return titles_dict


def get_bs_titles():
    # Same failover as get_s_titles: burningseries.cx stands in for bs.to when
    # it is down, while the stored URLs stay on bs.to.
    html_response = site_mirrors.read_text("https://bs.to/andere-serien")
    soup = BeautifulSoup(html_response, "lxml")
    titles_dict = {}

    page_link_elements = soup.find_all("li")

    for el in page_link_elements:
        a_tag = el.find("a")

        if a_tag:
            href = a_tag.get("href", "").strip()
            title = a_tag.text.strip()

            # Only add to dictionary if both href and a visible title exist and href is for a serie
            if href and 'serie/' in href and title:
                titles_dict[site_mirrors.absolute("bs.to", href)] = [title]

    return titles_dict

# hanime.tv's own catalogue API sits behind a Cloudflare Turnstile challenge and
# is not usable from a script.  Its sitemap is the sanctioned route to the same
# list - robots.txt disallows nothing and advertises this file precisely so that
# the catalogue can be enumerated - and it is served gzipped at a fifteenth of
# the size of the plain XML.
#
# The trade-off is that a sitemap carries no titles, only URLs, so each title is
# derived from its slug.  That is what this fetcher did originally too, and it
# reads acceptably ("koikishi-purely-kiss-2" -> "Koikishi Purely Kiss 2").
_HANIME_SITEMAP = "https://hanime.tv/sitemap.xml.gz"
_HANIME_VIDEO_PATH = "/videos/hentai/"
# Leading bytes of a gzip stream, spelled without escapes for legibility.
_GZIP_MAGIC = bytes.fromhex("1f8b")


def get_hanime_titles():
    """Fetch the hanime.tv catalogue as ``{series_url: [series_title]}``.

    The sitemap lists one entry per episode, but the search bar is a list of
    things to download rather than of individual files, so episodes are grouped
    into series (see :mod:`hanime_series`) and only the series is offered - one
    "Succubus Connect" row instead of three numbered ones.  Each series is keyed
    by its first episode's URL, which is what the page is handed when the row is
    picked; the page expands it back into the full episode list from the index
    written here.
    """
    import hanime_series

    response = requests.get(_HANIME_SITEMAP, headers=_HEADERS, timeout=60)
    response.raise_for_status()

    raw = response.content
    # Gunzip only when the body really is gzip: a proxy that already decoded it
    # would otherwise turn a working fetch into a confusing parse error.
    if raw[:2] == _GZIP_MAGIC:
        raw = gzip.decompress(raw)

    root = ElementTree.fromstring(raw)
    slugs = []
    # Matched on the tag's local name so the sitemap namespace, which the file
    # declares and could reasonably change, never decides whether this works.
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "loc":
            continue
        url = (element.text or "").strip()
        slug = url.partition(_HANIME_VIDEO_PATH)[2]
        # Skip the site's own pages (/home, /search) and anything nested deeper
        # than a single video slug.
        if not slug or "/" in slug:
            continue
        slugs.append(slug)

    grouped = hanime_series.group_slugs(slugs)
    # Persisted before returning so the page can expand a series into episodes
    # without re-fetching the sitemap.
    hanime_series.save_index(grouped)

    return {
        hanime_series.url_for_slug(episodes[0][1]): [
            hanime_series.title_from_slug(series_slug)
        ]
        for series_slug, episodes in grouped.items()
        if episodes
    }


def get_animepahe_titles():
    # The whole catalogue sits on one page - "list mode" is the site's own
    # plain-text index of every series, with no pagination to walk - so a single
    # request replaces the page sweep anikototv needs.  Routed through
    # site_mirrors so animepahe.ng stands in when animepahe.ch does not answer;
    # the stored URLs stay on animepahe.ch either way.
    html_response = site_mirrors.read_text("https://animepahe.ch/series/list-mode/")
    soup = BeautifulSoup(html_response, "lxml")
    titles_dict = {}

    # Scoped to the index container: the sidebar carries its own <a class="series">
    # links for the currently popular shows, which would otherwise be scraped
    # twice over and, for the thumbnail half of each pair, with no title at all.
    page_link_elements = soup.select("div.soralist a.series")

    for el in page_link_elements:
        href = el.get("href", "").strip()
        title = el.text.strip()

        # The site links each series with its trailing slash; that form is kept
        # as-is so a stored link matches the one a user copies from the site.
        if href and title:
            titles_dict[site_mirrors.absolute("animepahe.ch", href)] = [title]

    # Collapse the seasons of one series into a single row, the way anikototv's
    # catalogue is collapsed - but worked out from the titles, since animepahe
    # publishes no relation data of any kind.  The row is offered under the
    # series' plain name ("Rent-a-Girlfriend"), with every season's own title
    # kept beside it as a search alias, so looking up either the series or one
    # particular season still finds it.  A collapsed season keeps its entry with
    # no titles: not a search result, still a link the app knows and routes.
    index = animepahe_series.build_index(titles_dict)
    animepahe_series.save_index(index)
    for entry, members in index.items():
        if entry in titles_dict:
            titles_dict[entry] = [animepahe_series.base_name(members)] + [
                m[4] for m in members if m[4]
            ]
    for href in animepahe_series.grouped_away(index):
        if href in titles_dict:
            titles_dict[href] = []

    return titles_dict
