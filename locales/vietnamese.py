"""Vietnamese interface texts - see i18n.py for how they are used."""

TRANSLATIONS: dict[str, str] = {
    # --- Main window --------------------------------------------------------
    "Settings": "Cài đặt",
    "Update": "Cập nhật",
    "Update to {build}": "Cập nhật lên {build}",
    "Installed build: {build}": "Bản đã cài: {build}",
    "Available build: {build}": "Bản mới có: {build}",
    "Type something...": "Nhập gì đó...",
    "Confirm": "Xác nhận",
    "Back": "Quay lại",
    "Under Development": "Đang phát triển",
    "Invalid URL": "URL không hợp lệ",
    "No enabled providers or languages for this site": "Không có nhà cung cấp hay ngôn ngữ nào được bật cho trang này",
    "No enabled providers for this site": "Không có nhà cung cấp nào được bật cho trang này",
    "No enabled languages for this site": "Không có ngôn ngữ nào được bật cho trang này",
    "fetching titles: {sites}": "đang tải danh sách phim: {sites}",

    # --- Updating -----------------------------------------------------------
    "Update Aniloader": "Cập nhật Aniloader",
    "Update from build {installed} to {available}?": "Cập nhật từ bản {installed} lên bản {available}?",
    "The new version is downloaded and started, and this one is removed once it has closed.":
        "Phiên bản mới sẽ được tải về và khởi chạy, còn bản này sẽ bị xóa sau khi đóng.",
    "{downloading} download(s) in progress and {queued} queued will be cancelled.  Part-finished episodes are deleted and can be queued again after the restart.":
        "{downloading} lượt tải đang chạy và {queued} lượt trong hàng chờ sẽ bị hủy.  Các tập tải dở sẽ bị xóa và có thể thêm lại vào hàng chờ sau khi khởi động lại.",
    "Yes": "Có",
    "No": "Không",
    "OK": "OK",
    "Downloading…": "Đang tải…",
    "Update failed": "Cập nhật thất bại",
    "Could not install the update:": "Không thể cài đặt bản cập nhật:",
    "No release has been published yet.": "Chưa có bản phát hành nào.",
    "The version file lists a newer build, but there is no release to download from.":
        "Tệp phiên bản báo có bản mới hơn, nhưng chưa có bản phát hành nào để tải.",
    "The newest release has no .exe attached, so there is nothing to install.":
        "Bản phát hành mới nhất không kèm tệp .exe, nên không có gì để cài đặt.",
    "The download ended early - check your connection and try again.":
        "Quá trình tải bị dừng giữa chừng - hãy kiểm tra kết nối và thử lại.",
    "The download failed - check your connection and try again.":
        "Tải xuống thất bại - hãy kiểm tra kết nối và thử lại.",
    "Could not save the download:": "Không thể lưu tệp đã tải:",
    "Could not download the update:": "Không thể tải bản cập nhật:",
    "Could not clear the previous build at:": "Không thể xóa bản trước đó tại:",
    "Delete that file and try again.": "Hãy xóa tệp đó và thử lại.",
    "Could not move the current build aside:": "Không thể di chuyển bản hiện tại sang chỗ khác:",
    "Updating needs write access to the app's folder.":
        "Cần quyền ghi vào thư mục của ứng dụng để cập nhật.",
    "Could not install the new build:": "Không thể cài đặt bản mới:",
    "The update installed but would not start:": "Bản cập nhật đã được cài nhưng không khởi động được:",
    "Start it yourself from:": "Hãy tự khởi chạy từ:",
    "The update installed but stopped immediately after starting (exit code {code}).":
        "Bản cập nhật đã được cài nhưng tắt ngay sau khi khởi động (mã thoát {code}).",

    # --- Download panels ----------------------------------------------------
    "Downloading ({count})": "Đang tải ({count})",
    "Pending ({count})": "Đang chờ ({count})",
    "(retry {count}/{limit})": "(thử lại {count}/{limit})",
    "ffmpeg not found - install it and add it to your PATH, then retry":
        "Không tìm thấy ffmpeg - hãy cài đặt, thêm vào PATH rồi thử lại",
    "already downloaded - skipping": "đã tải rồi - bỏ qua",
    "could not create folder {folder}: {error}": "không thể tạo thư mục {folder}: {error}",
    "skipped: {language} / {provider} not available": "bỏ qua: {language} / {provider} không khả dụng",
    "Trying {combination}": "Đang thử {combination}",
    "error with {provider}: {error}": "lỗi với {provider}: {error}",

    # --- Shutdown warning ---------------------------------------------------
    "All downloads are finished.": "Tất cả lượt tải đã xong.",
    "The PC will shut down in {seconds} seconds.": "Máy tính sẽ tắt sau {seconds} giây.",
    "The PC will shut down in 1 second.": "Máy tính sẽ tắt sau 1 giây.",
    "Cancel shutdown": "Hủy tắt máy",
    "Closing this window lets the shutdown go ahead.": "Nếu đóng cửa sổ này, máy tính vẫn sẽ tắt.",
    "Could not cancel the shutdown - run {command} to stop it.":
        "Không thể hủy tắt máy - hãy chạy {command} để dừng lại.",

    # --- Series pages -------------------------------------------------------
    "From:": "Từ:",
    "To:": "Đến:",
    "Fetching seasons…": "Đang tải các mùa…",
    "No episodes found": "Không tìm thấy tập nào",
    "Error: {message}": "Lỗi: {message}",
    "Ep. {number} - {title}": "Tập {number} - {title}",
    "Ep. {number} - {title}  (Overall: {overall})": "Tập {number} - {title}  (Tổng: {overall})",
    "Movie {number} - {title}": "Phim {number} - {title}",
    "Episode {number}": "Tập {number}",
    "{count} episode": "{count} tập",
    "{count} episodes": "{count} tập",
    "up to {quality} (hanime.tv doesn't serve 1080p without an account)":
        "tối đa {quality} (hanime.tv không cung cấp 1080p nếu không có tài khoản)",
    "This doesn't look like a hanime.tv video link.": "Đây có vẻ không phải là liên kết video của hanime.tv.",
    "aniworld.to refused the request (HTTP 403) and the browser fallback could not get past it either":
        "aniworld.to đã từ chối yêu cầu (HTTP 403) và trình duyệt dự phòng cũng không vượt qua được",
    "Language: {names}": "Ngôn ngữ: {names}",
    "No animepahe language enabled - showing subtitles. Pick one in Settings → Languages":
        "Chưa bật ngôn ngữ nào của animepahe - đang hiển thị bản phụ đề. Hãy chọn một trong Cài đặt → Ngôn ngữ",
    "Only available as {languages} - switch it on in Settings → Languages":
        "Chỉ có bản {languages} - hãy bật trong Cài đặt → Ngôn ngữ",
    "no {language}": "không có {language}",
    "not on animepahe": "không có trên animepahe",
    "animepahe does not have season {seasons}": "animepahe không có mùa {seasons}",
    "animepahe does not have seasons {seasons}": "animepahe không có các mùa {seasons}",
    "starts at episode {number}": "bắt đầu từ tập {number}",
    "missing episode {numbers}": "thiếu tập {numbers}",
    "missing episodes {numbers}": "thiếu các tập {numbers}",
    "+{count} more": "+{count} tập khác",
    "Japanese · Sub": "Tiếng Nhật · Phụ đề",

    # --- Settings -----------------------------------------------------------
    "General": "Chung",
    "Search bars": "Thanh tìm kiếm",
    "Providers": "Nhà cung cấp",
    "Languages": "Ngôn ngữ",
    "Support": "Hỗ trợ",
    "App language:": "Ngôn ngữ ứng dụng:",
    "Restart Aniloader to switch to this language.": "Khởi động lại Aniloader để chuyển sang ngôn ngữ này.",
    "Theme:": "Giao diện:",
    "Dark": "Tối",
    "Light": "Sáng",
    "Neon": "Neon",
    "Neon color:": "Màu neon:",
    "Aqua": "Xanh ngọc",
    "Green": "Xanh lá",
    "Pink": "Hồng",
    "Purple": "Tím",
    "Orange": "Cam",
    "Yellow": "Vàng",
    "Blue": "Xanh dương",
    "Red": "Đỏ",
    "White": "Trắng",
    "Max quality:": "Chất lượng tối đa:",
    "Min quality:": "Chất lượng tối thiểu:",
    "Shutdown when done": "Tắt máy khi xong",
    "ON": "BẬT",
    "OFF": "TẮT",
    "Simultaneous DLs:": "Tải cùng lúc:",
    "More than 4 at once can cause occasional quality drops on some hosts - 3-4 is recommended.":
        "Tải hơn 4 tập cùng lúc đôi khi làm giảm chất lượng trên một số máy chủ - nên để 3-4.",
    "Download delay:": "Độ trễ giữa các lượt tải:",
    "Retries:": "Số lần thử lại:",
    "Set Download Path": "Chọn thư mục tải xuống",
    "No path set": "Chưa chọn thư mục",
    "Select Download Folder": "Chọn thư mục tải xuống",
    "Website": "Trang web",
    "Search bar": "Thanh tìm kiếm",
    "Caching": "Bộ nhớ đệm",
    "Cache duration:": "Thời hạn bộ nhớ đệm:",
    "days": "ngày",
    "Drag to reorder  ·  click to toggle": "Kéo để sắp xếp  ·  nhấn để bật/tắt",
    "Need help, found a bug or have an idea?  Get in touch on Discord, or find the source code and the latest version below.":
        "Cần trợ giúp, phát hiện lỗi hay có ý tưởng?  Hãy liên hệ trên Discord, hoặc xem mã nguồn và phiên bản mới nhất bên dưới.",
    "Questions, bug reports and announcements": "Hỏi đáp, báo lỗi và thông báo",
    "Source code and releases": "Mã nguồn và các bản phát hành",
    "Official download page": "Trang tải xuống chính thức",

    # --- Download languages (Settings → Languages, download progress) -------
    "Japanese · English Sub": "Tiếng Nhật · Phụ đề tiếng Anh",
    "English Dub": "Lồng tiếng Anh",
    "Japanese · German Sub": "Tiếng Nhật · Phụ đề tiếng Đức",
    "German Dub": "Lồng tiếng Đức",
    "Japanese · Portuguese (Brazil) Sub": "Tiếng Nhật · Phụ đề tiếng Bồ Đào Nha (Brazil)",
    "Japanese · Spanish Sub": "Tiếng Nhật · Phụ đề tiếng Tây Ban Nha",
    "Japanese · Spanish (Latin America) Sub": "Tiếng Nhật · Phụ đề tiếng Tây Ban Nha (Mỹ Latinh)",
    "Japanese · French Sub": "Tiếng Nhật · Phụ đề tiếng Pháp",
    "Japanese · Indonesian Sub": "Tiếng Nhật · Phụ đề tiếng Indonesia",
    "Japanese · Thai Sub": "Tiếng Nhật · Phụ đề tiếng Thái",
    "Japanese · Vietnamese Sub": "Tiếng Nhật · Phụ đề tiếng Việt",
}
