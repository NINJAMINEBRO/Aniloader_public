"""The language Aniloader's own interface is shown in.

Every piece of text the program shows goes through :func:`tr`, which looks it up
by its English wording in the chosen language's table (see ``locales/``) and
falls back to that English wording when there is no translation - so a string
added without one shows up in English instead of breaking anything.

The language is picked in Settings -> General and takes effect from the next
start.  Widgets are built with their text, so switching live would mean
rebuilding them - the download queue among them, mid-download - and the setting
is read once instead, before the window is built.

Deliberately never translated: anything that comes from the sites (series and
episode titles, the season names they use), provider names, and the season and
episode names downloads are saved under.  Those are folder and file names, and a
library whose folders changed language along with the interface would stop
recognising the episodes it already holds.
"""

from locales import french, german, indonesian, portuguese, spanish, thai, vietnamese

DEFAULT_LANGUAGE = "English"

# Setting value -> (name shown in the picker, translations, Qt's locale name).
# Each language is listed under its own name, so someone who switched to a
# language they can't read still finds the way back to theirs.
LANGUAGES: dict[str, tuple[str, dict[str, str], str]] = {
    "English":    ("English",            {},                       "en"),
    "German":     ("Deutsch",            german.TRANSLATIONS,      "de"),
    "Spanish":    ("Español",            spanish.TRANSLATIONS,     "es"),
    "French":     ("Français",           french.TRANSLATIONS,      "fr"),
    "Portuguese": ("Português (Brasil)", portuguese.TRANSLATIONS,  "pt_BR"),
    "Vietnamese": ("Tiếng Việt",         vietnamese.TRANSLATIONS,  "vi"),
    "Indonesian": ("Bahasa Indonesia",   indonesian.TRANSLATIONS,  "id"),
    "Thai":       ("ไทย",                thai.TRANSLATIONS,        "th"),
}

_language = DEFAULT_LANGUAGE

# Qt's own translations (context menus of text fields and the like), kept
# referenced for as long as they are installed.
_qt_translator = None


def set_language(language: str) -> None:
    """Show the interface in *language*, a :data:`LANGUAGES` key.

    Anything unknown - a hand-edited or outdated settings file - falls back to
    English.  Call it before any widget is built: text already on screen keeps
    the language it was created in.
    """
    global _language
    _language = language if language in LANGUAGES else DEFAULT_LANGUAGE
    _install_qt_translations(LANGUAGES[_language][2])


def current_language() -> str:
    """The :data:`LANGUAGES` key the interface is currently shown in."""
    return _language


def tr(text: str, /, **values) -> str:
    """*text* in the interface language, ``{placeholders}`` filled from *values*.

    *text* is positional-only, so a placeholder may be named anything -
    ``{language}`` included - without colliding with the parameters here.
    """
    return translate(text, _language, **values)


def translate(text: str, language: str, /, **values) -> str:
    """*text* in a specific *language* rather than the current one.

    Used to say something in a language the user has just picked, before it has
    taken effect.
    """
    table = LANGUAGES.get(language, LANGUAGES[DEFAULT_LANGUAGE])[1]
    translated = table.get(text, text)
    if not values:
        return translated
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        # A translation with a broken placeholder must not take the text with it.
        return text.format(**values)


def N_(text: str) -> str:
    """Mark *text* for translation where it is defined; :func:`tr` it where shown.

    For strings kept in constants: translating them at import time would fix
    them in whatever language was active then, which is always English.
    """
    return text


def _install_qt_translations(locale: str) -> None:
    """Load Qt's translations for its built-in texts, where Qt ships them.

    That covers the context menus of text fields and spin boxes ("Copy",
    "Paste", …) for the languages Qt has files for.  Where it has none the load
    simply fails and those few texts stay English.
    """
    global _qt_translator
    from PySide6 import QtCore

    app = QtCore.QCoreApplication.instance()
    if app is None:
        return
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if locale == "en":
        return

    translator = QtCore.QTranslator(app)
    folder = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{locale}", folder):
        app.installTranslator(translator)
        _qt_translator = translator
