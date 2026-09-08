"""Va config.py: cong tat phai la bool that, khong phai bat ky thu gi truthy."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "config.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    if asr.get("required") and asr.get("failure_policy") != "fail":
        raise ValueError("Required ASR must use failure_policy=fail")'''
NEW = '''    if asr.get("required") and asr.get("failure_policy") != "fail":
        raise ValueError("Required ASR must use failure_policy=fail")
    # Kiểu, không chỉ giá trị. Đây là công tắc an toàn duy nhất của cơ chế tự cho qua, và
    # `"ship_without_a_listener": "false"` viết tay trong JSON là một chuỗi - truthy - nên
    # nó sẽ **bật** cái người ta vừa cố tắt, im lặng. Một công tắc chỉ tắt được khi gõ đúng
    # kiểu thì không phải công tắc.
    if not isinstance(asr.get("ship_without_a_listener", True), bool):
        raise ValueError("asr.ship_without_a_listener must be a boolean")'''

assert OLD in s, "khong khop cho chen kiem kieu"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
