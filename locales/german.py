"""German interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "Einstellungen",
    "Update": "Update",
    "Update to {build}": "Update auf {build}",
    "Installed build: {build}": "Installierter Build: {build}",
    "Available build: {build}": "Verfügbarer Build: {build}",
    "Type something...": "Etwas eingeben...",
    "Confirm": "Bestätigen",
    "Back": "Zurück",
    "Under Development": "In Entwicklung",
    "Invalid URL": "Ungültige URL",
    "No enabled providers or languages for this site": "Keine aktivierten Anbieter oder Sprachen für diese Seite",
    "No enabled providers for this site": "Keine aktivierten Anbieter für diese Seite",
    "No enabled languages for this site": "Keine aktivierten Sprachen für diese Seite",
    "fetching titles: {sites}": "Titel werden geladen: {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "Aniloader aktualisieren",
    "Update from build {installed} to {available}?": "Von Build {installed} auf {available} aktualisieren?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "Die neue Version wird heruntergeladen und gestartet, diese hier wird entfernt, sobald sie geschlossen ist.",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "{downloading} laufende und {queued} wartende Download(s) werden abgebrochen.  Halb fertige Folgen werden gelöscht und können nach dem Neustart erneut eingereiht werden.",
    "Yes": "Ja",
    "No": "Nein",
    "OK": "OK",
    "Downloading…": "Wird heruntergeladen…",
    "Update failed": "Update fehlgeschlagen",
    "Could not install the update:": "Das Update konnte nicht installiert werden:",
    "No release has been published yet.": "Es wurde noch kein Release veröffentlicht.",
    "The version file lists a newer build, but there is no release to download from.":
        "Die Versionsdatei nennt einen neueren Build, aber es gibt kein Release zum Herunterladen.",
    "The newest release has no .exe attached, so there is nothing to install.":
        "Am neuesten Release hängt keine .exe, es gibt also nichts zu installieren.",
    "The download ended early - check your connection and try again.":
        "Der Download wurde vorzeitig beendet - prüfe deine Verbindung und versuche es erneut.",
    "The download failed - check your connection and try again.":
        "Der Download ist fehlgeschlagen - prüfe deine Verbindung und versuche es erneut.",
    "Could not save the download:": "Der Download konnte nicht gespeichert werden:",
    "Could not download the update:": "Das Update konnte nicht heruntergeladen werden:",
    "Could not clear the previous build at:": "Der vorherige Build konnte nicht entfernt werden:",
    "Delete that file and try again.": "Lösche diese Datei und versuche es erneut.",
    "Could not move the current build aside:": "Der aktuelle Build konnte nicht beiseitegelegt werden:",
    "Updating needs write access to the app's folder.":
        "Zum Aktualisieren wird Schreibzugriff auf den Ordner der App benötigt.",
    "Could not install the new build:": "Der neue Build konnte nicht installiert werden:",
    "The update installed but would not start:": "Das Update wurde installiert, startet aber nicht:",
    "Start it yourself from:": "Starte es selbst von hier:",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "Das Update wurde installiert, hat sich aber direkt nach dem Start beendet (Exit-Code {code}).",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "Wird heruntergeladen ({count})",
    "Pending ({count})": "Ausstehend ({count})",
    "(retry {count}/{limit})": "(Wiederholung {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "ffmpeg nicht gefunden - installiere es, füge es deinem PATH hinzu und versuche es erneut",
    "already downloaded - skipping": "bereits heruntergeladen - wird übersprungen",
    "could not create folder {folder}: {error}": "Ordner {folder} konnte nicht erstellt werden: {error}",
    "skipped: {language} / {provider} not available": "übersprungen: {language} / {provider} nicht verfügbar",
    "Trying {combination}": "Versuche {combination}",
    "error with {provider}: {error}": "Fehler bei {provider}: {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "Alle Downloads sind fertig.",
    "The PC will shut down in {seconds} seconds.": "Der PC fährt in {seconds} Sekunden herunter.",
    "The PC will shut down in 1 second.": "Der PC fährt in 1 Sekunde herunter.",
    "Cancel shutdown": "Herunterfahren abbrechen",
    "Closing this window lets the shutdown go ahead.":
        "Schließt du dieses Fenster, fährt der PC trotzdem herunter.",
    "Could not cancel the shutdown - run {command} to stop it.":
        "Das Herunterfahren konnte nicht abgebrochen werden - führe {command} aus, um es zu stoppen.",

    # --- Series pages -------------------------------------------------------
    "From:": "Von:",
    "To:": "Bis:",
    "Fetching seasons…": "Staffeln werden geladen…",
    "No episodes found": "Keine Folgen gefunden",
    "Error: {message}": "Fehler: {message}",
    "Ep. {number} - {title}": "Folge {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "Folge {number} - {title}  (Gesamt: {overall})",
    "Movie {number} - {title}": "Film {number} - {title}",
    "Episode {number}": "Folge {number}",
    "{count} episode": "{count} Folge",
    "{count} episodes": "{count} Folgen",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "bis {quality} (hanime.tv liefert 1080p nur mit Konto)",
    "This doesn't look like a hanime.tv video link.": "Das sieht nicht nach einem hanime.tv-Videolink aus.",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "aniworld.to hat die Anfrage abgelehnt (HTTP 403) und auch der Browser-Fallback kam nicht durch",
    "Language: {names}": "Sprache: {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "Keine animepahe-Sprache aktiviert - Untertitel werden angezeigt. Wähle eine unter Einstellungen → Sprachen",
    "Only available as {languages} - switch it on in Settings → Languages":
        "Nur als {languages} verfügbar - aktiviere es unter Einstellungen → Sprachen",
    "no {language}": "{language} fehlt",
    "not on animepahe": "nicht auf animepahe",
    "animepahe does not have season {seasons}": "animepahe hat Staffel {seasons} nicht",
    "animepahe does not have seasons {seasons}": "animepahe hat die Staffeln {seasons} nicht",
    "starts at episode {number}": "beginnt bei Folge {number}",
    "missing episode {numbers}": "fehlende Folge {numbers}",
    "missing episodes {numbers}": "fehlende Folgen {numbers}",
    "+{count} more": "+{count} weitere",
    "Japanese · Sub": "Japanisch · Untertitel",

    # --- Settings -----------------------------------------------------------
    "General": "Allgemein",
    "Search bars": "Suchleisten",
    "Providers": "Anbieter",
    "Languages": "Sprachen",
    "Support": "Support",
    "App language:": "App-Sprache:",
    "Restart Aniloader to switch to this language.": "Starte Aniloader neu, um zu dieser Sprache zu wechseln.",
    "Theme:": "Design:",
    "Dark": "Dunkel",
    "Light": "Hell",
    "Neon": "Neon",
    "Neon color:": "Neonfarbe:",
    "Aqua": "Aqua",
    "Green": "Grün",
    "Pink": "Pink",
    "Purple": "Lila",
    "Orange": "Orange",
    "Yellow": "Gelb",
    "Blue": "Blau",
    "Red": "Rot",
    "White": "Weiß",
    "Max quality:": "Max. Qualität:",
    "Min quality:": "Min. Qualität:",
    "Shutdown when done": "Herunterfahren, wenn fertig",
    "ON": "AN",
    "OFF": "AUS",
    "Simultaneous DLs:": "Gleichzeitige DLs:",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "Mehr als 4 gleichzeitig können bei manchen Hostern gelegentlich die Qualität senken - 3-4 werden empfohlen.",
    "Download delay:": "Download-Verzögerung:",
    "Retries:": "Wiederholungen:",
    "Set Download Path": "Download-Pfad festlegen",
    "No path set": "Kein Pfad festgelegt",
    "Select Download Folder": "Download-Ordner auswählen",
    "Website": "Website",
    "Search bar": "Suchleiste",
    "Caching": "Cache",
    "Cache duration:": "Cache-Dauer:",
    "days": "Tage",
    "Drag to reorder  ·  click to toggle": "Ziehen zum Sortieren  ·  Klicken zum Umschalten",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "Brauchst du Hilfe, hast du einen Fehler gefunden oder eine Idee?  Melde dich auf Discord, oder finde unten den Quellcode und die neueste Version.",
    "Questions, bug reports and announcements": "Fragen, Fehlermeldungen und Ankündigungen",
    "Source code and releases": "Quellcode und Releases",
    "Official download page": "Offizielle Download-Seite",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "Japanisch · Englische Untertitel",
    "English Dub": "Englische Synchro",
    "Japanese · German Sub": "Japanisch · Deutsche Untertitel",
    "German Dub": "Deutsche Synchro",
    "Japanese · Portuguese (Brazil) Sub": "Japanisch · Portugiesische Untertitel (Brasilien)",
    "Japanese · Spanish Sub": "Japanisch · Spanische Untertitel",
    "Japanese · Spanish (Latin America) Sub": "Japanisch · Spanische Untertitel (Lateinamerika)",
    "Japanese · French Sub": "Japanisch · Französische Untertitel",
    "Japanese · Indonesian Sub": "Japanisch · Indonesische Untertitel",
    "Japanese · Thai Sub": "Japanisch · Thailändische Untertitel",
    "Japanese · Vietnamese Sub": "Japanisch · Vietnamesische Untertitel",
}
