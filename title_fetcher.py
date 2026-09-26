from PySide6 import QtCore


class TitleFetcher(QtCore.QThread):
    """Fetches all titles for one site in a background thread.

    Emits titles_ready(site, data) where data is {url: [title, alt_title?]}.
    """

    titles_ready = QtCore.Signal(str, dict)

    def __init__(self, site: str, parent=None):
        super().__init__(parent)
        self._site = site

    def run(self):
        import asyncio
        from titles import (
            get_aniworld_titles,
            get_s_titles,
            get_bs_titles,
            get_anikototv_titles,
            get_hanime_titles,
            get_animepahe_titles,
        )

        result: dict[str, list[str]] = {}
        try:
            if self._site == "aniworld.to":
                result = get_aniworld_titles()
            elif self._site == "s.to":
                result = get_s_titles()
            elif self._site == "bs.to":
                result = get_bs_titles()
            elif self._site == "hanime.tv":
                result = get_hanime_titles()
            elif self._site == "animepahe.ch":
                result = get_animepahe_titles()
            elif self._site == "anikototv.to":
                raw = asyncio.run(get_anikototv_titles())
                # hrefs in anikototv are relative - make them absolute
                result = {
                    (f"https://anikototv.to{k}" if k.startswith("/") else k): v
                    for k, v in raw.items()
                }
        except Exception as exc:
            print(f"[TitleFetcher] {self._site}: {exc}")

        self.titles_ready.emit(self._site, result)