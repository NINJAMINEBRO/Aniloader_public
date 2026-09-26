"""Loading pages in a real browser when a site refuses a plain request.

Cloudflare answers an HTTP client it distrusts with a challenge instead of the
page - an HTTP 403 and a "Just a moment…" interstitial that only a real browser
gets past.  This module is the way past it: an undetected, headless Chrome
driven through SeleniumBase.  It is deliberately only a fallback.  A browser
takes seconds to start where a request takes milliseconds, so callers make
their normal request first and come here once it has actually been refused.

A :class:`Browser` starts Chrome on its first fetch and keeps it for every page
after that.  A caller that turns out to need a dozen pages - aniworld's season
list, one page per season - pays for one launch rather than twelve, and one
that never needs the browser pays for nothing.

Chrome itself must be installed; without it every fetch comes back empty and
the reason is printed.
"""

# Substrings that indicate Cloudflare is interrupting the request with an
# interstitial / challenge page rather than serving the real page.
_CF_MARKERS = (
    "just a moment",
    "verifying you are human",
    "attention required",
    "cf-browser-verification",
    "challenge-platform",
    "_cf_chl_opt",
    "cf_chl",
)


def looks_like_cloudflare(html: str, status_code: int = 200) -> bool:
    """Heuristically decide whether *html* is a Cloudflare challenge page."""
    if status_code in (403, 429, 503):
        return True
    lowered = (html or "").lower()
    return any(marker in lowered for marker in _CF_MARKERS)


class Browser:
    """One undetected Chrome, started on first use and shared by every fetch.

    Use it as a context manager so Chrome is closed however the caller exits::

        with Browser("aniworld") as browser:
            html = browser.fetch(url)

    *name* prefixes the messages printed about it, e.g. ``[aniworld]``.
    """

    def __init__(self, name: str = "browser"):
        self._name = name
        self._context = None     # SeleniumBase's SB context manager, once entered
        self._sb = None          # the driver it yielded
        self._unavailable = False

    def __enter__(self) -> "Browser":
        return self

    def __exit__(self, *_exc) -> bool:
        self.close()
        return False

    def fetch(self, url: str) -> str:
        """The HTML of *url* once any Cloudflare challenge has been cleared.

        ``uc_open_with_reconnect`` briefly detaches the webdriver so the bot
        check runs without seeing automation, then reattaches once the page
        has loaded.  Returns "" when Chrome can't be started or the page can't
        be opened at all; a challenge that never clears comes back as the
        challenge page, which callers recognise by what it lacks.
        """
        sb = self._driver()
        if sb is None:
            return ""

        html = ""
        try:
            sb.uc_open_with_reconnect(url, reconnect_time=4)
            html = sb.get_page_source()

            # Older interactive challenge: a submit button labelled "Weiter".
            if 'button type="submit"' in html and "Weiter" in html:
                try:
                    sb.wait_for_element_visible('button[type="submit"]', timeout=30)
                    sb.click('button[type="submit"]')
                    sb.sleep(2)
                    html = sb.get_page_source()
                except Exception:
                    pass

            # Still challenged?  One more reconnect cycle with a longer wait.
            if looks_like_cloudflare(html):
                sb.uc_open_with_reconnect(url, reconnect_time=6)
                html = sb.get_page_source()
        except Exception as exc:
            print(f"[{self._name}] browser fallback failed for {url}: {exc}")
        return html

    def close(self) -> None:
        """Shut Chrome down, if it was ever started."""
        context, self._context, self._sb = self._context, None, None
        if context is not None:
            try:
                context.__exit__(None, None, None)
            except Exception:
                pass

    def _driver(self):
        """The running browser, starting it on first use; None if it can't start."""
        if self._sb is None and not self._unavailable:
            from seleniumbase import SB  # imported lazily - heavy and browser-dependent

            context = SB(uc=True, headless2=True)
            try:
                self._sb = context.__enter__()
                self._context = context
            except Exception as exc:
                # Remembered, so a caller fetching many pages doesn't try (and
                # report) a doomed browser launch once per page.
                self._unavailable = True
                if "Chrome not found" in str(exc):
                    print(f"[{self._name}] Chrome must be installed for the Cloudflare workaround.")
                else:
                    print(f"[{self._name}] browser fallback could not start: {exc}")
        return self._sb


def fetch(url: str, name: str = "browser") -> str:
    """:meth:`Browser.fetch` for a single page, closing Chrome afterwards."""
    with Browser(name) as browser:
        return browser.fetch(url)
