r"""Áp toàn bộ bản vá đang chờ, đúng thứ tự, rồi chạy bộ test đầy đủ.

    python scripts/pending_patches/apply_all.py                 # thử, không ghi gì
    python scripts/pending_patches/apply_all.py --apply         # ghi thật rồi chạy test

**CHỈ CHẠY KHI KHÔNG CÓ LƯỢT `run` NÀO ĐANG BAY.** Bản vá trong `ORDER` sửa file nằm trong
`QUALITY_IMPLEMENTATION_FILES`, nên ghi vào chúng đổi `quality_implementation_hash()` và lượt
`resume` kế tiếp sẽ bị từ chối. Script tự kiểm điều này trước khi ghi, bằng nhịp tim của
`worker_leases` chứ không bằng file khoá.

`ORDER` là hàng chờ; `APPLIED` là hồ sơ những cái đã vào cây thật. Mỗi script `assert` chuỗi
gốc trước khi thay, nên áp sai thứ tự hay áp hai lần thì nó dừng chứ không làm hỏng file — đó
là lý do giữ lại `APPLIED` thay vì xoá.
"""
from __future__ import annotations

import argparse
import ast
import sqlite3
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VERSIONS = Path(r"D:\Novels\Audiobooks\_versions")
LEASE_STALE_SECONDS = 180.0

# Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.
ORDER: tuple[str, ...] = ("patch_two_pins_do_not_share_a_chapter.py",)

APPLIED = (
    "patch_reserve_all.py",
    "patch_reserve_test.py",
    "patch_name_no_halt.py",
    "patch_name_no_halt_test.py",
    "patch_pace_digits.py",
    "patch_pace_digits_test.py",
    "patch_ck_fold.py",
    "patch_ck_fold_test.py",
    "patch_ceiling_repairable.py",
    "patch_ceiling_repairable_test.py",
    "patch_quote_recovery.py",
    "patch_quote_tests.py",
    "patch_test2.py",
    "patch_short_anchor.py",
    "patch_anchor_test.py",
    "patch_laugh.py",
    "patch_known_carry.py",
    "patch_fakedb.py",
    # Cơ chế xuất bản khi không có ai để hỏi, 2026-09-08 12:2x. Bốn cái này là **một** thay
    # đổi và phải áp cùng nhau: bảng ở `_db`, cổng ở `_pipeline`, công tắc và cổng thứ sáu ở
    # `_wiring`, con số cho báo cáo ở `_report`. Áp thiếu `_wiring` thì bản quét recovery
    # không biết bảng mới và sẽ đánh hỏng lại đúng những đoạn vừa được cho qua.
    "patch_machine_accept_db.py",
    "patch_machine_accept_pipeline.py",
    "patch_machine_accept_wiring.py",
    "patch_machine_accept_report.py",
    # 2026-09-08 17:5x, tại ranh giới alpha.62 / lô 1.
    #
    # `patch_pin_voice_model` phải viết lại một lần: bản đầu nhét model giọng vào
    # `perceptual_cache_check` và `test_perceptual_cache_marker_requires_locked_revision_and_
    # checkpoint_hash` bắt ngay. Test ấy đúng - hàm kia đăng ký là `model:utmosv2_cache`, nên
    # thiếu ghim TTS sẽ báo thành lỗi perceptual. Bản sau có `voice_model_check` riêng.
    "patch_pin_voice_model.py",
    "patch_strip_zero_width.py",
    # 2026-09-08 19:4x, sau khi lô 1 chết ở đoạn 1.406/3.727 vì một nửa cặp surrogate lạc.
    "patch_lone_surrogate.py",
    # 2026-09-09 ~05:00, tại ranh giới lô 1 / lô vá. Năm cái này ra đời từ bốn kiểu hỏng thật
    # của lô 1, và bộ test bắt được HAI chỗ tôi đè lên quyết định cố ý của người trước:
    #
    #   - `patch_pace_relaxed_is_a_decision` ban đầu đưa `TTS_PACE_BAND_RELAXED` vào
    #     HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS. `test_the_warning_blocks_publication_so_a_
    #     person_hears_it` đỏ, và nó đúng: làm thế là biến mã ấy thành IM LẶNG, vứt mất tín
    #     hiệu "nên có người nghe". Sửa lại: cho vào MACHINE_ACCEPTABLE (có ghi sổ) thay vì
    #     ALLOWED (im lặng).
    #   - `patch_casting_gate_no_halt` làm `test_gender_conflict_fails_before_voice_casting`
    #     đỏ. Test ấy viết lại kèm lý do và cái giá, không xoá.
    "patch_asr_surrogate.py",
    "patch_casting_gate_no_halt.py",
    "patch_loudness_review_ships.py",
    "patch_pace_relaxed_is_a_decision.py",
    "patch_edge_fade.py",
    # 2026-09-09 ~10:50, tại ranh giới lô vá / lô 2. Hai bản vá **tài nguyên**, không phải chất
    # lượng — chúng không đổi một mẫu audio nào, chỉ đổi việc máy có chạy hay không và ai được
    # cấp giọng nào.
    #
    #   - `patch_pool_counts_its_own_ram`: pool TTS định cỡ chỉ theo VRAM. Đo giữa chương 007
    #     của lô vá: RAM trống 2,85 GB dưới sàn 3,5 GB, pool tự giữ 7,63 GB, GPU 0% và 4,6 W
    #     hơn nửa giờ với nhịp tim vẫn sống. Worker thứ ba là thứ làm cho không worker nào chạy
    #     được. Hằng số 2,65 GB không phải số mới: theo dõi đỉnh RSS 25 phút bắt được 14 worker
    #     TTS ở 2,68 cực đại / 2,57 trung vị, gần trùng phân bố worker cảm thụ mà người trước
    #     đã đo. Bản vá còn sửa một fixture cũ vốn thiếu trường `free_ram_gb` — thiếu đúng chỗ
    #     biến một hụt tài nguyên nhất thời thành cái chốt vĩnh viễn mà chính file test ấy cấm.
    #   - `patch_reserve_marks_the_slot`: `reserve()` chỉ nhận tên preset nên một giọng đã ghim
    #     nhích bộ đếm qua một bậc formant *bất kỳ*. Lô 1 mất bậc `0,898` của Thanh Bình trong
    #     khi `f104` phát cho cả CHA lẫn SỐ BA — một va chạm giọng tránh được hoàn toàn.
    "patch_reserve_marks_the_slot.py",
    "patch_pool_counts_its_own_ram.py",
    # 2026-09-10, tại ranh giới lô 2 / lô vá cho lô 2. Hai nguyên nhân lô 2 hỏng, hai bản vá.
    #
    #   - `patch_rate_impossible_is_the_same_family`: `ASR_TRANSCRIPT_RATE_IMPOSSIBLE` là em
    #     ruột của `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` — `_evaluate_transcript_core` trả hai mã
    #     cạnh nhau với hình dạng y hệt. Chú thích của mã kia ghi rõ nó "was a bare string in
    #     three places", tức đã được nâng thành hằng số và đưa vào danh sách không-chặn; mã này
    #     bị bỏ sót trong đúng lần dọn ấy. Lô 2 tính tiền hai chương (031, 043), cả hai đoạn là
    #     tiếng cười mà Whisper lặp vòng. Bản vá còn sửa hai chỗ **cứng hoá tên mã**: cho RATE
    #     đi qua đường ấy mà không sửa thì báo cáo đổ cho mốc-thời-gian trong khi thủ phạm là
    #     số-từ.
    #   - `patch_finished_take_beats_a_cut_off_one`: bản vá **đầu tiên thay audio** chứ không chỉ
    #     gỡ chặn, nên nó được dựng để mặc định từ chối. Bốn điều kiện ở tầng database, kiểm từ
    #     chính hai dòng dữ liệu; đường ống chỉ đề nghị; bất biến `dual_passed` nới đúng một chỗ.
    #     Ba ca trên 50.196 đoạn, cả ba đương nhiệm dài đúng 1,92s = 12 khung × 160 ms.
    #
    #     Một cách chữa rẻ hơn đã bị phép đo bác bỏ trước khi viết: nới cái cớ văn-bản-ngắn ở
    #     chỗ phán xử ứng viên. Đếm thì 469 đoạn văn-bản-ngắn có ứng viên mà đương nhiệm KHÔNG
    #     chạm trần, phần lớn đã `verified` — làm thế là trao quyền thay thế cho bốn trăm chỗ
    #     chẳng cần thay. Chỉ 14 đoạn có đủ cả ba điều kiện.
    "patch_rate_impossible_is_the_same_family.py",
    "patch_finished_take_beats_a_cut_off_one.py",
    # 2026-09-10: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # `APPLIED` bên dưới ĐÃ vào cây thật; chúng assert chuỗi gốc nên chạy lại sẽ dừng chứ không
    # hỏng gì.
    #
    # 2026-09-10, viết trong lúc lô 2 chạy bốn chương cuối. Áp ở ranh giới lô, **trước** lô vá cho
    # lô 2 — nếu áp sau thì chương 031 và 043 lại hỏng đúng chỗ cũ.
    #
    # `ASR_TRANSCRIPT_RATE_IMPOSSIBLE` là em ruột của `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE`:
    # `_evaluate_transcript_core` trả hai mã cạnh nhau với hình dạng y hệt (`ASR_INCONCLUSIVE`,
    # `repairable: False`, `severe: False`). Cái kia có chú thích ghi rõ nó "was a bare string in
    # three places" — tức đã được nâng thành hằng số và đưa vào danh sách không-chặn; cái này bị bỏ
    # sót trong đúng lần dọn ấy, vẫn là chuỗi trần ở một chỗ và không nằm trong danh sách nào.
    #
    # Lô 2 tính tiền hai chương cho chỗ bỏ sót ấy (031, 043), và cả hai đoạn là **tiếng cười**.
    # Chạy thử trên bản sao: 266 test asr/policy/quality xanh.
    # 2026-09-10, viết trong lúc lô 3 chạy. Áp ở ranh giới lô, TRƯỚC lô 4.
    #
    # `patch_dropped_marks_are_the_same_name`: cùng một nhân vật bị tách đôi vì Ollama rơi dấu ngẫu
    # nhiên trong nhãn nó tự đặt (THU LÃNH / THỦ LÃNH, NGUOI TRA LOI / NGƯỜI TRẢ LỜI - nguồn văn bản
    # không chứa chuỗi nào trong số ấy). Ở lô 3 bản rơi dấu đã thành bản trội (66 so với 32, 160
    # so với 46) vì `_known_summary` đưa bản nhiều lần hơn vào prompt kế tiếp. Mỗi bản tách một
    # chiếm một chỗ trong kho 14 giọng nam, và một người đọc bằng hai giọng. Luật gộp là "tập con
    # dấu", không phải "bỏ dấu ra giống nhau" - MÁ và MÀ vẫn là hai từ. Thử trên bản sao: 65 test
    # casting xanh.
    #
    # `patch_wrap_prefers_a_stranger`: nấc quay vòng của bộ cấp phát giọng biết ai cùng chương. Lô 3
    # có 18 người nam đòi 14 chỗ, nấc quay vòng mù chạy thật, 3 trong 7 va chạm nằm cùng chương
    # (IGOR + THU LÃNH ở 062 đã vào audio). Khi PHẢI dùng chung, chọn bậc mà người giữ nó có ít
    # chương chung nhất với người sắp cast; không biết ai đang cast thì quay vòng như cũ. Thử trên
    # bản sao: 294 test xanh, và hai bản vá áp được theo CẢ HAI thứ tự.
    # Ba bản vá cùng sửa character_registry.py. Thứ tự này là thứ tự ĐÃ THỬ; thứ tự ngược
    # (họ-bịa trước) cũng xanh sau khi neo của bản rơi dấu được thu hẹp ngày 2026-09-10 - nhưng
    # "cũng xanh" là kết quả đo trên hai bản sao, không phải lời hứa. Đừng đổi mà không đo lại.
    # Thứ tư, file khác (audio_io.py) nên không chạm neo ba bản trên: một bản thu chỉ "chậm"
    # khi chậm theo cả chữ lẫn âm tiết. Chương 075 của lô 3 mất một câu 10/10 lần ở ~11 chars/s
    # vì câu toàn từ ngắn (2,25 chữ/từ); theo âm tiết nó đọc gần trung vị kho. Áp trước lô vá
    # của lô 3 để chính chương 075 là phép thử đầu tiên.
    "patch_dropped_marks_are_the_same_name.py",
    "patch_wrap_prefers_a_stranger.py",
    "patch_stray_surname_is_the_same_name.py",
    "patch_pace_counts_syllables_too.py",
    # 2026-09-11: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Hai bản vá cho ranh giới lô 4 -> 5. Cả hai sửa `character_registry.py` nhưng ở hai vùng khác
    # nhau (một ở `_canonicalize_named_speakers`, một ở `PresetAllocator`), và đã đo: áp theo **cả
    # hai** thứ tự cho ra cùng một file byte-một.
    #
    # `patch_the_book_decides_the_spelling` phải áp **cùng lúc** với việc nối
    # `scripts/source_spellings.py` vào `port_casting` - nửa gieo một mình sẽ ghim `SELNE VALKRYN`
    # dưới tên `SELENE`, rồi phân tích lại sinh `SELNE`, không khớp pin, và cấp một giọng mới.
    #
    # `patch_a_step_remembers_every_holder` sinh ra từ lô đúc lại của lô 3: `patch_wrap_prefers_a_
    # stranger` chạy đúng cho KANG (dùng chung với VIKTOR, người không có trong chương 071) rồi mù
    # với người kế tiếp, vì một bậc chỉ nhớ người giữ **đầu tiên**.
    # Thu ba, file khac (audio_io.py): sua mot loi CHINH TOI dua vao 21:19 cung ngay. Bo dem am
    # tiet tach theo khoang trang, nen moi cach doc noi bang gach ngang thanh MOT am tiet, va
    # chuong 084 mat vi the trong vong bon tieng.
    "patch_the_book_decides_the_spelling.py",
    "patch_a_step_remembers_every_holder.py",
    "patch_a_transliteration_is_many_syllables.py",
    # 2026-09-11: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Một bản vá, áp ở bước 1 của ranh giới lô 4 chạy LẠI (ranh gioi chet 08:45 vi phien Claude Code
    # thoat). NGUOI_TRA_LOI - gạch dưới - xuất hiện 45 câu trong bốn project tạo sau 07:25, và chương
    # 104 đúc lại có người ấy nói bằng hai giọng. Phải áp TRƯỚC các chương đúc lại còn lại và lô 5.
    "patch_an_underscore_is_a_space.py",
    # 2026-09-12: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Xếp hàng cho ranh giới lô 5 → 6 (2026-09-11 18:35). Xem `APPLIED` cho thứ tự và lý do các
    # nhóm đã vào cây.
    #
    # - patch_keep_the_locked_reading: vòng sửa ASR giữ cách đọc ghim khi bản đọc-ghim chỉ thua
    #   bài chính tả neo tên, thay vì đề cử bản đọc theo chữ viết (348/716 đoạn được sửa trong
    #   sách - 48% - đọc `Jake`/`Ishtara` thay vì `Giếch`/`I-xờ-hờ-ta-ra`). Đã thử trên bản sao
    #   lo03r_084b: 10/10 đoạn, chương ghép lại trong 38 giây không GPU. Sau khi vào cây, ranh giới
    #   chạy `scripts/keep_the_locked_reading.py --book --apply` cho các chương đã lên sách.
    # - patch_a_number_is_read_in_full: `vietnamese_number_words` đọc trọn vẹn tới dưới 10^12 theo
    #   ngữ pháp số đếm, và hai thước nhịp (ký tự, âm tiết) đếm dãy chữ số như đọc ra - từ 1000 lấy
    #   cận dưới của hai cách đọc. Chương 106 của lô 4 mất vì "123456" đếm là một âm tiết / sáu
    #   ký tự (10/10 lần ở 12,35 kt/s, sàn 12,5). ASR không đổi. Sau khi vào cây: ranh giới 5 → 6
    #   đúc lại 106 bằng `--recast 4:106`.
    # - patch_one_promoted_take_and_one_way_to_fail: **sau** hai bản vá trên (nó vá đúng đoạn mã
    #   bản vá thứ nhất thêm). Hai chỗ hở của đường `over_a_cut_off_incumbent` - đường mà bản vá
    #   thứ nhất vừa làm cho chạy được lần đầu: (a) việc hạ bản `promoted` cũ trở thành vô điều
    #   kiện, nên "một đoạn, nhiều nhất một ứng viên được đề cử" đúng cho cả ba đường thăng hạng
    #   (nếu không, `segment_candidate_resume_plan` sẽ ném ở lần đọc sau, xa chỗ gây ra lỗi);
    #   (b) `_promote_a_finished_take_over_a_cut_off_one` bọc mọi ngoại lệ thành "thôi không thay",
    #   vì `_segment_candidate_item` ném thật khi checksum văn bản đọc trôi và một ngoại lệ ở đấy
    #   giết chương đang phiên.
    "patch_keep_the_locked_reading.py",
    "patch_a_number_is_read_in_full.py",
    "patch_one_promoted_take_and_one_way_to_fail.py",
    # 2026-09-12: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.
    "patch_a_pinned_person_outranks_a_ported_voice.py",
    # 2026-09-13: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.
    "patch_a_supervisor_with_a_console_of_its_own.py",
    "patch_a_tie_goes_to_the_emptier_step.py",
    "patch_two_children_in_one_chapter_get_two_voices.py",
    # 2026-09-13: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.
    "patch_a_finished_take_is_promoted_without_two_passing_checks.py",
    "patch_a_stretched_cry_with_an_accent_is_still_a_cry.py",
    # 2026-09-14: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.
    "patch_a_formula_is_read_as_words.py",
    "patch_a_finished_take_survives_the_report.py",
    # 2026-09-15: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng
    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.
    # Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.
    "patch_the_nameless_crowd_says_where_it_speaks.py",
    "patch_no_gender_evidence_does_not_kill_the_book.py",
)


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _runs_in_flight() -> list[tuple[Path, str]]:
    """Project nào thật sự đang chạy, kèm lý do - đọc nhịp tim, không đọc file khoá.

    Bản đầu của hàm này liệt kê mọi thư mục có `.worker.lock`, và gắn cờ **cả 41 project** kể
    cả những cái xong từ hôm kia: file khoá nằm lại sau khi tiến trình chết. Một bộ canh lúc
    nào cũng kêu thì tệ hơn không có bộ canh - nó chỉ dạy người ta gõ `--force`.

    Tín hiệu đúng nằm trong bảng `worker_leases`: một lượt đang bay có dòng `state='running'`
    với `heartbeat_at` vừa mới đây; một lượt đã xong không còn dòng nào. Đo lúc 00:24 ngày
    2026-09-08: alpha.56 nhịp cách 2 giây, alpha.50 không có dòng lease nào.

    Mở read-only để không chạm vào project đang chạy.
    """
    if not VERSIONS.is_dir():
        return []
    now = time.time()
    live: list[tuple[Path, str]] = []
    for database in sorted(VERSIONS.glob("*/*/project.sqlite3")):
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT worker_name, pid, state, heartbeat_at FROM worker_leases"
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            # Một project hỏng hoặc đang bị khoá ghi không nói lên điều gì về việc nó có đang
            # chạy hay không; bỏ qua thay vì gắn cờ.
            continue
        for row in rows:
            if str(row["state"]) != "running":
                continue
            age = now - float(row["heartbeat_at"] or 0.0)
            if age <= LEASE_STALE_SECONDS:
                live.append(
                    (
                        database.parent,
                        f"lease {row['worker_name']} pid={row['pid']} nhịp cách {age:.0f}s",
                    )
                )
    return live


def _assignment_span(lines: Sequence[str], name: str) -> tuple[int, int]:
    """(dòng đầu, dòng cuối) - chỉ số 0 - của phép gán cấp module cho `name`."""
    tree = ast.parse("\n".join(lines))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
            node.targets[0], ast.Name
        ):
            target = node.targets[0].id
        if target == name:
            return node.lineno - 1, int(node.end_lineno or node.lineno) - 1
    raise ValueError(f"không thấy phép gán {name} ở cấp module")


def retire_queue(path: Path, names: Sequence[str], when: str) -> int:
    """Rút `names` khỏi `ORDER` trong file `path` và ghi chúng vào cuối `APPLIED`. Trả về số rút.

    Gọi ngay sau khi áp xong và **trước** bộ test, để cây được kiểm là cây sẽ được commit. Ở ranh
    giới lô 2 việc này làm tay, sau khi `_remember_green` đã ghi vân tay - nên `before_a_batch`
    chạy lại cả bộ test trên một cây chỉ khác đúng chỗ hàng chờ. Và một ranh giới không có ai
    ngồi cạnh (`scripts/boundary.sh`) thì không có tay nào để làm: cửa số 3 của gate đọc chính
    `ORDER`, hàng chờ còn tên là lô sau không bao giờ bắt đầu.

    Khối chú thích đứng ngay trên `ORDER` (và những dòng chú thích nằm trong tuple) đi theo tên
    xuống `APPLIED`, thụt vào bốn cách - đó là cách hồ sơ này vẫn được viết tay từ trước.
    """
    names = [name for name in names]
    if not names:
        return 0
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("utf-8").replace("\r\n", "\n").split("\n")

    # Tìm hai phép gán bằng `ast`, không bằng "dòng chỉ có `)`": một hàng chờ MỘT tên viết gọn
    # `ORDER: tuple[str, ...] = ("patch_x.py",)` không có dòng `)` riêng, và bản đầu của hàm này
    # nhảy tới dấu `)` kế tiếp - là dấu đóng của `APPLIED` - rồi ghi ra một file không import
    # được (đo 19:10 2026-09-11 trên cây tạm, đúng dạng hàng chờ mà cây thật đã mang hai giờ
    # trước đó). Ranh giới tự chạy không có ai sửa tay file hỏng ấy.
    start, end = _assignment_span(lines, "ORDER")
    inner_comments = [line.strip() for line in lines[start + 1 : end] if line.strip().startswith("#")]
    above = start
    while above > 0 and lines[above - 1].startswith("#"):
        above -= 1
    above_comments = lines[above:start]

    applied, applied_end = _assignment_span(lines, "APPLIED")
    if lines[applied_end] != ")":
        raise ValueError("APPLIED phải đóng bằng một dòng `)` riêng để ghi thêm vào cuối")

    record = [
        f"    # {when}: rút khỏi hàng chờ bởi `apply_all --apply`, ngay trước bộ test. Lý do từng",
        "    # bản vá nằm trong docstring của chính nó; khối dưới đây là chú thích của hàng chờ.",
    ]
    for line in above_comments + inner_comments:
        record.append(("    #" + line.lstrip("#").rstrip()).rstrip())
    record.extend(f'    "{name}",' for name in names)

    new_lines = (
        lines[:above]
        + [
            "# Hàng chờ rỗng. Mọi bản vá đã vào cây; xem `APPLIED` cho thứ tự và lý do từng nhóm.",
            "ORDER: tuple[str, ...] = ()",
        ]
        + lines[end + 1 : applied_end]
        + record
        + lines[applied_end:]
    )
    path.write_bytes(newline.join(new_lines).encode("utf-8"))
    return len(names)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Ghi thật thay vì chỉ liệt kê")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Bỏ bước chạy test - chỉ dùng khi định chạy tay ngay sau đó",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ghi kể cả khi phát hiện lượt chạy đang bay. Đừng.",
    )
    args = parser.parse_args(argv)

    if not ORDER:
        _say(f"Hàng chờ rỗng. {len(APPLIED)} bản vá đã vào cây thật; xem README.md.")
        return 0

    missing = [name for name in ORDER if not (HERE / name).is_file()]
    if missing:
        _say("thiếu bản vá: " + ", ".join(missing))
        return 2

    _say(f"{len(ORDER)} bản vá, theo thứ tự:")
    for index, name in enumerate(ORDER, 1):
        _say(f"  {index}. {name}")

    in_flight = _runs_in_flight()
    if in_flight:
        _say("")
        _say("CÓ LƯỢT CHẠY ĐANG BAY:")
        for path, why in in_flight:
            _say(f"   {path}")
            _say(f"      {why}")
        if not args.force:
            _say("")
            _say("Không ghi. Đợi nó xong, hoặc `stop` nó, rồi chạy lại.")
            return 1
        _say("   --force: ghi bất chấp. Lượt ấy sẽ không resume được.")
    else:
        _say("")
        _say("Không có lượt nào đang chạy.")

    if not args.apply:
        _say("")
        _say("Đây là lượt thử, chưa ghi gì. Thêm --apply để ghi thật.")
        return 0

    python = sys.executable
    for name in ORDER:
        _say("")
        _say(f"--- {name} ---")
        result = subprocess.run(
            [python, str(HERE / name), str(ROOT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        _say((result.stdout or "").rstrip())
        if result.returncode != 0:
            _say((result.stderr or "").rstrip())
            _say("")
            _say(f"DỪNG ở {name}. Những bản vá trước nó ĐÃ được ghi - đừng chạy lại từ đầu,")
            _say("sửa cái này rồi áp nốt phần còn lại bằng tay.")
            return 1

    retired = retire_queue(Path(__file__).resolve(), ORDER, time.strftime("%Y-%m-%d"))
    _say("")
    _say(f"Đã rút {retired} bản vá khỏi hàng chờ vào APPLIED - trước bộ test, để cây được kiểm")
    _say("là cây sẽ được commit.")

    if args.skip_tests:
        _say("")
        _say("Đã áp hết. Bỏ qua test theo yêu cầu - hãy chạy chúng.")
        return 0

    _say("")
    _say("--- bộ test đầy đủ ---")
    tests = subprocess.run([python, "-m", "pytest", "-q"], cwd=str(ROOT), text=True)
    if tests.returncode != 0:
        _say("")
        _say("TEST ĐỎ. Đừng chạy lượt nào cho tới khi xanh lại.")
        return 1
    # Ghi lại rằng bộ test đã xanh cho **cây này**, để `before_a_batch.py` không chạy lại cùng
    # một bộ test trên cùng một cây ngay sau đây. Ở ranh giới lô 2 hai lượt chạy liên tiếp kiểm
    # đúng một cây và giữa chúng chỉ có một file Markdown đổi - mười tám phút GPU ngồi không.
    #
    # Bản ghi do **người đã thấy** lượt xanh viết, không phải một lời khẳng định của người khác:
    # đó là khác biệt giữa việc ghi sổ và việc thêm một cờ bỏ-qua.
    try:
        sys.path.insert(0, str(HERE.parent))
        from before_a_batch import _remember_green, _source_fingerprint

        _remember_green(_source_fingerprint())
    except Exception as exc:  # noqa: BLE001
        _say(f"(không ghi được vân tay lượt xanh: {exc!r} - lần sau chạy lại bộ test)")
    _say("")
    _say("Xanh hết. Giờ mới được chạy lượt mới.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
