"""Thai interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "การตั้งค่า",
    "Update": "อัปเดต",
    "Update to {build}": "อัปเดตเป็น {build}",
    "Installed build: {build}": "เวอร์ชันที่ติดตั้ง: {build}",
    "Available build: {build}": "เวอร์ชันใหม่: {build}",
    "Type something...": "พิมพ์อะไรสักอย่าง...",
    "Confirm": "ยืนยัน",
    "Back": "ย้อนกลับ",
    "Under Development": "อยู่ระหว่างพัฒนา",
    "Invalid URL": "URL ไม่ถูกต้อง",
    "No enabled providers or languages for this site": "ไม่มีผู้ให้บริการหรือภาษาที่เปิดใช้สำหรับเว็บนี้",
    "No enabled providers for this site": "ไม่มีผู้ให้บริการที่เปิดใช้สำหรับเว็บนี้",
    "No enabled languages for this site": "ไม่มีภาษาที่เปิดใช้สำหรับเว็บนี้",
    "fetching titles: {sites}": "กำลังดึงรายชื่อเรื่อง: {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "อัปเดต Aniloader",
    "Update from build {installed} to {available}?": "อัปเดตจากเวอร์ชัน {installed} เป็น {available} หรือไม่?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "ระบบจะดาวน์โหลดและเปิดเวอร์ชันใหม่ แล้วลบเวอร์ชันนี้ทิ้งเมื่อปิดลง",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "การดาวน์โหลดที่กำลังทำงาน {downloading} รายการ และที่รอคิว {queued} รายการจะถูกยกเลิก  ตอนที่ดาวน์โหลดไม่เสร็จจะถูกลบ และเพิ่มเข้าคิวใหม่ได้หลังรีสตาร์ต",
    "Yes": "ใช่",
    "No": "ไม่",
    "OK": "ตกลง",
    "Downloading…": "กำลังดาวน์โหลด…",
    "Update failed": "อัปเดตไม่สำเร็จ",
    "Could not install the update:": "ติดตั้งอัปเดตไม่ได้:",
    "No release has been published yet.": "ยังไม่มีเวอร์ชันที่เผยแพร่",
    "The version file lists a newer build, but there is no release to download from.":
        "ไฟล์เวอร์ชันระบุว่ามีเวอร์ชันใหม่กว่า แต่ยังไม่มีเวอร์ชันที่เผยแพร่ให้ดาวน์โหลด",
    "The newest release has no .exe attached, so there is nothing to install.":
        "เวอร์ชันล่าสุดไม่มีไฟล์ .exe แนบมา จึงไม่มีอะไรให้ติดตั้ง",
    "The download ended early - check your connection and try again.":
        "การดาวน์โหลดหยุดก่อนเสร็จ - ตรวจสอบการเชื่อมต่อแล้วลองใหม่",
    "The download failed - check your connection and try again.":
        "ดาวน์โหลดไม่สำเร็จ - ตรวจสอบการเชื่อมต่อแล้วลองใหม่",
    "Could not save the download:": "บันทึกไฟล์ที่ดาวน์โหลดไม่ได้:",
    "Could not download the update:": "ดาวน์โหลดอัปเดตไม่ได้:",
    "Could not clear the previous build at:": "ลบเวอร์ชันก่อนหน้าไม่ได้ที่:",
    "Delete that file and try again.": "ลบไฟล์นั้นแล้วลองใหม่",
    "Could not move the current build aside:": "ย้ายเวอร์ชันปัจจุบันออกไม่ได้:",
    "Updating needs write access to the app's folder.":
        "การอัปเดตต้องมีสิทธิ์เขียนในโฟลเดอร์ของแอป",
    "Could not install the new build:": "ติดตั้งเวอร์ชันใหม่ไม่ได้:",
    "The update installed but would not start:": "ติดตั้งอัปเดตแล้ว แต่เปิดไม่ขึ้น:",
    "Start it yourself from:": "เปิดด้วยตนเองได้จาก:",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "ติดตั้งอัปเดตแล้ว แต่ปิดตัวทันทีหลังเปิด (รหัสออก {code})",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "กำลังดาวน์โหลด ({count})",
    "Pending ({count})": "รอคิว ({count})",
    "(retry {count}/{limit})": "(ลองใหม่ {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "ไม่พบ ffmpeg - โปรดติดตั้งและเพิ่มลงใน PATH แล้วลองใหม่",
    "already downloaded - skipping": "ดาวน์โหลดแล้ว - ข้าม",
    "could not create folder {folder}: {error}": "สร้างโฟลเดอร์ {folder} ไม่ได้: {error}",
    "skipped: {language} / {provider} not available": "ข้าม: ไม่มี {language} / {provider}",
    "Trying {combination}": "กำลังลอง {combination}",
    "error with {provider}: {error}": "เกิดข้อผิดพลาดกับ {provider}: {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "ดาวน์โหลดเสร็จทั้งหมดแล้ว",
    "The PC will shut down in {seconds} seconds.": "คอมพิวเตอร์จะปิดในอีก {seconds} วินาที",
    "The PC will shut down in 1 second.": "คอมพิวเตอร์จะปิดในอีก 1 วินาที",
    "Cancel shutdown": "ยกเลิกการปิดเครื่อง",
    "Closing this window lets the shutdown go ahead.":
        "หากปิดหน้าต่างนี้ เครื่องจะยังคงปิดตามกำหนด",
    "Could not cancel the shutdown - run {command} to stop it.":
        "ยกเลิกการปิดเครื่องไม่ได้ - รัน {command} เพื่อหยุด",

    # --- Series pages -------------------------------------------------------
    "From:": "จาก:",
    "To:": "ถึง:",
    "Fetching seasons…": "กำลังดึงข้อมูลซีซัน…",
    "No episodes found": "ไม่พบตอน",
    "Error: {message}": "ข้อผิดพลาด: {message}",
    "Ep. {number} - {title}": "ตอนที่ {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "ตอนที่ {number} - {title}  (รวม: {overall})",
    "Movie {number} - {title}": "ภาพยนตร์ {number} - {title}",
    "Episode {number}": "ตอนที่ {number}",
    "{count} episode": "{count} ตอน",
    "{count} episodes": "{count} ตอน",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "สูงสุด {quality} (hanime.tv ไม่ให้ 1080p หากไม่มีบัญชี)",
    "This doesn't look like a hanime.tv video link.": "ลิงก์นี้ดูไม่เหมือนลิงก์วิดีโอของ hanime.tv",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "aniworld.to ปฏิเสธคำขอ (HTTP 403) และเบราว์เซอร์สำรองก็ผ่านไม่ได้เช่นกัน",
    "Language: {names}": "ภาษา: {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "ยังไม่ได้เปิดใช้ภาษาของ animepahe - กำลังแสดงแบบซับ เลือกภาษาได้ที่ การตั้งค่า → ภาษา",
    "Only available as {languages} - switch it on in Settings → Languages":
        "มีเฉพาะแบบ {languages} - เปิดใช้ได้ที่ การตั้งค่า → ภาษา",
    "no {language}": "ไม่มี{language}",
    "not on animepahe": "ไม่มีบน animepahe",
    "animepahe does not have season {seasons}": "animepahe ไม่มีซีซัน {seasons}",
    "animepahe does not have seasons {seasons}": "animepahe ไม่มีซีซัน {seasons}",
    "starts at episode {number}": "เริ่มที่ตอนที่ {number}",
    "missing episode {numbers}": "ขาดตอนที่ {numbers}",
    "missing episodes {numbers}": "ขาดตอนที่ {numbers}",
    "+{count} more": "และอีก {count} ตอน",
    "Japanese · Sub": "ญี่ปุ่น · ซับ",

    # --- Settings -----------------------------------------------------------
    "General": "ทั่วไป",
    "Search bars": "แถบค้นหา",
    "Providers": "ผู้ให้บริการ",
    "Languages": "ภาษา",
    "Support": "ช่วยเหลือ",
    "App language:": "ภาษาของแอป:",
    "Restart Aniloader to switch to this language.": "รีสตาร์ต Aniloader เพื่อเปลี่ยนเป็นภาษานี้",
    "Theme:": "ธีม:",
    "Dark": "มืด",
    "Light": "สว่าง",
    "Neon": "นีออน",
    "Neon color:": "สีนีออน:",
    "Aqua": "ฟ้าอมเขียว",
    "Green": "เขียว",
    "Pink": "ชมพู",
    "Purple": "ม่วง",
    "Orange": "ส้ม",
    "Yellow": "เหลือง",
    "Blue": "น้ำเงิน",
    "Red": "แดง",
    "White": "ขาว",
    "Max quality:": "คุณภาพสูงสุด:",
    "Min quality:": "คุณภาพต่ำสุด:",
    "Shutdown when done": "ปิดเครื่องเมื่อเสร็จ",
    "ON": "เปิด",
    "OFF": "ปิด",
    "Simultaneous DLs:": "ดาวน์โหลดพร้อมกัน:",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "ดาวน์โหลดพร้อมกันมากกว่า 4 รายการ อาจทำให้คุณภาพลดลงเป็นบางครั้งในบางโฮสต์ - แนะนำ 3-4",
    "Download delay:": "หน่วงเวลาดาวน์โหลด:",
    "Retries:": "ลองใหม่:",
    "Set Download Path": "ตั้งโฟลเดอร์ดาวน์โหลด",
    "No path set": "ยังไม่ได้ตั้งโฟลเดอร์",
    "Select Download Folder": "เลือกโฟลเดอร์ดาวน์โหลด",
    "Website": "เว็บไซต์",
    "Search bar": "แถบค้นหา",
    "Caching": "แคช",
    "Cache duration:": "ระยะเวลาแคช:",
    "days": "วัน",
    "Drag to reorder  ·  click to toggle": "ลากเพื่อจัดลำดับ  ·  คลิกเพื่อเปิด/ปิด",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "ต้องการความช่วยเหลือ เจอบั๊ก หรือมีไอเดีย?  ติดต่อได้ที่ Discord หรือดูซอร์สโค้ดและเวอร์ชันล่าสุดด้านล่าง",
    "Questions, bug reports and announcements": "คำถาม รายงานบั๊ก และประกาศ",
    "Source code and releases": "ซอร์สโค้ดและเวอร์ชันที่เผยแพร่",
    "Official download page": "หน้าดาวน์โหลดอย่างเป็นทางการ",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "ญี่ปุ่น · ซับอังกฤษ",
    "English Dub": "พากย์อังกฤษ",
    "Japanese · German Sub": "ญี่ปุ่น · ซับเยอรมัน",
    "German Dub": "พากย์เยอรมัน",
    "Japanese · Portuguese (Brazil) Sub": "ญี่ปุ่น · ซับโปรตุเกส (บราซิล)",
    "Japanese · Spanish Sub": "ญี่ปุ่น · ซับสเปน",
    "Japanese · Spanish (Latin America) Sub": "ญี่ปุ่น · ซับสเปน (ละตินอเมริกา)",
    "Japanese · French Sub": "ญี่ปุ่น · ซับฝรั่งเศส",
    "Japanese · Indonesian Sub": "ญี่ปุ่น · ซับอินโดนีเซีย",
    "Japanese · Thai Sub": "ญี่ปุ่น · ซับไทย",
    "Japanese · Vietnamese Sub": "ญี่ปุ่น · ซับเวียดนาม",
}
