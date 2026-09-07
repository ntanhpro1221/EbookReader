"""Va analysis.py: mot cai ten khong doc duoc thi doc nguyen van, khong giet ca cuon sach."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''                    if self.quality_profile == "high_quality":
                        raise RuntimeError(
                            "High-quality pronunciation QA could not resolve: "
                            + ", ".join(skipped_surfaces)
                        )'''

NEW = '''                    # Không ném lỗi nữa. Ba dòng trên vừa nói "TTS sẽ đọc nguyên văn", rồi
                    # dòng này giết cả lượt chạy - hai câu ấy không thể cùng đúng.
                    #
                    # Sự thận trọng thì đúng, và `_command_pronounce` đã ghi rõ vì sao: đọc
                    # sai một cái tên suốt cả cuốn còn tệ hơn để người đọc đánh vần chữ Latin.
                    # Nhưng kết luận của lập luận ấy là **đọc nguyên văn**, không phải **dừng
                    # lại**. Dừng lại chỉ đúng khi có người đứng sẵn để hỏi.
                    #
                    # alpha.57 chết lúc 03:00 vì đúng một từ: `Cred`, đơn vị tiền trong
                    # truyện, có mặt ở 24 trên 478 chương. Mười một tên khác cùng lô được cứu
                    # bằng từ điển CMU hoặc dự phòng; riêng nó có cụm phụ âm đầu `cr` không
                    # nằm trong LATIN_NAME_ONSET_READINGS nên bị coi là không đủ chắc để đoán.
                    # Một lượt chạy 1.357 segment dừng ở bước sau phân tích, và thứ duy nhất
                    # đưa nó đi tiếp được là một người gõ tay cách đọc vào.
                    #
                    # Giờ nó đi tiếp, và để lại dấu vết đọc được: sự kiện
                    # NAME_PRONUNCIATION_UNCERTAIN_SKIPPED ở trên đã mang đủ tên và lý do, nên
                    # ai muốn ghim lại bằng `pronounce` thì tra ra ngay - chứ không phải đọc
                    # traceback rồi đoán.
                    if self.quality_profile == "high_quality":
                        self.log(
                            "Hồ sơ high_quality: KHÔNG dừng vì tên chưa đọc được. "
                            f"{len(skipped_surfaces)} tên sẽ đọc nguyên văn: {skipped_surfaces}. "
                            "Ghim bằng `pronounce` nếu muốn khác."
                        )'''

assert OLD in s, "khong khop cho raise"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
