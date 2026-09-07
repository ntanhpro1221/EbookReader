"""Va audio_io.py: dem ky tu NHU GIONG DOC PHAT RA, khong phai nhu chu viet."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "audio_io.py"
s = io.open(p, encoding="utf-8").read()

OLD_IMPORT = "from .io_utils import atomic_write_text, ffmpeg_executable, run_hidden, sha256_file"
NEW_IMPORT = (
    "from .io_utils import atomic_write_text, ffmpeg_executable, run_hidden, sha256_file\n"
    "from .text_processing import vietnamese_number_words"
)
assert OLD_IMPORT in s, "khong khop import"
s = s.replace(OLD_IMPORT, NEW_IMPORT, 1)

HELPER = '''

_DIGIT_RUN = re.compile(r"\\d+")


def spoken_speakable_chars(text: str) -> int:
    """Ký tự đọc được, đếm như **giọng đọc phát ra**, không phải như chữ viết.

    VieNeu đọc `22` thành "hai mươi hai": hai ký tự viết, mười một ký tự nói. Đếm chuỗi viết
    làm mọi văn bản có chữ số trông chậm hơn thực tế, và phép kiểm nhịp thì so với một sàn
    tính trên văn bản không có số.

    alpha.57 mất tiêu đề chương 023 vì đúng chuyện đó: `Chương 22 - 22: Ấn tượng đầu tiên` là
    24 ký tự viết và 40 ký tự đọc, nên ở 2,25 giây nó đo ra 10,68 kt/s (dưới sàn 12,5) trong
    khi tai người nghe 17,78 kt/s (giữa dải). Mười một lần thử, mười một lần cùng con số -
    không phải xui mà là số học. Chương mất tiêu đề thì không xuất bản được.

    `asr.py` đã gọi `vietnamese_number_words` từ lâu, vì so bản ghi với văn bản cũng đòi nở số
    ra chữ trước. Đây là cùng một sự thật, áp cho phép đo nhịp.

    **Giới hạn còn lại, cố ý không lấp bằng phỏng đoán:** `vietnamese_number_words` chỉ nở tới
    999 và ném lỗi trên số lớn hơn. Số từ 1000 trở lên vẫn được đếm theo chữ viết, tức vẫn bị
    tính thiếu. Bịa một hệ số ước cho chúng sẽ là đoán, và đoán chính là thứ đã tạo ra lỗi này.
    """
    def expand(match: "re.Match[str]") -> str:
        try:
            return vietnamese_number_words(int(match.group()))
        except (ValueError, OverflowError):
            return match.group()

    return sum(char.isalnum() for char in _DIGIT_RUN.sub(expand, text))
'''

ANCHOR = "def is_short_utterance(text: str) -> bool:"
assert ANCHOR in s, "khong khop cho chen ham"
s = s.replace(ANCHOR, HELPER.strip("\n") + "\n\n\n" + ANCHOR, 1)

OLD_POLICY = "    speakable_chars = max(1, sum(char.isalnum() for char in text))"
NEW_POLICY = "    speakable_chars = max(1, spoken_speakable_chars(text))"
assert OLD_POLICY in s, "khong khop segment_duration_policy"
s = s.replace(OLD_POLICY, NEW_POLICY, 1)

OLD_RATE = """    speakable_chars = sum(char.isalnum() for char in text)
    if (
        segment is not None
        and speakable_chars >= int(settings["tts"].get("rate_check_min_chars", 24))
    ):"""
NEW_RATE = """    speakable_chars = spoken_speakable_chars(text)
    if (
        segment is not None
        and speakable_chars >= int(settings["tts"].get("rate_check_min_chars", 24))
    ):"""
assert OLD_RATE in s, "khong khop phep kiem nhip"
s = s.replace(OLD_RATE, NEW_RATE, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
