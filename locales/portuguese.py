"""Portuguese (Brazil) interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "Configurações",
    "Update": "Atualizar",
    "Update to {build}": "Atualizar para {build}",
    "Installed build: {build}": "Versão instalada: {build}",
    "Available build: {build}": "Versão disponível: {build}",
    "Type something...": "Digite algo...",
    "Confirm": "Confirmar",
    "Back": "Voltar",
    "Under Development": "Em desenvolvimento",
    "Invalid URL": "URL inválida",
    "No enabled providers or languages for this site": "Nenhum provedor ou idioma ativado para este site",
    "No enabled providers for this site": "Nenhum provedor ativado para este site",
    "No enabled languages for this site": "Nenhum idioma ativado para este site",
    "fetching titles: {sites}": "buscando títulos: {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "Atualizar o Aniloader",
    "Update from build {installed} to {available}?": "Atualizar da versão {installed} para a {available}?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "A nova versão é baixada e iniciada, e esta é removida assim que for fechada.",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "{downloading} download(s) em andamento e {queued} na fila serão cancelados.  Episódios baixados pela metade são excluídos e podem voltar para a fila depois de reiniciar.",
    "Yes": "Sim",
    "No": "Não",
    "OK": "OK",
    "Downloading…": "Baixando…",
    "Update failed": "Falha na atualização",
    "Could not install the update:": "Não foi possível instalar a atualização:",
    "No release has been published yet.": "Nenhuma versão foi publicada ainda.",
    "The version file lists a newer build, but there is no release to download from.":
        "O arquivo de versão indica uma versão mais nova, mas não há nenhuma publicação para baixar.",
    "The newest release has no .exe attached, so there is nothing to install.":
        "A publicação mais recente não tem um .exe anexado, então não há nada para instalar.",
    "The download ended early - check your connection and try again.":
        "O download terminou antes do fim - verifique sua conexão e tente de novo.",
    "The download failed - check your connection and try again.":
        "O download falhou - verifique sua conexão e tente de novo.",
    "Could not save the download:": "Não foi possível salvar o download:",
    "Could not download the update:": "Não foi possível baixar a atualização:",
    "Could not clear the previous build at:": "Não foi possível remover a versão anterior em:",
    "Delete that file and try again.": "Exclua esse arquivo e tente de novo.",
    "Could not move the current build aside:": "Não foi possível mover a versão atual:",
    "Updating needs write access to the app's folder.":
        "A atualização precisa de permissão de escrita na pasta do app.",
    "Could not install the new build:": "Não foi possível instalar a nova versão:",
    "The update installed but would not start:": "A atualização foi instalada, mas não inicia:",
    "Start it yourself from:": "Inicie-a manualmente a partir de:",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "A atualização foi instalada, mas fechou logo depois de iniciar (código de saída {code}).",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "Baixando ({count})",
    "Pending ({count})": "Pendentes ({count})",
    "(retry {count}/{limit})": "(nova tentativa {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "ffmpeg não encontrado - instale-o, adicione-o ao seu PATH e tente de novo",
    "already downloaded - skipping": "já baixado - pulando",
    "could not create folder {folder}: {error}": "não foi possível criar a pasta {folder}: {error}",
    "skipped: {language} / {provider} not available": "pulado: {language} / {provider} indisponível",
    "Trying {combination}": "Tentando {combination}",
    "error with {provider}: {error}": "erro com {provider}: {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "Todos os downloads foram concluídos.",
    "The PC will shut down in {seconds} seconds.": "O PC será desligado em {seconds} segundos.",
    "The PC will shut down in 1 second.": "O PC será desligado em 1 segundo.",
    "Cancel shutdown": "Cancelar desligamento",
    "Closing this window lets the shutdown go ahead.":
        "Se você fechar esta janela, o PC será desligado mesmo assim.",
    "Could not cancel the shutdown - run {command} to stop it.":
        "Não foi possível cancelar o desligamento - execute {command} para interrompê-lo.",

    # --- Series pages -------------------------------------------------------
    "From:": "De:",
    "To:": "Até:",
    "Fetching seasons…": "Buscando temporadas…",
    "No episodes found": "Nenhum episódio encontrado",
    "Error: {message}": "Erro: {message}",
    "Ep. {number} - {title}": "Ep. {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "Ep. {number} - {title}  (Geral: {overall})",
    "Movie {number} - {title}": "Filme {number} - {title}",
    "Episode {number}": "Episódio {number}",
    "{count} episode": "{count} episódio",
    "{count} episodes": "{count} episódios",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "até {quality} (o hanime.tv não oferece 1080p sem conta)",
    "This doesn't look like a hanime.tv video link.": "Isto não parece um link de vídeo do hanime.tv.",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "O aniworld.to recusou a solicitação (HTTP 403) e o navegador de reserva também não conseguiu passar",
    "Language: {names}": "Idioma: {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "Nenhum idioma do animepahe ativado - mostrando legendado. Escolha um em Configurações → Idiomas",
    "Only available as {languages} - switch it on in Settings → Languages":
        "Disponível apenas como {languages} - ative em Configurações → Idiomas",
    "no {language}": "sem {language}",
    "not on animepahe": "não está no animepahe",
    "animepahe does not have season {seasons}": "o animepahe não tem a temporada {seasons}",
    "animepahe does not have seasons {seasons}": "o animepahe não tem as temporadas {seasons}",
    "starts at episode {number}": "começa no episódio {number}",
    "missing episode {numbers}": "falta o episódio {numbers}",
    "missing episodes {numbers}": "faltam os episódios {numbers}",
    "+{count} more": "+{count} a mais",
    "Japanese · Sub": "Japonês · Legendado",

    # --- Settings -----------------------------------------------------------
    "General": "Geral",
    "Search bars": "Barras de pesquisa",
    "Providers": "Provedores",
    "Languages": "Idiomas",
    "Support": "Suporte",
    "App language:": "Idioma do app:",
    "Restart Aniloader to switch to this language.": "Reinicie o Aniloader para mudar para este idioma.",
    "Theme:": "Tema:",
    "Dark": "Escuro",
    "Light": "Claro",
    "Neon": "Neon",
    "Neon color:": "Cor neon:",
    "Aqua": "Água",
    "Green": "Verde",
    "Pink": "Rosa",
    "Purple": "Roxo",
    "Orange": "Laranja",
    "Yellow": "Amarelo",
    "Blue": "Azul",
    "Red": "Vermelho",
    "White": "Branco",
    "Max quality:": "Qualidade máx.:",
    "Min quality:": "Qualidade mín.:",
    "Shutdown when done": "Desligar ao terminar",
    "ON": "SIM",
    "OFF": "NÃO",
    "Simultaneous DLs:": "Downloads simultâneos:",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "Mais de 4 ao mesmo tempo pode reduzir a qualidade de vez em quando em alguns servidores - recomenda-se 3-4.",
    "Download delay:": "Intervalo entre downloads:",
    "Retries:": "Novas tentativas:",
    "Set Download Path": "Definir pasta de downloads",
    "No path set": "Nenhuma pasta definida",
    "Select Download Folder": "Selecionar pasta de downloads",
    "Website": "Site",
    "Search bar": "Barra de pesquisa",
    "Caching": "Cache",
    "Cache duration:": "Duração do cache:",
    "days": "dias",
    "Drag to reorder  ·  click to toggle": "Arraste para reordenar  ·  clique para alternar",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "Precisa de ajuda, encontrou um bug ou tem uma ideia?  Fale comigo no Discord, ou encontre abaixo o código-fonte e a versão mais recente.",
    "Questions, bug reports and announcements": "Dúvidas, relatos de bugs e avisos",
    "Source code and releases": "Código-fonte e versões",
    "Official download page": "Página oficial de download",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "Japonês · Legendas em inglês",
    "English Dub": "Dublagem em inglês",
    "Japanese · German Sub": "Japonês · Legendas em alemão",
    "German Dub": "Dublagem em alemão",
    "Japanese · Portuguese (Brazil) Sub": "Japonês · Legendas em português (Brasil)",
    "Japanese · Spanish Sub": "Japonês · Legendas em espanhol",
    "Japanese · Spanish (Latin America) Sub": "Japonês · Legendas em espanhol (América Latina)",
    "Japanese · French Sub": "Japonês · Legendas em francês",
    "Japanese · Indonesian Sub": "Japonês · Legendas em indonésio",
    "Japanese · Thai Sub": "Japonês · Legendas em tailandês",
    "Japanese · Vietnamese Sub": "Japonês · Legendas em vietnamita",
}
