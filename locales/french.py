"""French interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "Paramètres",
    "Update": "Mise à jour",
    "Update to {build}": "Mettre à jour vers {build}",
    "Installed build: {build}": "Version installée : {build}",
    "Available build: {build}": "Version disponible : {build}",
    "Type something...": "Tapez quelque chose...",
    "Confirm": "Confirmer",
    "Back": "Retour",
    "Under Development": "En développement",
    "Invalid URL": "URL invalide",
    "No enabled providers or languages for this site": "Aucun fournisseur ni aucune langue activés pour ce site",
    "No enabled providers for this site": "Aucun fournisseur activé pour ce site",
    "No enabled languages for this site": "Aucune langue activée pour ce site",
    "fetching titles: {sites}": "récupération des titres : {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "Mettre à jour Aniloader",
    "Update from build {installed} to {available}?": "Passer de la version {installed} à la version {available} ?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "La nouvelle version est téléchargée et lancée, et celle-ci est supprimée une fois fermée.",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "{downloading} téléchargement(s) en cours et {queued} en attente seront annulés.  Les épisodes à moitié téléchargés sont supprimés et pourront être remis en file d'attente après le redémarrage.",
    "Yes": "Oui",
    "No": "Non",
    "OK": "OK",
    "Downloading…": "Téléchargement…",
    "Update failed": "Échec de la mise à jour",
    "Could not install the update:": "Impossible d'installer la mise à jour :",
    "No release has been published yet.": "Aucune version n'a encore été publiée.",
    "The version file lists a newer build, but there is no release to download from.":
        "Le fichier de version indique une version plus récente, mais aucune publication n'est disponible au téléchargement.",
    "The newest release has no .exe attached, so there is nothing to install.":
        "La dernière publication ne contient pas de .exe, il n'y a donc rien à installer.",
    "The download ended early - check your connection and try again.":
        "Le téléchargement s'est arrêté trop tôt - vérifiez votre connexion et réessayez.",
    "The download failed - check your connection and try again.":
        "Le téléchargement a échoué - vérifiez votre connexion et réessayez.",
    "Could not save the download:": "Impossible d'enregistrer le téléchargement :",
    "Could not download the update:": "Impossible de télécharger la mise à jour :",
    "Could not clear the previous build at:": "Impossible de supprimer la version précédente :",
    "Delete that file and try again.": "Supprimez ce fichier et réessayez.",
    "Could not move the current build aside:": "Impossible de mettre de côté la version actuelle :",
    "Updating needs write access to the app's folder.":
        "La mise à jour nécessite un accès en écriture au dossier de l'application.",
    "Could not install the new build:": "Impossible d'installer la nouvelle version :",
    "The update installed but would not start:": "La mise à jour est installée mais ne démarre pas :",
    "Start it yourself from:": "Lancez-la vous-même depuis :",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "La mise à jour est installée mais s'est arrêtée juste après le démarrage (code de sortie {code}).",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "En téléchargement ({count})",
    "Pending ({count})": "En attente ({count})",
    "(retry {count}/{limit})": "(nouvel essai {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "ffmpeg introuvable - installez-le, ajoutez-le à votre PATH, puis réessayez",
    "already downloaded - skipping": "déjà téléchargé - ignoré",
    "could not create folder {folder}: {error}": "impossible de créer le dossier {folder} : {error}",
    "skipped: {language} / {provider} not available": "ignoré : {language} / {provider} non disponible",
    "Trying {combination}": "Essai : {combination}",
    "error with {provider}: {error}": "erreur avec {provider} : {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "Tous les téléchargements sont terminés.",
    "The PC will shut down in {seconds} seconds.": "Le PC va s'éteindre dans {seconds} secondes.",
    "The PC will shut down in 1 second.": "Le PC va s'éteindre dans 1 seconde.",
    "Cancel shutdown": "Annuler l'arrêt",
    "Closing this window lets the shutdown go ahead.":
        "Si vous fermez cette fenêtre, le PC s'éteindra quand même.",
    "Could not cancel the shutdown - run {command} to stop it.":
        "Impossible d'annuler l'arrêt - exécutez {command} pour l'annuler.",

    # --- Series pages -------------------------------------------------------
    "From:": "De :",
    "To:": "À :",
    "Fetching seasons…": "Récupération des saisons…",
    "No episodes found": "Aucun épisode trouvé",
    "Error: {message}": "Erreur : {message}",
    "Ep. {number} - {title}": "Ép. {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "Ép. {number} - {title}  (Total : {overall})",
    "Movie {number} - {title}": "Film {number} - {title}",
    "Episode {number}": "Épisode {number}",
    "{count} episode": "{count} épisode",
    "{count} episodes": "{count} épisodes",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "jusqu'à {quality} (hanime.tv ne fournit pas le 1080p sans compte)",
    "This doesn't look like a hanime.tv video link.": "Ceci ne ressemble pas à un lien vidéo hanime.tv.",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "aniworld.to a refusé la requête (HTTP 403) et le navigateur de secours n'a pas pu passer non plus",
    "Language: {names}": "Langue : {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "Aucune langue animepahe activée - affichage en sous-titré. Choisissez-en une dans Paramètres → Langues",
    "Only available as {languages} - switch it on in Settings → Languages":
        "Disponible uniquement en {languages} - activez-la dans Paramètres → Langues",
    "no {language}": "sans {language}",
    "not on animepahe": "pas sur animepahe",
    "animepahe does not have season {seasons}": "animepahe n'a pas la saison {seasons}",
    "animepahe does not have seasons {seasons}": "animepahe n'a pas les saisons {seasons}",
    "starts at episode {number}": "commence à l'épisode {number}",
    "missing episode {numbers}": "épisode manquant {numbers}",
    "missing episodes {numbers}": "épisodes manquants {numbers}",
    "+{count} more": "+{count} autres",
    "Japanese · Sub": "Japonais · Sous-titré",

    # --- Settings -----------------------------------------------------------
    "General": "Général",
    "Search bars": "Barres de recherche",
    "Providers": "Fournisseurs",
    "Languages": "Langues",
    "Support": "Assistance",
    "App language:": "Langue de l'app :",
    "Restart Aniloader to switch to this language.": "Redémarrez Aniloader pour passer à cette langue.",
    "Theme:": "Thème :",
    "Dark": "Sombre",
    "Light": "Clair",
    "Neon": "Néon",
    "Neon color:": "Couleur néon :",
    "Aqua": "Aqua",
    "Green": "Vert",
    "Pink": "Rose",
    "Purple": "Violet",
    "Orange": "Orange",
    "Yellow": "Jaune",
    "Blue": "Bleu",
    "Red": "Rouge",
    "White": "Blanc",
    "Max quality:": "Qualité max. :",
    "Min quality:": "Qualité min. :",
    "Shutdown when done": "Éteindre une fois terminé",
    "ON": "OUI",
    "OFF": "NON",
    "Simultaneous DLs:": "Téléch. simultanés :",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "Plus de 4 à la fois peut parfois faire baisser la qualité chez certains hébergeurs - 3-4 est recommandé.",
    "Download delay:": "Délai entre téléch. :",
    "Retries:": "Nouvelles tentatives :",
    "Set Download Path": "Choisir le dossier de téléchargement",
    "No path set": "Aucun dossier choisi",
    "Select Download Folder": "Choisir le dossier de téléchargement",
    "Website": "Site",
    "Search bar": "Barre de recherche",
    "Caching": "Cache",
    "Cache duration:": "Durée du cache :",
    "days": "jours",
    "Drag to reorder  ·  click to toggle": "Glissez pour réordonner  ·  cliquez pour activer",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "Besoin d'aide, un bug à signaler ou une idée ?  Contactez-moi sur Discord, ou trouvez ci-dessous le code source et la dernière version.",
    "Questions, bug reports and announcements": "Questions, rapports de bugs et annonces",
    "Source code and releases": "Code source et versions",
    "Official download page": "Page de téléchargement officielle",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "Japonais · Sous-titres anglais",
    "English Dub": "Doublage anglais",
    "Japanese · German Sub": "Japonais · Sous-titres allemands",
    "German Dub": "Doublage allemand",
    "Japanese · Portuguese (Brazil) Sub": "Japonais · Sous-titres portugais (Brésil)",
    "Japanese · Spanish Sub": "Japonais · Sous-titres espagnols",
    "Japanese · Spanish (Latin America) Sub": "Japonais · Sous-titres espagnols (Amérique latine)",
    "Japanese · French Sub": "Japonais · Sous-titres français",
    "Japanese · Indonesian Sub": "Japonais · Sous-titres indonésiens",
    "Japanese · Thai Sub": "Japonais · Sous-titres thaïs",
    "Japanese · Vietnamese Sub": "Japonais · Sous-titres vietnamiens",
}
