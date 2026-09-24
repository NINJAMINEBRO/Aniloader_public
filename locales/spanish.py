"""Spanish interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "Ajustes",
    "Update": "Actualizar",
    "Update to {build}": "Actualizar a {build}",
    "Installed build: {build}": "Versión instalada: {build}",
    "Available build: {build}": "Versión disponible: {build}",
    "Type something...": "Escribe algo...",
    "Confirm": "Confirmar",
    "Back": "Atrás",
    "Under Development": "En desarrollo",
    "Invalid URL": "URL no válida",
    "No enabled providers or languages for this site": "No hay proveedores ni idiomas activados para este sitio",
    "No enabled providers for this site": "No hay proveedores activados para este sitio",
    "No enabled languages for this site": "No hay idiomas activados para este sitio",
    "fetching titles: {sites}": "obteniendo títulos: {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "Actualizar Aniloader",
    "Update from build {installed} to {available}?": "¿Actualizar de la versión {installed} a la {available}?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "La nueva versión se descarga y se inicia, y esta se elimina en cuanto se cierre.",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "Se cancelarán {downloading} descarga(s) en curso y {queued} en cola.  Los episodios a medio descargar se eliminan y se pueden volver a poner en cola tras el reinicio.",
    "Yes": "Sí",
    "No": "No",
    "OK": "Aceptar",
    "Downloading…": "Descargando…",
    "Update failed": "Error al actualizar",
    "Could not install the update:": "No se pudo instalar la actualización:",
    "No release has been published yet.": "Todavía no se ha publicado ningún lanzamiento.",
    "The version file lists a newer build, but there is no release to download from.":
        "El archivo de versión indica una versión más nueva, pero no hay ningún lanzamiento para descargar.",
    "The newest release has no .exe attached, so there is nothing to install.":
        "El último lanzamiento no incluye ningún .exe, así que no hay nada que instalar.",
    "The download ended early - check your connection and try again.":
        "La descarga terminó antes de tiempo - comprueba tu conexión y vuelve a intentarlo.",
    "The download failed - check your connection and try again.":
        "La descarga falló - comprueba tu conexión y vuelve a intentarlo.",
    "Could not save the download:": "No se pudo guardar la descarga:",
    "Could not download the update:": "No se pudo descargar la actualización:",
    "Could not clear the previous build at:": "No se pudo eliminar la versión anterior en:",
    "Delete that file and try again.": "Elimina ese archivo y vuelve a intentarlo.",
    "Could not move the current build aside:": "No se pudo apartar la versión actual:",
    "Updating needs write access to the app's folder.":
        "Para actualizar se necesita permiso de escritura en la carpeta de la app.",
    "Could not install the new build:": "No se pudo instalar la nueva versión:",
    "The update installed but would not start:": "La actualización se instaló, pero no se inicia:",
    "Start it yourself from:": "Iníciala tú mismo desde:",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "La actualización se instaló, pero se cerró justo después de iniciarse (código de salida {code}).",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "Descargando ({count})",
    "Pending ({count})": "Pendientes ({count})",
    "(retry {count}/{limit})": "(reintento {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "No se encontró ffmpeg - instálalo, añádelo a tu PATH y vuelve a intentarlo",
    "already downloaded - skipping": "ya descargado - se omite",
    "could not create folder {folder}: {error}": "no se pudo crear la carpeta {folder}: {error}",
    "skipped: {language} / {provider} not available": "omitido: {language} / {provider} no disponible",
    "Trying {combination}": "Probando {combination}",
    "error with {provider}: {error}": "error con {provider}: {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "Todas las descargas han terminado.",
    "The PC will shut down in {seconds} seconds.": "El PC se apagará en {seconds} segundos.",
    "The PC will shut down in 1 second.": "El PC se apagará en 1 segundo.",
    "Cancel shutdown": "Cancelar apagado",
    "Closing this window lets the shutdown go ahead.":
        "Si cierras esta ventana, el PC se apagará igualmente.",
    "Could not cancel the shutdown - run {command} to stop it.":
        "No se pudo cancelar el apagado - ejecuta {command} para detenerlo.",

    # --- Series pages -------------------------------------------------------
    "From:": "Desde:",
    "To:": "Hasta:",
    "Fetching seasons…": "Obteniendo temporadas…",
    "No episodes found": "No se encontraron episodios",
    "Error: {message}": "Error: {message}",
    "Ep. {number} - {title}": "Ep. {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "Ep. {number} - {title}  (Total: {overall})",
    "Movie {number} - {title}": "Película {number} - {title}",
    "Episode {number}": "Episodio {number}",
    "{count} episode": "{count} episodio",
    "{count} episodes": "{count} episodios",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "hasta {quality} (hanime.tv no ofrece 1080p sin una cuenta)",
    "This doesn't look like a hanime.tv video link.": "Esto no parece un enlace de vídeo de hanime.tv.",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "aniworld.to rechazó la solicitud (HTTP 403) y el navegador de respaldo tampoco pudo superarla",
    "Language: {names}": "Idioma: {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "Ningún idioma de animepahe activado - se muestran subtítulos. Elige uno en Ajustes → Idiomas",
    "Only available as {languages} - switch it on in Settings → Languages":
        "Solo disponible como {languages} - actívalo en Ajustes → Idiomas",
    "no {language}": "sin {language}",
    "not on animepahe": "no está en animepahe",
    "animepahe does not have season {seasons}": "animepahe no tiene la temporada {seasons}",
    "animepahe does not have seasons {seasons}": "animepahe no tiene las temporadas {seasons}",
    "starts at episode {number}": "empieza en el episodio {number}",
    "missing episode {numbers}": "falta el episodio {numbers}",
    "missing episodes {numbers}": "faltan los episodios {numbers}",
    "+{count} more": "+{count} más",
    "Japanese · Sub": "Japonés · Subtitulado",

    # --- Settings -----------------------------------------------------------
    "General": "General",
    "Search bars": "Barras de búsqueda",
    "Providers": "Proveedores",
    "Languages": "Idiomas",
    "Support": "Soporte",
    "App language:": "Idioma de la app:",
    "Restart Aniloader to switch to this language.": "Reinicia Aniloader para cambiar a este idioma.",
    "Theme:": "Tema:",
    "Dark": "Oscuro",
    "Light": "Claro",
    "Neon": "Neón",
    "Neon color:": "Color neón:",
    "Aqua": "Aguamarina",
    "Green": "Verde",
    "Pink": "Rosa",
    "Purple": "Morado",
    "Orange": "Naranja",
    "Yellow": "Amarillo",
    "Blue": "Azul",
    "Red": "Rojo",
    "White": "Blanco",
    "Max quality:": "Calidad máx.:",
    "Min quality:": "Calidad mín.:",
    "Shutdown when done": "Apagar al terminar",
    "ON": "SÍ",
    "OFF": "NO",
    "Simultaneous DLs:": "Descargas simultáneas:",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "Más de 4 a la vez puede bajar la calidad de vez en cuando en algunos servidores - se recomiendan 3-4.",
    "Download delay:": "Pausa entre descargas:",
    "Retries:": "Reintentos:",
    "Set Download Path": "Elegir carpeta de descargas",
    "No path set": "Ninguna carpeta elegida",
    "Select Download Folder": "Seleccionar carpeta de descargas",
    "Website": "Sitio web",
    "Search bar": "Barra de búsqueda",
    "Caching": "Caché",
    "Cache duration:": "Duración de la caché:",
    "days": "días",
    "Drag to reorder  ·  click to toggle": "Arrastra para ordenar  ·  haz clic para activar",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "¿Necesitas ayuda, encontraste un error o tienes una idea?  Escríbeme en Discord, o encuentra abajo el código fuente y la última versión.",
    "Questions, bug reports and announcements": "Preguntas, informes de errores y anuncios",
    "Source code and releases": "Código fuente y lanzamientos",
    "Official download page": "Página oficial de descarga",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "Japonés · Subtítulos en inglés",
    "English Dub": "Doblaje en inglés",
    "Japanese · German Sub": "Japonés · Subtítulos en alemán",
    "German Dub": "Doblaje en alemán",
    "Japanese · Portuguese (Brazil) Sub": "Japonés · Subtítulos en portugués (Brasil)",
    "Japanese · Spanish Sub": "Japonés · Subtítulos en español",
    "Japanese · Spanish (Latin America) Sub": "Japonés · Subtítulos en español (Latinoamérica)",
    "Japanese · French Sub": "Japonés · Subtítulos en francés",
    "Japanese · Indonesian Sub": "Japonés · Subtítulos en indonesio",
    "Japanese · Thai Sub": "Japonés · Subtítulos en tailandés",
    "Japanese · Vietnamese Sub": "Japonés · Subtítulos en vietnamita",
}
