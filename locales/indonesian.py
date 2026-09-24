"""Indonesian interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "Pengaturan",
    "Update": "Perbarui",
    "Update to {build}": "Perbarui ke {build}",
    "Installed build: {build}": "Versi terpasang: {build}",
    "Available build: {build}": "Versi tersedia: {build}",
    "Type something...": "Ketik sesuatu...",
    "Confirm": "Konfirmasi",
    "Back": "Kembali",
    "Under Development": "Dalam pengembangan",
    "Invalid URL": "URL tidak valid",
    "No enabled providers or languages for this site": "Tidak ada penyedia atau bahasa yang aktif untuk situs ini",
    "No enabled providers for this site": "Tidak ada penyedia yang aktif untuk situs ini",
    "No enabled languages for this site": "Tidak ada bahasa yang aktif untuk situs ini",
    "fetching titles: {sites}": "mengambil judul: {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "Perbarui Aniloader",
    "Update from build {installed} to {available}?": "Perbarui dari versi {installed} ke {available}?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "Versi baru akan diunduh dan dijalankan, lalu versi ini dihapus setelah ditutup.",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "{downloading} unduhan yang berjalan dan {queued} yang mengantre akan dibatalkan.  Episode yang belum selesai diunduh akan dihapus dan bisa dimasukkan ke antrean lagi setelah dimulai ulang.",
    "Yes": "Ya",
    "No": "Tidak",
    "OK": "OK",
    "Downloading…": "Mengunduh…",
    "Update failed": "Pembaruan gagal",
    "Could not install the update:": "Tidak dapat memasang pembaruan:",
    "No release has been published yet.": "Belum ada rilis yang diterbitkan.",
    "The version file lists a newer build, but there is no release to download from.":
        "File versi menyebutkan versi yang lebih baru, tetapi belum ada rilis untuk diunduh.",
    "The newest release has no .exe attached, so there is nothing to install.":
        "Rilis terbaru tidak menyertakan file .exe, jadi tidak ada yang bisa dipasang.",
    "The download ended early - check your connection and try again.":
        "Unduhan berhenti sebelum selesai - periksa koneksi Anda dan coba lagi.",
    "The download failed - check your connection and try again.":
        "Unduhan gagal - periksa koneksi Anda dan coba lagi.",
    "Could not save the download:": "Tidak dapat menyimpan unduhan:",
    "Could not download the update:": "Tidak dapat mengunduh pembaruan:",
    "Could not clear the previous build at:": "Tidak dapat menghapus versi sebelumnya di:",
    "Delete that file and try again.": "Hapus file itu dan coba lagi.",
    "Could not move the current build aside:": "Tidak dapat memindahkan versi saat ini:",
    "Updating needs write access to the app's folder.":
        "Pembaruan membutuhkan izin tulis ke folder aplikasi.",
    "Could not install the new build:": "Tidak dapat memasang versi baru:",
    "The update installed but would not start:": "Pembaruan sudah terpasang tetapi tidak mau berjalan:",
    "Start it yourself from:": "Jalankan sendiri dari:",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "Pembaruan sudah terpasang tetapi langsung berhenti setelah dijalankan (kode keluar {code}).",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "Mengunduh ({count})",
    "Pending ({count})": "Menunggu ({count})",
    "(retry {count}/{limit})": "(coba ulang {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "ffmpeg tidak ditemukan - pasang dan tambahkan ke PATH, lalu coba lagi",
    "already downloaded - skipping": "sudah diunduh - dilewati",
    "could not create folder {folder}: {error}": "tidak dapat membuat folder {folder}: {error}",
    "skipped: {language} / {provider} not available": "dilewati: {language} / {provider} tidak tersedia",
    "Trying {combination}": "Mencoba {combination}",
    "error with {provider}: {error}": "kesalahan pada {provider}: {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "Semua unduhan sudah selesai.",
    "The PC will shut down in {seconds} seconds.": "PC akan dimatikan dalam {seconds} detik.",
    "The PC will shut down in 1 second.": "PC akan dimatikan dalam 1 detik.",
    "Cancel shutdown": "Batalkan mematikan PC",
    "Closing this window lets the shutdown go ahead.":
        "Jika jendela ini ditutup, PC tetap akan dimatikan.",
    "Could not cancel the shutdown - run {command} to stop it.":
        "Tidak dapat membatalkan mematikan PC - jalankan {command} untuk menghentikannya.",

    # --- Series pages -------------------------------------------------------
    "From:": "Dari:",
    "To:": "Sampai:",
    "Fetching seasons…": "Mengambil musim…",
    "No episodes found": "Tidak ada episode yang ditemukan",
    "Error: {message}": "Kesalahan: {message}",
    "Ep. {number} - {title}": "Ep. {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "Ep. {number} - {title}  (Keseluruhan: {overall})",
    "Movie {number} - {title}": "Film {number} - {title}",
    "Episode {number}": "Episode {number}",
    "{count} episode": "{count} episode",
    "{count} episodes": "{count} episode",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "hingga {quality} (hanime.tv tidak menyediakan 1080p tanpa akun)",
    "This doesn't look like a hanime.tv video link.": "Ini sepertinya bukan tautan video hanime.tv.",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "aniworld.to menolak permintaan (HTTP 403) dan browser cadangan juga tidak bisa menembusnya",
    "Language: {names}": "Bahasa: {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "Tidak ada bahasa animepahe yang aktif - menampilkan versi subtitle. Pilih salah satu di Pengaturan → Bahasa",
    "Only available as {languages} - switch it on in Settings → Languages":
        "Hanya tersedia sebagai {languages} - aktifkan di Pengaturan → Bahasa",
    "no {language}": "tanpa {language}",
    "not on animepahe": "tidak ada di animepahe",
    "animepahe does not have season {seasons}": "animepahe tidak memiliki musim {seasons}",
    "animepahe does not have seasons {seasons}": "animepahe tidak memiliki musim {seasons}",
    "starts at episode {number}": "dimulai dari episode {number}",
    "missing episode {numbers}": "episode {numbers} tidak ada",
    "missing episodes {numbers}": "episode {numbers} tidak ada",
    "+{count} more": "+{count} lainnya",
    "Japanese · Sub": "Jepang · Subtitle",

    # --- Settings -----------------------------------------------------------
    "General": "Umum",
    "Search bars": "Bilah pencarian",
    "Providers": "Penyedia",
    "Languages": "Bahasa",
    "Support": "Dukungan",
    "App language:": "Bahasa aplikasi:",
    "Restart Aniloader to switch to this language.": "Mulai ulang Aniloader untuk beralih ke bahasa ini.",
    "Theme:": "Tema:",
    "Dark": "Gelap",
    "Light": "Terang",
    "Neon": "Neon",
    "Neon color:": "Warna neon:",
    "Aqua": "Aqua",
    "Green": "Hijau",
    "Pink": "Merah muda",
    "Purple": "Ungu",
    "Orange": "Oranye",
    "Yellow": "Kuning",
    "Blue": "Biru",
    "Red": "Merah",
    "White": "Putih",
    "Max quality:": "Kualitas maks.:",
    "Min quality:": "Kualitas min.:",
    "Shutdown when done": "Matikan PC setelah selesai",
    "ON": "AKTIF",
    "OFF": "MATI",
    "Simultaneous DLs:": "Unduhan bersamaan:",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "Lebih dari 4 sekaligus kadang menurunkan kualitas di beberapa host - disarankan 3-4.",
    "Download delay:": "Jeda unduhan:",
    "Retries:": "Coba ulang:",
    "Set Download Path": "Atur folder unduhan",
    "No path set": "Belum ada folder",
    "Select Download Folder": "Pilih folder unduhan",
    "Website": "Situs",
    "Search bar": "Bilah pencarian",
    "Caching": "Cache",
    "Cache duration:": "Durasi cache:",
    "days": "hari",
    "Drag to reorder  ·  click to toggle": "Seret untuk mengurutkan  ·  klik untuk mengaktifkan",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "Butuh bantuan, menemukan bug, atau punya ide?  Hubungi saya di Discord, atau temukan kode sumber dan versi terbaru di bawah.",
    "Questions, bug reports and announcements": "Pertanyaan, laporan bug, dan pengumuman",
    "Source code and releases": "Kode sumber dan rilis",
    "Official download page": "Halaman unduhan resmi",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "Jepang · Subtitle Inggris",
    "English Dub": "Sulih Suara Inggris",
    "Japanese · German Sub": "Jepang · Subtitle Jerman",
    "German Dub": "Sulih Suara Jerman",
    "Japanese · Portuguese (Brazil) Sub": "Jepang · Subtitle Portugis (Brasil)",
    "Japanese · Spanish Sub": "Jepang · Subtitle Spanyol",
    "Japanese · Spanish (Latin America) Sub": "Jepang · Subtitle Spanyol (Amerika Latin)",
    "Japanese · French Sub": "Jepang · Subtitle Prancis",
    "Japanese · Indonesian Sub": "Jepang · Subtitle Indonesia",
    "Japanese · Thai Sub": "Jepang · Subtitle Thailand",
    "Japanese · Vietnamese Sub": "Jepang · Subtitle Vietnam",
}
