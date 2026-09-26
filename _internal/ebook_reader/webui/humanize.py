"""Chữ cho người đọc: trạng thái, giai đoạn, sự kiện của dây chuyền nói bằng tiếng Việt thường ngày.

Nguyên tắc: nói điều người dùng nhận ra được (một chương đã nghe được, một câu nên nghe lại), không nói cách hệ
thống làm (lease, critic, candidate). Sự kiện nào không có nghĩa với người nghe thì không có mặt ở đây - nó vẫn
nằm nguyên trong "Chi tiết kỹ thuật".
"""
from __future__ import annotations

import ast
import re

WORKING_PHASES = frozenset({"analysis", "casting", "synthesis"})

PROFILE_LABELS = {
    "fast": "Nhanh",
    "balanced": "Cân bằng",
    "high_quality": "Chất lượng cao",
}

CHAPTER_STATUS_LABELS = {
    "pending": "Chờ",
    "synthesizing": "Đang thu",
    "verifying": "Đang kiểm tra",
    "completed": "Nghe được",
    "failed": "Lỗi",
    "warning": "Cần xem lại",
}

GENDER_LABELS = {"male": "Nam", "female": "Nữ"}
AGE_LABELS = {
    "child": "Trẻ em",
    "teen": "Thiếu niên",
    "young": "Thanh niên",
    "adult": "Trưởng thành",
    "elderly": "Cao tuổi",
}

_STABLE_ID = re.compile(r"\bc(\d{5})_s(\d{7})_[0-9a-f]+")
_NUMERIC_TITLE = re.compile(r"^\s*0*(\d+)\s*$")


def phase_of(status: str, stage: str) -> str:
    if status == "completed" or stage in ("completed", "completed_with_errors"):
        return "done"
    if status == "error" or stage in ("unrecoverable_error", "critical_stop"):
        return "error"
    if status in ("stopped", "paused"):
        return "stopped"
    return {
        "analyzing": "analysis",
        "casting": "casting",
        "synthesizing": "synthesis",
    }.get(status, "idle")


def status_label(phase: str, stage: str, *, active: bool) -> str:
    if phase == "done":
        return "Xong, còn chương lỗi" if stage == "completed_with_errors" else "Hoàn tất"
    if phase == "error":
        return "Dừng khẩn cấp" if stage == "critical_stop" else "Gặp lỗi"
    if phase == "stopped":
        return "Đã dừng"
    if phase == "idle":
        # Worker đã chạy nhưng chưa làm câu nào (đang nạp model): "Chưa bắt đầu" cạnh nút Dừng là mâu thuẫn.
        return "Đang khởi động" if active else "Chưa bắt đầu"
    doing = {"analysis": "phân tích truyện", "casting": "phân vai", "synthesis": "thu âm"}[phase]
    return f"Đang {doing}" if active else f"Tạm ngưng lúc {doing}"


def chapter_title(title: str) -> str:
    """Tên file chương là số ("645") thì đọc thành "Chương 645"; còn lại giữ nguyên."""
    match = _NUMERIC_TITLE.match(title)
    return f"Chương {match.group(1)}" if match else title.strip()


_HEADING = re.compile(
    r"^\s*((?:chương|chapter|hồi|quyển|phần|tiết)\s*[\dIVXLC]+)\s*(?:[-:–—.·|]+\s*(.*?))?\s*$", re.IGNORECASE
)


def is_heading(text: str) -> bool:
    return len(text) <= 160 and _HEADING.match(text) is not None


def chapter_names(file_title: str, heading: str | None) -> tuple[str, str]:
    """(tên, phụ đề) của một chương cho người đọc.

    Tên file không phải tên chương: nguồn của cuốn 2 đánh số file lệch một so với truyện - file `645.txt` mở đầu
    bằng "Chương 646 - Trở về (1)". Người nghe thấy "Chương 645" trên danh sách rồi nghe đọc "Chương 646" là hai con
    số vênh nhau. Nên dòng tiêu đề trong văn bản thắng; tên file chỉ là đường lui khi chương không có tiêu đề.
    """
    if heading and len(heading) <= 160:
        match = _HEADING.match(heading)
        if match:
            name = match.group(1).strip()
            return name[:1].upper() + name[1:], (match.group(2) or "").strip()
    return chapter_title(file_title), ""


def person_name(name: str) -> str:
    """Tên chuẩn hoá của sổ nhân vật viết HOA HẾT ("VIỄN CỔ MỘC NÃI Y"); người đọc thấy "Viễn Cổ Mộc Nãi Y".
    Tên đã có chữ thường thì để nguyên - người viết sách đã chọn cách viết ấy. Vai phụ cục bộ mang nhãn nội bộ
    "NPC_LOCAL::c00006::r0b2…::người lùn": người đọc chỉ thấy "người lùn"; gạch dưới thành dấu cách."""
    if "::" in name:
        name = name.rsplit("::", 1)[-1]
    name = name.replace("_", " ").strip()
    if name != name.upper():
        return name
    words = []
    for word in name.split():
        if word in _ROMAN_NUMERALS:
            words.append(word)
        else:
            words.append("-".join(part[:1] + part[1:].lower() for part in word.split("-")))
    return " ".join(words)


_ROMAN_NUMERALS = frozenset({"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"})


def voice_tone(formant: float, pitch: float) -> str:
    """Một chữ mô tả biến thể của giọng gốc, như người nghe nhận ra nó."""
    if formant <= 0.9 or pitch <= -2.5:
        return "trầm hẳn"
    if formant <= 0.96 or pitch <= -1.5:
        return "hơi trầm"
    if formant >= 1.1 or pitch >= 2.5:
        return "sáng hẳn"
    if formant >= 1.04 or pitch >= 1.5:
        return "hơi sáng"
    return ""


def error_text(error: str) -> str:
    text = error.strip().splitlines()[0] if error.strip() else ""
    return text[:240]


def _where(message: str, chapters: dict[int, str]) -> str:
    match = _STABLE_ID.search(message)
    if not match:
        return ""
    return chapters.get(int(match.group(1)), f"chương thứ {int(match.group(1))}")


def _pronunciations(message: str) -> str:
    match = re.search(r"\{.*\}", message)
    if not match:
        return ""
    try:
        mapping = ast.literal_eval(match.group(0))
    except (ValueError, SyntaxError):
        return ""
    return ", ".join(f"{source} → {spoken}" for source, spoken in mapping.items())


def _listed_names(message: str) -> str:
    match = re.search(r"\[(.*?)\]", message)
    if not match:
        return ""
    try:
        return ", ".join(str(name) for name in ast.literal_eval(match.group(0)))
    except (ValueError, SyntaxError):
        return ""


def _mismatch(message: str, chapters: dict[int, str]) -> str:
    where = _where(message, chapters)
    return (f"Một câu ở {where} vẫn đọc lệch chữ sau khi thử lại hết lượt; đã giữ bản tốt nhất - nên nghe lại"
            if where else "")


def _short(message: str, chapters: dict[int, str]) -> str:
    where = _where(message, chapters)
    return f"Một câu rất ngắn ở {where} không tự kiểm được bằng nhận dạng giọng nói" if where else ""


def _dictionary(message: str, _chapters: dict[int, str]) -> str:
    pairs = _pronunciations(message)
    return f"Cách đọc tên lấy theo từ điển: {pairs}" if pairs else ""


def _uncertain(message: str, _chapters: dict[int, str]) -> str:
    names = _listed_names(message)
    return f"Chưa chắc cách đọc nên giữ nguyên chữ: {names}" if names else ""


def _protest(message: str, _chapters: dict[int, str]) -> str:
    match = re.search(r"(\d+) segment", message)
    count = match.group(1) if match else "Vài"
    return f"{count} câu được đọc dù AI đạo diễn chưa đồng ý cách thể hiện - nên nghe lại"


def _reconciled(message: str, _chapters: dict[int, str]) -> str:
    match = re.match(r"Hợp nhất NPC (.+?) → (.+?) \((\d+) segment\) ở chương (\d+)", message)
    if not match:
        return ""
    return f"Nhận ra “{match.group(1)}” chính là {person_name(match.group(2))} (chương thứ {match.group(4)})"


def _resumed(_message: str, _chapters: dict[int, str]) -> str:
    return "Bắt đầu chạy - đã kiểm tra lại dữ liệu cũ"


EVENT_TEXT = {
    "ASR_MISMATCH_UNRESOLVED": _mismatch,
    "NAME_PRONUNCIATION_FROM_DICTIONARY": _dictionary,
    "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED": _uncertain,
    "ANALYSIS_DIRECTOR_CRITIC_PROTESTED": _protest,
    "LOCAL_IDENTITY_RECONCILED": _reconciled,
    "RECOVERY_SCAN": _resumed,
}

_EVENT_LEVEL = {
    "ASR_MISMATCH_UNRESOLVED": "warning",
    "ANALYSIS_DIRECTOR_CRITIC_PROTESTED": "warning",
    "ASR_UNVERIFIABLE_SHORT_TEXT": "info",
    "NAME_PRONUNCIATION_FROM_DICTIONARY": "info",
    "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED": "info",
    "LOCAL_IDENTITY_RECONCILED": "info",
    "RECOVERY_SCAN": "info",
}


def event_text(code: str, message: str, chapters: dict[int, str]) -> str:
    handler = EVENT_TEXT.get(code)
    return handler(message, chapters) if handler else ""


def event_level(code: str, raw_level: str) -> str:
    return _EVENT_LEVEL.get(code, "error" if raw_level == "error" else "info")
