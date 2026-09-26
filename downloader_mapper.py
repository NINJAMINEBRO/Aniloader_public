"""Dispatches a download request to the correct provider module.

Returns True if the download succeeded, False otherwise.

Each branch imports its provider module lazily and forwards the request;
providers without a real implementation yet return False immediately.
"""


def map(provider: str, url: str, download_path: str, file_name: str, quality: str | None = None) -> bool:
    """Route *url* to the downloader for *provider* and return success.

    Parameters
    ----------
    provider:
        Recognised provider name, e.g. ``"VOE"``, ``"Vidmoly"``.
    url:
        Episode/video URL forwarded to the provider's downloader.
    download_path:
        Directory in which the output file will be created.
    file_name:
        Desired filename (including extension) for the downloaded file.
    quality:
        Requested quality tier (e.g. ``"1080p"``).  Only VOE honours this;
        it selects the matching rendition from the HLS master playlist and
        returns False when that tier isn't offered so the caller can fall
        back to the next lower tier.
    """
    try:
        if provider == "VOE":
            from downloaders import VOE
            # VOE.download returns False on failure, True on success
            result = VOE.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Vidmoly":
            from downloaders import Vidmoly
            result = Vidmoly.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Doodstream":
            from downloaders import Doodstream
            result = Doodstream.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Filemoon":
            from downloaders import Filemoon  # noqa: F401 - not implemented
            return False

        if provider == "Vidoza":
            from downloaders import Vidoza
            # Vidoza.download returns False on failure, True on success
            result = Vidoza.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "SpeedFiles":
            from downloaders import SpeedFiles
            result = SpeedFiles.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Hanime":
            from downloaders import Hanime
            result = Hanime.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Kiwi-Stream":
            # Module file is KiwiStream.py (no dash), so a normal import works;
            # only the provider *name* carries the dash.
            from downloaders import KiwiStream
            result = KiwiStream.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Vidstream":
            from downloaders import Vidstream
            result = Vidstream.download(url, download_path, file_name, quality=quality)
            return result is not False

        if provider == "Blogger":
            from downloaders import Blogger
            result = Blogger.download(url, download_path, file_name, quality=quality)
            return result is not False

    except Exception as exc:
        print(f"[downloader_mapper] {provider} raised an error: {exc}")
        return False

    print(f"[downloader_mapper] Unknown provider: {provider!r}")
    return False