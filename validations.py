import site_mirrors


def supported_websites():
    """The canonical hostname of every supported site.

    Backup domains are deliberately absent: this set names the *sites* the app
    knows, and is what settings keys, cache files and page routing are keyed on.
    Which domain a site is currently reachable under is site_mirrors' business.
    """
    return set(site_mirrors.SITE_MIRRORS)


def is_valid_url(url):
    from urllib.parse import urlparse
    try:
        result = urlparse(url)
        # Ensure it has a scheme (http/https) and a domain name
        if all([result.scheme in ['http', 'https'], result.netloc]):
            # A backup domain is as valid as the primary - canonical() accepts
            # both and answers with the site they belong to.
            return site_mirrors.canonical(result.hostname) is not None
        return False
    except ValueError:
        return False
