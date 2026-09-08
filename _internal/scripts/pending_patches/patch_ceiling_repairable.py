"""Va pipeline.py: ban thu cham tran khung thi PHAI duoc thu lai, du ASR khong phan xu duoc."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "pipeline.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''                else:
                    inconclusive_result = aggregate_decode_failures(
                        [first_result, result]
                    )
                    last_results[segment_id] = {
                        **inconclusive_result,
                        "passed": False,
                        "verdict": ASR_INCONCLUSIVE,
                        "repairable": False,
                        "confirmation_verdicts": [first_verdict, second_verdict],
                    }
                    rejected.append(item)'''

NEW = '''                else:
                    inconclusive_result = aggregate_decode_failures(
                        [first_result, result]
                    )
                    # "Không phán xử được" thường có nghĩa là bản thu ổn mà ASR mù - câu quá
                    # ngắn, tiếng thốt - và thu lại thì cũng thế, nên không sửa là đúng.
                    #
                    # Trừ khi bộ sinh đã tự khai là nó hỏng. `generation_ceiling_hit` nghĩa là
                    # mô hình sinh cho tới khi hết khung mà chưa tự dừng, và đó là bằng chứng
                    # về BẢN THU, không phải về ASR - độc lập hoàn toàn với việc ASR có đọc
                    # được hay không.
                    #
                    # alpha.60 mất chương 026 vì đúng chỗ này. `"Gì cơ?"` - hai từ, 4 ký tự
                    # đọc - ra 1,92 giây, tức 2,1 ký tự/giây khi bình thường là ~16. Nó chạm
                    # trần, tắt tiếng êm nên `generation_endpoint_active` bằng 0, và
                    # `_ceiling_endpoint_requires_repair` đòi cả hai nên cũng bỏ qua. Phép
                    # kiểm nhịp thì không chạy vì 4 ký tự dưới ngưỡng `rate_check_min_chars`
                    # là 24. Một bản lảm nhảm 1,9 giây lọt qua mọi lưới và **không được thu
                    # lại lần nào** - `segment_candidates` rỗng.
                    #
                    # Thu lại gần như chắc chắn cứu được: `scripts/probe_frame_cap.py` sinh
                    # lại chính câu ấy ở năm trần khác nhau và bốn lần cho bản sạch 0,64-0,80
                    # giây tự kết thúc, endpoint tắt, không chạm trần. Đây là lỗi ngẫu nhiên
                    # theo seed, và gieo lại là đúng thuốc.
                    hit_ceiling = self._segment_generation_hit_ceiling(item)
                    last_results[segment_id] = {
                        **inconclusive_result,
                        "passed": False,
                        "verdict": ASR_INCONCLUSIVE,
                        "repairable": hit_ceiling,
                        "confirmation_verdicts": [first_verdict, second_verdict],
                    }
                    if hit_ceiling:
                        self.log(
                            f"Segment {item['stable_id']}: ASR không phán xử được, nhưng bản "
                            "thu chạm trần khung sinh - thu lại thay vì bỏ qua."
                        )
                        confirmed.append(item)
                    else:
                        rejected.append(item)'''

assert OLD in s, "khong khop nhanh inconclusive"
s = s.replace(OLD, NEW, 1)

HELPER = '''    @staticmethod
    def _segment_generation_hit_ceiling(row: Any) -> bool:
        """Bộ sinh có tự khai là nó chạy hết khung mà chưa dừng không?

        Khác `_ceiling_endpoint_requires_repair` ở đúng một chỗ, và chỗ ấy quan trọng: hàm kia
        đòi **cả** chạm trần **lẫn** endpoint còn to. Một bản lảm nhảm cho tới hết khung rồi
        tắt tiếng êm thì endpoint bằng 0, và nó lọt qua. Hàm này chỉ hỏi vế thứ nhất.
        """
        try:
            warning_value = row["warning_code"]
        except (IndexError, KeyError, TypeError):
            warning_value = None
        if GENERATION_CEILING_WARNING in str(warning_value or "").split("|"):
            return True
        try:
            raw_metrics = row["signal_json"]
        except (IndexError, KeyError, TypeError):
            return False
        try:
            metrics = json.loads(str(raw_metrics or "{}"))
        except (TypeError, json.JSONDecodeError):
            return False
        return isinstance(metrics, dict) and bool(metrics.get(GENERATION_CEILING_METRIC))

    @staticmethod
    def _ceiling_endpoint_requires_repair(row: Any) -> bool:'''

ANCHOR = '''    @staticmethod
    def _ceiling_endpoint_requires_repair(row: Any) -> bool:'''
assert ANCHOR in s, "khong khop cho chen helper"
s = s.replace(ANCHOR, HELPER, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
