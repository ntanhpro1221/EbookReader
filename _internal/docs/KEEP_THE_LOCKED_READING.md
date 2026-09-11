# Giữ cách đọc ghim: bài chính tả neo tên không được đổi thứ người nghe nghe

Viết 2026-09-11, 18:40, trong lúc lô 5 đang phân tích. Mã nằm ở
`scripts/pending_patches/patch_keep_the_locked_reading.py` (chưa vào cây — áp ở ranh giới lô
5 → 6) và `scripts/keep_the_locked_reading.py` (lượt đề cử lại cho các chương đã lên sách).
Đặc tả gốc và hai lần sửa đặc tả nằm trong `OPTIMISATION_QUEUE.md`; tài liệu này ghi **thứ
đã làm khác đặc tả, và vì sao**, để người sau không phải đọc lại 700 dòng bản vá.

## Con số dẫn tới bản vá

Đo trên cuốn sách 92 chương đã ghép (`A_NAME_READ_MANY_WAYS.md`):

    716   ứng viên được đề cử (đoạn đã đi qua vòng sửa ASR)
    348   trong đó là `source_spelling_v1` — đọc tên theo CHỮ VIẾT (48%)
          Jake 79 · Michael 35 · Spirit 31 · Will 20 · Apex 19 · Willem 16 · Alice 13
    348   / 348 bản đọc-ghim anh em: cả hai đường phiên `fail` với DUY NHẤT một mã,
          ASR_LOCKED_NAME_ANCHOR_MISMATCH; nhịp qua; WAV còn nguyên trên đĩa

Cơ chế, đọc từ chương 084 đúc lại: bản đọc-ghim (`I-xờ-hờ-ta-ra`) qua cổng nhịp, chết ở cổng
neo tên trên cả beam lẫn greedy. Vòng sửa "rõ tiếng" ở vòng lẻ yêu cầu biến thể đọc theo chữ
viết (`Ishtara`), Whisper nghe được, ứng viên ấy được đề cử, đương nhiệm của đoạn đổi, và bản
đọc-ghim bị đánh dấu `invalid: incumbent checksum changed`. Chương lên sách với một thành phố
đọc khác mọi chương kia.

`LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md` đã kết luận neo tên là bài chính tả, không phải
bằng chứng bản thu hỏng, và `_grant_machine_acceptances` đã coi mã ấy là máy chấp nhận được —
nhưng ở **cuối chương**, sau vòng sửa. Với trần khung, "chỉ sau khi hết ngân sách sửa" là đúng;
với neo tên nó sai, vì vòng sửa "cứu" bằng cách đổi cách đọc, tức đổi thứ người nghe nghe.
Bản vá đưa quyết định ấy xuống tầng ứng viên, **trước** khi vòng sửa thay cách đọc.

## Bản vá làm gì

`database.py`

- `find_locked_reading_that_lost_only_the_spelling_test(segment_id, policy_hash)` — không ném.
  Gọi đúng hàm kiểm mà đường đề cử gọi, coi một lần ném là "không". Năm điều kiện, kiểm từ dữ
  liệu bằng `require_all` nên lời từ chối nêu đúng mệnh đề: (1) biến thể `locked_spoken_v1`;
  (2) cả hai check phiên tồn tại; (3) hợp mã trượt khác rỗng và ⊆ {`ASR_LOCKED_NAME_ANCHOR_
  MISMATCH`, `ASR_LOCKED_NAME_ANCHOR_REVIEW`}; (4) tín hiệu không có cờ chặn, không chạm trần,
  không `pace_outlier`, file trên đĩa khớp checksum; (5) đương nhiệm hiện tại của đoạn hoặc
  chưa đổi, hoặc là anh em `source_spelling_v1` đã được đề cử — cùng `segment_id`, mang đúng
  checksum hiện tại của đoạn.
- `promote_segment_candidate(..., keeping_the_locked_reading=True)` nới **ba** bất biến trong
  cùng hàm, sau khi năm điều kiện trên đã kiểm: tập trạng thái được đề cử (thêm `dual_failed`
  và `invalid`); "hai check ASR phải PASS" (kiểm lại tại chỗ nới: mã trượt chỉ được là neo tên);
  "checksum đương nhiệm chưa đổi". Mọi chốt chặn toàn vẹn khác — voice profile, provenance
  split / vocalization / delivery / postprocess, cảm thụ — chạy nguyên.
- `_validated_promoted_candidate_conn` đọc lý do từ chính dòng check cuối của ứng viên
  (`repair_action == keep_locked_reading_over_spelling_take`) và chỉ khi ấy mới chấp nhận sổ
  phiên trượt-chỉ-neo-tên. Hàm này chạy mỗi lần dựng kế hoạch tiếp tục và mỗi lần lắp ráp
  chương; không nới ở đây thì đoạn vừa giữ cách đọc ghim làm chương không lắp được.

`pipeline.py`

- `_keep_the_locked_reading(item)` — đường ống chỉ đề nghị. Gọi trong vòng sửa ASR ngay trước
  khi cấp phát ứng viên **vòng lẻ** (vòng mà biến thể chữ viết được yêu cầu). Ghi phán quyết
  máy cho từng mã neo tên với lý do "neo tên là bài chính tả; giữ cách đọc ghim để nhất quán
  toàn sách", ghi `machine_take_substitutions`, log một dòng.
- `_publish_verified_chapter(chapter)` — đuôi của `_process_chapter` tách thành hàm (xem
  "Ba điều bất ngờ", mục 3).

## Ba điều bất ngờ khi thử trên bản sao của project thật

Bài thử (`tests/test_keep_the_locked_reading.py`, nằm trong bản vá) chép `lo03r_084b` vào thư
mục tạm và đề cử lại ở đó; bỏ qua có nói lý do nếu máy không có project ấy. Đồ thị ứng viên
với đủ provenance quá nặng để dựng tay, và một bài thử trên dữ liệu thật đã bắt được ba lỗi
thiết kế mà bài dựng tay sẽ không thấy.

1. **CAS cuối cùng so với đương nhiệm cũ.** `promote_segment_candidate` kết thúc bằng
   `UPDATE segments … WHERE id=? AND wav_sha256=?` với `candidate.incumbent_sha256` — đương
   nhiệm mà ứng viên *đã đấu với*. Khi giữ cách đọc ghim, đương nhiệm hiện tại là anh em
   đọc-theo-chữ-viết, nên CAS trả 0 dòng và "thắng" đọc thành "mất đương nhiệm". Sửa: khi giữ
   cách đọc ghim, CAS so với `segment.wav_sha256` đọc cùng giao dịch — vẫn là CAS, đúng đối
   tượng. Rồi hạ anh em đọc-theo-chữ-viết khỏi `promoted` trong cùng giao dịch, có CAS theo
   checksum cũ, vì `_invalidate_candidate_conn` cố ý không hạ bản đã đề cử và
   `segment_candidate_resume_plan` ném nếu một đoạn có hai bản được đề cử. Ràng buộc CHECK
   của bảng đòi `promoted_at IS NULL` khi không còn `promoted`; `final_check_id` giữ lại để
   sổ vẫn kể được bản ấy từng qua cổng cuối.

2. **CAS trạng thái ứng viên so với hằng số — và đường "bản hoàn chỉnh thắng bản bị cắt"
   chưa từng chạy thật.** Dòng cuối `UPDATE segment_candidates … WHERE id=? AND state=?` so với
   hằng số `dual_passed`. Đường `over_a_cut_off_incumbent` (có sẵn) đề cử ứng viên
   `dual_failed`, nên với hằng số ấy nó *không bao giờ* đi qua được — giao dịch cuốn lại,
   không hỏng dữ liệu, chỉ là không bao giờ thành công. Đếm 47 project lô: **0** dòng
   `machine_take_substitutions`, 0 sự kiện `SEGMENT_TAKE_SUBSTITUTED`, 0 lỗi "state CAS
   failed" — đường ấy chưa từng được gọi, nên lỗi chưa từng lộ. Sửa: so với `candidate_state`
   đọc ở đầu giao dịch. Đúng cho cả ba đường.

3. **Không chạy lại cả `_process_chapter` cho chương đã hoàn thành.** Thử đầu tiên của lượt
   đề cử lại gọi `_process_chapter` trên chương 084 và nó nạp Whisper. Nguyên nhân: một chương
   đã hoàn thành vẫn có thể mang đoạn `failed` được máy cấp phép (`Selene Valkryn.`, thua neo
   tên qua **năm** vòng ứng viên, chấp nhận ở cuối chương). Bước tổng hợp coi đoạn ấy là chưa có
   bằng chứng hiện hành — vì phán quyết đã làm "current asr failure" thành sai — đặt lại thành
   `signal_passed`, rồi đưa vào hàng chờ phiên. Đó là hành vi resume có chủ ý của đường ống
   (một chương dở dang phải được phiên lại), nhưng cho lượt ghép lại thì nó biến một việc chỉ
   ffmpeg thành một việc cần GPU. Vậy đuôi của `_process_chapter` — cấp phép máy, ba cổng chặn,
   ffmpeg, sổ chất lượng chương, artifact, hoàn thành — tách thành `_publish_verified_chapter`,
   và **hai người gọi** dùng chung một thân hàm. Bản vá tách bằng cách cắt đúng văn bản (không
   chép tay), nên cổng nào thêm sau này thì cả hai người gọi cùng đi qua.

Một điều nhỏ hơn cùng buổi: `test_no_new_blind_compound_check_is_added` đếm `if` ghép ba điều
kiện trở lên trước một `raise` trong `database.py` và không cho tăng. Bản vá đầu thêm một cái;
đổi sang `require_all` — và lời từ chối nêu đúng mệnh đề, cái mà bài thử ấy tồn tại để đòi.

## Lượt đề cử lại cho các chương đã lên sách

    python scripts/keep_the_locked_reading.py <project> [--apply]
    python scripts/keep_the_locked_reading.py --book --apply      # mọi project manifest.json ghi

Không GPU. Dựng một `BookPipeline` bỏ qua `__init__` (mẫu `refresh_terminal_reports_without_
runtime`), với `TTSCoordinator` thật — đường ống hỏi nó cả về văn bản (`spoken_text_with_
anchors`) — nhưng rào chỗ nạp model và mọi lối vào tổng hợp: có đi tới đó là script ném chứ
không lặng lẽ nạp VieNeu cạnh một lô đang bay. Từ chối khi project đang chạy, khi cây mã chưa
có bản vá, và khi project khoá chính sách chất lượng phiên bản khác cây mã.

**Chính sách chất lượng là của project, không phải của cây mã.** `implementation_hash` nằm
trong chính sách, nên mỗi bản vá đã áp từ lúc chương được đúc đổi mã băm ấy (đo 18:25 trên
084b: `c7d785…` theo cây mã, `054f8c…` trong project). Với mã băm của cây mã thì không ứng viên
nào thuộc chính sách đang hoạt động, không bằng chứng nào hiện hành, và MP3 mới cũng không.
Lượt này ghép lại chương dưới đúng chính sách chương ấy được đúc, và không gọi
`set_current_quality_policy`. Đây cũng là lý do `cli run` trên một project cũ sau bản vá sẽ
phiên lại cả chương — nó đổi chính sách — và là lý do ranh giới tạo project mới thay vì resume.

Kết quả trên bản sao 084b (18:30): 10/10 đoạn giữ cách đọc ghim; 7 anh em đọc-theo-chữ-viết bị
hạ (3 đoạn còn lại đương nhiệm chưa từng đổi); 12 bản `promoted` đều `locked_spoken_v1`; không
đoạn nào có hai bản được đề cử; kế hoạch tiếp tục dựng được cho cả 12; chương ghép lại trong
38 giây, MP3 mới `8274b4…` 14,5 MB có bằng chứng QA hiện hành; `cli validate` qua hết
(decode, checksum, chapter_qa, segment_qa, publishable).

Ranh giới chạy lượt này ở **bước 6b** (`boundary.sh`): sau khi lô kế tiếp đã khởi động — vì
không GPU nên chạy cạnh lô là vô hại — và trước khi ghép sách, để `assemble_book.py --apply`
chép MP3 mới (nó chép khi kích thước đổi). Các project vừa vá / đúc lại ở bước 3–4b chạy bằng
mã mới nên đã tự giữ cách đọc ghim; `--book` chỉ chạm các chương trong manifest của lần ghép
trước.

## Lượt thử trên cả cuốn sách, và hai luật nó ép script phải có

Lượt thử chỉ-đọc trên 36 project của manifest (18:50) đếm **1.127** đoạn có bản đọc-ghim chỉ
thua bài chính tả — không phải 348. Hai lý do, và mỗi lý do thành một luật của script:

1. **Chỉ chương manifest ghi, không phải cả project.** Một project lô có 31 chương nhưng sách
   chỉ lấy vài chương từ nó; phần còn lại đã bị bản đúc lại thay. Không lọc thì lượt này chạm
   142 chương-project cho một cuốn sách 116 chương — phí, và tệ hơn phí: `assemble_book` chọn
   bản có `completed_at` mới nhất, nên một chương cũ vừa ghép lại sẽ **đoạt lại chỗ** của bản
   đúc lại, và dàn giọng cũ quay về sách. `--book` giờ mang theo tập chương của từng project;
   33 chương bị bản khác thay được bỏ qua và nói ra.

2. **Chỉ đoạn đang phát bản đọc-theo-chữ-viết.** Trong 1.127 có 597 đoạn đang phát `Jake` — lỗi
   người nghe nghe thấy — và 530 đoạn vẫn phát bản gốc (`failed`, máy đã cấp phép) nhưng có bản
   đọc-ghim rõ tiếng chỉ thua bài chính tả. Hai bản ấy cùng đọc ghim, cùng thua cùng một bài;
   không có bằng chứng nào xếp hạng chúng, và đổi audio đã lên sách mà không có lý do người
   nghe cảm được là đổi cho có. Mặc định để yên; `--also-unchanged` mở nếu có ngày cần. (Vòng
   sửa đã vá vẫn đề cử bản rõ tiếng ở lô mới — ở đó chưa có gì lên sách để mà giữ.)

Sau hai luật: **452 đoạn trong 102 chương** sẽ được chữa, 411 để yên, 33 chương bỏ qua. Ở ~40
giây một chương, bước 6b mất chừng 70 phút — chạy cạnh lô 6 vừa khởi động, không GPU. Thử lại
trên bản sao 084b với luật mới: 7/7 đoạn, 3 để yên, MP3 mới `9a4a30…`, `cli validate` qua.

## Dự đoán ghi trước (kiểm ở lô 6 và sau lượt đề cử lại)

- Lô 6: tỉ lệ ứng viên `source_spelling_v1` được đề cử về **~0** cho các ca chỉ-neo-tên; số
  neo tên `matched=False` không đổi (cổng vẫn nói điều nó thấy); `one_person_one_voice.py`
  không đổi (đây là chuyện cách đọc, không phải giọng).
- Sau `--book --apply`: lượt thử chỉ-đọc chạy lại phải in "không đoạn nào đang phát bản
  đọc-theo-chữ-viết" cho cả 36 project (để yên 411); đếm bản `source_spelling_v1` được đề cử
  trong sách giảm đúng 452; những ca còn lại là đoạn thua thêm mã khác ngoài neo tên — chúng
  đúng là bản thu hỏng, và đổi cách đọc ở đó không phải lỗi.
- Nếu một chương ghép lại không được, script in "CHƯA ghép lại" với lý do; artifact đã đánh
  dấu hết hiệu lực nên `cli run` (GPU) sẽ tự ghép lại khi được gọi.
