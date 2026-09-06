# Nhật ký phiên bản

Mỗi phiên bản là một tag Git kèm một lần chạy thật trên chapter thuộc `Text_Tmp`. Mục đích của file này là
để người tiếp theo biết **tại sao** một thay đổi được thực hiện và **bằng chứng nào** dẫn tới nó, chứ không
chỉ là danh sách commit.

## Quy ước

- Tag: `v<major>.<minor>.<patch>-alpha.<n>`, khớp với `version` trong `_internal/pyproject.toml`
  (pyproject luôn mang số của phiên bản **đang phát triển**, tag mang số của phiên bản **đã phát hành**).
- Output của từng phiên bản nằm ngoài repo, tại `D:\Novels\Audiobooks\_versions\<tag>\`.
  Audio và SQLite **không bao giờ được commit** — chúng chỉ để nghe lại và đối chiếu.
- Một phiên bản **không cần chạy hết**. Đọc log và chấm audio ngay khi có segment đầu tiên;
  thấy lỗi hệ thống thì dừng, sửa, tạo project sạch và chạy lại.
- Mọi thay đổi hành vi phải cập nhật `AGENTS.md` (invariant) và/hoặc `README.md` (hành vi người dùng thấy)
  trong cùng commit.

## Cách chạy một phiên bản

```bash
cd _internal
./runtime/.venv/Scripts/python.exe -m ebook_reader.cli create \
  --output-root "D:/Novels/Audiobooks/_versions/<tag>" \
  --source-dir "D:/Novels/Tools/Text" \
  --range "000..009" --width 3 --title "<tag>" --profile high_quality --json
./runtime/.venv/Scripts/python.exe scripts/port_pronunciations.py "<project trước>" "<project-root>"
./runtime/.venv/Scripts/python.exe -m ebook_reader.cli run "<project-root>" --json
```

**Gieo từ bản nào?** Bản có phán quyết của người, **không phải bản gần nhất**. Tính tới
2026-09-06 đó là **alpha.47**: chỉ nó có `Theosbane = theo-bên` với `source=listener_choice`.
alpha.48 và alpha.50 chỉ trùng nhờ may (`Theo-bên`, khác chữ hoa), alpha.49 thì lệch hẳn
(`Thê-ô-ban`). Gieo nhầm nguồn là chép lại một lần bốc thăm của máy thay vì quyết định của
chủ sách — và vì `port_pronunciations.py` giữ nguyên `source`, cái sai ấy sẽ tự nhân bản
sang mọi bản sau.

Kiểm nhanh trước khi gieo:

```bash
_internal/.venv/Scripts/python.exe -c "import sqlite3,glob;d=sqlite3.connect(glob.glob('D:/Novels/Audiobooks/_versions/<tag>/*/project.sqlite3')[0]);print([r for r in d.execute(\"SELECT surface,spoken_form,source FROM pronunciations WHERE source='listener_choice'\")])"
```

Rỗng nghĩa là bản ấy không mang quyết định nào của người — tìm bản khác.

`port_pronunciations.py` chạy **giữa `create` và `run`**, không lúc nào khác. Cách đọc một
cái tên không ổn định giữa các lần chạy — đo trên 112 tên: alpha.46 lệch 4, alpha.49 lệch 3,
alpha.47 lệch 0 — và mỗi cái tên trôi làm đổi audio của mọi segment chứa nó, tức xoá luôn
phán quyết người nghe đã cho cho những segment ấy. `normalize_name_pronunciations` bỏ qua tên
đã có cách đọc khóa, nên gieo sẵn bảng là những tên đó không bao giờ được gửi lên model.

Nó **từ chối** một project đã phân tích segment: đổi cách đọc sau lúc ấy làm trôi spoken text
dưới audio đã có — đúng cái bẫy khiến `pronounce` phải từ chối chạy giữa chừng.

> **Nguồn phải là `D:/Novels/Tools/Text`, không phải `Text_Tmp`.** Chỗ này từng ghi sai và
> đã tốn một lần chạy: alpha.46 lần đầu được tạo từ `Ebook Reader/Text_Tmp`, ra 995 segment
> thay vì 948, tức **một quyển sách khác** - không so được với alpha.43/44/45 nên toàn bộ ý
> nghĩa của việc đánh số phiên bản mất sạch.
>
> Cách kiểm tra rẻ nhất, làm ngay sau `create`: `input_manifest_hash` phải bắt đầu bằng
> `02502ba320`, và thư mục project phải tên `<tag>_02502ba320`. Hash khác nghĩa là nguồn khác,
> dừng lại trước khi chạy chứ đừng phát hiện sau ba tiếng.

Dùng `cli run` chứ không phải `run_book_job.py`: `run` khởi động qua background supervisor nên
chạy tiếp được sau khi đóng terminal, `stop`/`resume` dùng được, và watchdog tự chạy lại
(`scripts/resume_interrupted.py`) mới nhìn thấy nó. `run_book_job.py` chạy worker ngay trong
tiến trình gọi, mất hết những thứ đó.

Chấm giữa chừng, không cần đợi xong:

```bash
./runtime/.venv/Scripts/python.exe scripts/audit_audiobook.py "<project-root>"
```

---

### Kết quả chạy alpha.10: cả hai fix đều xác nhận có tác dụng

| | alpha.9 | alpha.10 |
|---|---|---|
| Segment fail | **15** | **2** |
| Publish kèm cảnh báo review | 0 | **12** |
| Đạt đúng target loudness | 27/107 (25%) | **199/199 (100%)** |
| Chạm trần peak | 75% | **0%** |
| Lệch loudness trung bình | −1,22 dB | **+0,00 dB** |
| Thứ tự theo `volume` | loud −17,8 **nhỏ hơn** normal −19,77 | loud −23,8 > normal −24,5 > soft −27,5 |

Dự đoán trước khi chạy là 9/15 sẽ pass nhờ hạ anchor xuống review; thực tế 13/15 pass, phần thêm đến từ
việc thôi tính lỗi tên hai lần trong metric canonical.

**Chương vẫn chưa publish** vì còn 2 segment fail, mỗi chương một cái — nhưng cả hai đều **không thuộc lớp
từ chối nhầm** mà alpha.10 nhắm tới:

- `c00002_s0000041` `"Joel cười trừ:"` → `"Joanne cười chữ."`. Câu 3 từ; bỏ tên ra còn 2 token thường, dưới
  ngưỡng miễn trừ nên anchor giữ hard-fail. Kể cả có miễn trừ, `trừ`→`chữ` vẫn cho WER 0,333 > 0,30.
- `c00001_s0000044` — câu dài, rất nhiều từ thường sai. Audio tệ thật, gate chặn đúng.

**Việc còn lại là "chặng cuối"**: với ~1 segment hỏng trên 100, không chương nào publish được. Đó là bài
toán khác với bài toán alpha.10 đã giải, và cần bằng chứng riêng trước khi đụng vào. Đừng nới thêm gate chỉ
để mọi thứ pass — đó chính là kiểu hỏng cần tránh.

### Điều tra: vì sao dịch cao độ lại làm hỏng giọng? — Không phải do dịch, mà do vocoder

Người dùng chất vấn đúng chỗ: dịch cao độ giữ nguyên formant thì về nguyên tắc **không được** đổi nhận diện
giọng. Đọc lại `apply_pitch_variant`: code làm đúng thiết kế — `harvest`+`stonemask` lấy F0, `cheaptrick`
lấy spectral envelope, `d4c` lấy aperiodicity, chỉ nhân F0 với `2^(steps/12)` rồi tổng hợp lại với envelope
**gốc**. Formant được bảo toàn.

Nhưng `steps == 0` **return sớm**, không đi qua WORLD. Nghĩa là khác biệt giữa `pitch 0` và `pitch ≠ 0`
không phải chỉ là cao độ — mà là **cả một vòng phân tích–tổng hợp lại**. Đo tách bạch hai thứ đó trên 8
segment, bằng cách ép chạy WORLD với `steps=0`:

| | MOS delta so với file gốc |
|---|---|
| WORLD round-trip, dịch **0** bán âm | **−0,268** |
| WORLD dịch **−1** | −0,201 |
| WORLD dịch **+1** | −0,367 |

**Dịch 0 bán âm đã mất 0,268 MOS.** Bản thân phép dịch gần như không thêm chi phí. Thủ phạm là vòng vocoder,
không phải cao độ.

**Hệ quả cho ý tưởng dùng bước 0,5 bán âm:** không giải quyết được gì. Mỗi biến thể vẫn trả **nguyên** cái
giá `−0,27` MOS vì giá nằm ở vòng vocoder chứ không ở độ lớn bước dịch — gấp đôi số biến thể là gấp đôi số
giọng phải trả giá. Thêm nữa, 0,5 bán âm ≈ 3% thay đổi F0, nằm ngay ngưỡng phân biệt của tai người với giọng
nói liên tục, nên hai nhân vật lệch nhau 0,5 bán âm sẽ nghe gần như giống hệt — không tạo ra được sự đa dạng
mà nó nhắm tới.

**Hướng đúng để có thêm giọng mà không trả giá:** catalog có 14 preset, đang cast 8. Bốn preset bị loại vì
style `tin_tuc` (`Minh Đức`, `Minh Triết`, `Mai Anh`, `Thùy Dung`) chạy ở `pitch 0` nên **không trả giá
vocoder nào**. Rào cản thật: chúng **không có file preview**, nên UTMOSv2 không có baseline để chấm tương
đối. Muốn dùng thì phải sinh và khóa preview cho chúng trước.

### Cơ chế đa dạng giọng: dịch cao độ không làm được, dịch formant mới làm được

Người nghe tiếng Việt nghe thử cùng một câu ở `-6, -4, -2, 0, +2, +4, +6` bán âm — F0 đi từ 106 Hz lên
206 Hz, **gần gấp đôi** — và kết luận: **"không thấy sự thay đổi đáng kể về âm sắc"**, mong đợi là giọng
phải trầm hơn hoặc chóe hơn.

Đó không phải lỗi. Đó là **hệ quả tất yếu của thiết kế**: nhận diện người nói nằm chủ yếu ở **formant**
(hình dạng khoang miệng), không ở cao độ. `apply_pitch_variant` **cố tình giữ nguyên** spectral envelope
theo đúng invariant, nên kết quả chỉ có thể là *cùng một người nói cao/thấp hơn*, không bao giờ là người khác.

**Cơ chế pitch-only tự mâu thuẫn với mục đích của chính nó.** Nó tốn 0,2–0,8 MOS mỗi biến thể, làm segment
fail ASR gấp 3,4 lần, và đổi lại những giọng mà người nghe không phân biệt được. "23 voice profile từ 10
preset" thực chất chỉ là ~10 giọng phân biệt được.

**Dịch formant thì làm được.** WORLD đã tách sẵn spectral envelope; co giãn nó theo trục tần số cho ra giọng
trầm hơn (`formant < 1`, khoang miệng lớn hơn) hoặc chóe hơn (`formant > 1`). Người nghe xác nhận hướng này
đúng ngay lần thử đầu. Giới hạn dưới đã chạm: `0,82` nghe **tù bí**, méo quá độ.

### So sánh các cách dịch cao độ, và vì sao WORLD là lựa chọn đúng

| Cách | Cao độ | Formant | Thời lượng | Nhiễu |
|---|---|---|---|---|
| Đổi tốc độ phát (resample) | đổi | **đổi theo** | đổi | không có |
| Phase vocoder (STFT) | đổi | đổi theo | giữ | phasiness, nhoè transient |
| PSOLA / WSOLA | đổi | **giữ cứng** | giữ | rè khi dịch mạnh |
| **Source–filter vocoder (WORLD)** | đổi | **điều khiển riêng** | giữ | mất mát khi dựng lại (~0,27 MOS) |

Chỉ WORLD cho phép điều khiển cao độ và formant **độc lập** — bốn cách kia buộc chúng đi cùng nhau hoặc khoá
cứng formant. Đo thực tế cũng xác nhận: rubberband (có sẵn trong FFmpeg của project, chế độ giữ formant) **tệ
hơn WORLD 0,2–0,3 MOS** ở cả hai chiều dịch. Đừng đổi sang nó.

### UTMOSv2 không đủ tin cậy để xếp hạng biến thể giọng

Hai lần nó mâu thuẫn với tai người nghe: chấm bản gốc `3,231` cao hơn `-4` `3,118` trong khi người nghe thấy
`-4` hay hơn hẳn; và MOS không giảm đều theo mức dịch (`-4` cao hơn `-2`, `+6` cao hơn `+2`). Nó vẫn dùng
được để phát hiện audio hỏng, nhưng **không được dùng để chọn giữa các biến thể pitch/formant** — việc đó
phải do tai người quyết.

### Quyết định: bản đã dịch không bao giờ bị chấm

Mọi gate — Whisper, UTMOSv2, tín hiệu — chạy trên **bản gốc** do VieNeu sinh ra. Dịch cao độ/formant là bước
cuối cùng, ghi file rồi thôi. Cao độ không thể làm sai chữ, nên kiểm nội dung trên bản gốc là hợp lệ; và đây
chính là thứ đang làm segment bị dịch fail gấp 3,4 lần một cách vô cớ. Phần giữ lại duy nhất là ghi file an
toàn (`.part` + checksum + atomic replace) — đó là I/O đúng cách, không phải chấm điểm.

## v0.2.0-alpha.13 — cảm xúc chưa bao giờ tới được audio

### Phát hiện gốc: `emotion` chỉ là một phép tra bảng ra nhiệt độ

`VieNeu.infer()` nhận `text`, `voice`, `style` và tham số lấy mẫu. **Không có tham số cảm xúc
nào.** Trước đây `emotion` được tra vào `EMOTION_TEMPERATURE` để ra một con số `temperature`,
`intensity` cộng thêm `0.015` mỗi bậc vào cả `temperature` lẫn `top_p`, `pace` cộng một offset nữa.

Bằng chứng quyết định — cùng câu, cùng giọng, cùng seed, chỉ đổi nhãn cảm xúc:

| emotion | temperature | sha256 audio |
|---|---|---|
| `sad` | 0.700 | `12365d2da85b4cc2` |
| `tender` | 0.700 | `12365d2da85b4cc2` |
| `happy` | 0.840 | `5628ca7e863cb50c` |
| `afraid` | 0.840 | `5628ca7e863cb50c` |
| `angry` | 0.860 | `ca8824b37b634ebf` |
| `surprised` | 0.860 | `ca8824b37b634ebf` |

Câu đánh dấu `angry` và câu đánh dấu `surprised` là **cùng một file, giống hệt từng bit**.
Nhãn cảm xúc chọn một trong 8 mức ngẫu nhiên, không chọn một cách diễn đạt.

### Nó không chỉ vô dụng mà còn có hại

Người nghe tiếng Việt chấm mù 4 cặp `neutral` vs cảm xúc-đã-phân-tích: **2 cặp neutral tốt hơn**,
1 cặp như nhau, 1 cặp thua. Khi tách riêng `intensity`, nhận xét là *"C nghe như lỗi"* — và đúng
file đó dài 1.60s trong khi cùng câu ở các mức khác chỉ 1.12s. Đó là sinh hỏng do nhiệt độ cao,
không phải nhấn mạnh.

Vì thế mọi segment giờ sinh ở **một nhiệt độ cố định 0.74** — đúng giá trị `neutral` vốn dùng cho
phần lớn sách. Các trần hạ nhiệt có chủ đích vẫn giữ: clarity repair, câu ngắn, vocalization.

**`pace` giữ ảnh hưởng lên `silence_p`** và **`volume` giữ mức LUFS** — hai thứ đó là hiệu ứng thật,
không phải ngẫu nhiên đội lốt.

### Lỗi ngủ đông lộ ra khi sửa: clarity repair chưa từng chạy

`CLARITY_MAX_TEMPERATURE = 0.78`, cao hơn nhiệt độ `neutral` là `0.74`. Mà `neutral` chiếm 71% số
đoạn. Nghĩa là chế độ giảm nhiễu khi ASR không xác nhận được **chưa bao giờ có tác dụng** với phần
lớn sách, và sau khi cố định nhiệt độ thì sẽ vô tác dụng hoàn toàn. Đã hạ xuống `0.66`.

Test giờ khoá **quan hệ** (`clarity < generation`) chứ không khoá con số, để không tái diễn.

### Lỗi chí mạng: một dòng thoại giết cả cuốn sách

Run thật 95 batch chết ở batch 30:

    Phân tích bắt buộc thất bại ở batch 30: nhận 0/1 segment
    lỗi cuối: DIRECTOR_FIELD_MISMATCH fields=intensity

Batch còn **1 segment**, cạn 3 lượt vì host và model không thống nhất `intensity` của một dòng —
trường không hề tới audio. Batch một segment không chia nhỏ được nữa → **sập cả run**.

Với 915 chương ≈ 18.000 batch, bất kỳ dòng nào cũng có thể giết nhiều ngày chạy.

Đã sửa: batch không chia nhỏ được nữa **và** mọi bất đồng còn lại chỉ nằm trong
`INAUDIBLE_DELIVERY_FIELDS = {emotion, intensity}` thì đi tiếp kèm cảnh báo. Đường dự phòng
`_heuristic(row)` vốn đã nằm ngay dưới nhánh raise — máy móc có sẵn, chỉ là `required` từ chối dùng.

### Chi phí thật của việc kiểm duyệt cảm xúc

Đo trên run thật: **~2,3 lượt gọi LLM mỗi batch**, tức hơn nửa công việc của Ollama là làm lại.
Lý do áp đảo là `emotion=neutral mâu thuẫn với cue trực tiếp`.

Host quét regex ra cue **trước khi gửi batch** nhưng giữ im tới lượt retry. Đưa tập cảm xúc cho
phép vào **request đầu tiên** (cùng hàm mà bộ adjudicate dùng):

| | trước | sau |
|---|---|---|
| lượt gọi LLM / batch | 2,31 | **1,71** |
| batch phải làm lại | 15/16 (94%) | **8/17 (47%)** |
| trượt `semantic delivery` | 21 | **7** |

**Giảm 26% số lượt gọi LLM.**

### Host từng áp cảm xúc ngược với văn bản

Bộ triệt tiêu cue phủ phủ định, cấm đoán, quá khứ, siêu ngôn ngữ — nhưng **thiếu nhóm chấm dứt**.
Nên *"Thu lại vẻ kinh ngạc"* (thôi kinh ngạc) bị đọc thành **đang** kinh ngạc, và model trả lời
đúng thì bị bắt làm lại.

Cố ý **không** gộp `nén`/`giấu`/`kìm`: cảm xúc bị nén thì vẫn còn đó, chỉ bị ghìm lại.

Mọi động từ chấm dứt đều phải được thêm vào **bộ chặn phủ định kép**, nếu không *"không thôi kinh
ngạc"* sẽ bị hiểu ngược. Có test cho từng động từ theo cả hai chiều.

### Bẫy escape đã mất hai vòng debug

Viết `\b` qua thiếu một tầng escape thì nó thành **ký tự backspace `\x08`**. Pattern trông đúng
trong source nhưng đòi khớp một ký tự điều khiển không văn bản nào có → **luật chết âm thầm**.
Đã thêm test quét mọi `SCOPED_AFFECT_*` để không tái diễn.

### Perceptual QA song song: 3,08x, giống hệt từng bit

Chấm WAV là **hàm thuần đọc file**. Chỉ `_score` ra process con; mọi ngưỡng, baseline và phán
quyết ở lại process cha, đúng thứ tự cũ.

Nhưng phát hiện kèm theo quan trọng hơn: **số luồng torch làm đổi điểm UTMOSv2** (~5e-07), vì torch
cộng các mảnh matmul theo thứ tự luồng nào xong trước. Điều này **đã đúng từ trước khi có pool** —
điểm UTMOSv2 vốn phụ thuộc số core của máy.

Nó thành lỗi khi take được chấm ở con còn baseline chấm ở cha: phán quyết là **hiệu** của hai số
đến từ hai chế độ số học khác nhau. Lần chạy đầu lệch 11/16 file. Sửa bằng cách ghim luồng **bên
trong verifier** (`_pin_threads`), để cha và con giống nhau **theo thiết kế**.

**Bài học về công cụ đo:** benchmark khi đó so kết quả đã `round(..., 4)` nên báo "identical" ở mọi
cỡ pool — và tôi đã tin. Một phép so không nhìn thấy được sai khác thì tệ hơn không so. Unit test
cũng không bắt được vì chúng dùng model giả trả số cố định. **Việc gì đụng số học dấu phẩy động thì
phải kiểm chứng bằng dữ liệu thật.**

### Chính sách vs cơ chế

`AFFECT_CUE_DISAGREEMENT_BLOCKS = False` là **chính sách**. Cơ chế retry vẫn sống và vẫn dùng cho
confidence và source-kind. 12 test hồi quy cũ bật cờ này lên để giữ nguyên giá trị, thay vì bị viết
lại hay xoá đi.

Nếu sau này có engine đọc được cảm xúc thật thì bật cờ lên, và trường `emotion` vẫn được phân tích
và lưu sẵn — nó không tốn thêm lượt gọi LLM nào, vì cùng lượt đó còn phải gán **người nói**, thứ
không regex nào làm được.

### Hướng duy nhất để có diễn xuất cảm xúc thật

Mỗi preset giọng VieNeu là một `ref_audio` đã nạp sẵn, gồm `speaker_emb` (192 chiều, **danh tính**)
và `codes` (**token âm thanh của đoạn mẫu — cách nói**). `voice=` và `ref_audio=` đi chung một
đường.

Nên cảm xúc thật phải đi qua `ref_codes`. `infer()` nhận `voice` dạng dict, nên về lý thuyết ghép
được `speaker_emb` của giọng này với `codes` của mẫu khác. Chưa thử, và khó ở chỗ **không có sẵn
bản thu cảm xúc** của các preset này.

**Output:** `D:\Novels\Audiobooks\_versions\v0.2.0-alpha.13b\alpha13b_59fc17e60a` (chương 000–003).

## v0.2.0-alpha.12 — dải formant tính theo register, đặt tên ranh giới nguồn

### Dải formant phải tính lại sau khi đã chỉnh F0

Người nghe: *"sau khi đã -4 f0 thì giọng thanh bình là một giọng trầm rồi, lúc này range paraat
phải tính lại. .86 tôi nghe hơi trầm quá"*.

Đây là lỗ hổng thật trong mô hình cũ. Dải formant được tính **chỉ từ giải phẫu** — chiều dài khoang
miệng suy ra từ F3. Nhưng cảm giác "người nói to/trầm" đến từ **cả F0 lẫn formant**, và hai thứ đó
rút từ cùng một ngân sách. Một preset đã bị hạ register thì đã tiêu mất một phần ngân sách ấy.

Giải phẫu **không thể tự thấy điều này**: hạ F0 bằng WORLD giữ nguyên spectral envelope, nên khoang
miệng ước lượng sau khi hạ đúng bằng trước khi hạ. Đo lại trên audio bao nhiêu lần cũng ra con số cũ.
Hệ số quy đổi bắt buộc phải lấy từ tai người nghe.

Đo được: Thanh Bình sàn `0.86` trên bản gốc, sàn `0.90` sau khi hạ `-4`. Vậy **1 bán âm ≈ 0.01
formant** (`REGISTER_FORMANT_TRADE_PER_SEMITONE`). Cả cửa sổ dịch chuyển lên, và giới hạn của phép
biến đổi vẫn chặn trên.

Ba ràng buộc độc lập giao nhau, mỗi cái đến từ một nguồn khác nhau:

| Ràng buộc | Nguồn | Đo bằng |
|---|---|---|
| Giải phẫu | khoang miệng phải nằm trong khoảng người lớn (12,8–19,7 cm) | Praat đo F3 |
| Thuật toán | PSOLA xuống cấp khi rời xa 1.0 | tai — `−0.15/+0.20` nam, đảo lại cho nữ |
| Ngân sách trầm | F0 và formant cùng tạo cảm giác trầm | tai — 0.01/bán âm |

Kết quả: Thanh Bình `[0.90, 1.20]`. Preset ở register gốc không đổi. Tổng 55 giọng phân biệt được.

### Retry của analysis phải nói rõ ranh giới nào bị vượt

Một batch thật tiêu hết cả 3 lượt vào **một** segment rồi buộc phải chia đôi:

    ‘Tỉnh dậy, phải tỉnh dậy!’     kind_hint=thought

`_source_kind_transition_rule` trả `""` cho hai trường hợp — nguồn là `thought` mà model muốn đổi, và
nguồn là narration mà model muốn gọi là `dialogue`. Mà `if self.rule:` nghĩa là rule rỗng **bị bỏ hẳn
khỏi payload**. Model chỉ nhận được "kind sai", không có gì để sửa theo, nên nó lặp lại đúng câu trả
lời cũ cho tới khi hết lượt. Chiều `dialogue` thì có rule tên hẳn hoi từ đầu.

Đặt tên chỉ ở **nhánh feedback**. Hàm rule vẫn trả `""`, vì rule khác rỗng ở đó sẽ **kích hoạt nhánh
source-kind override** ở tầng critic, mà provenance lưu trong `database.py` chỉ chấp nhận đúng hai
rule đang sở hữu một lock. Có test khoá riêng điều này lại.

### Quy trình: worktree để vừa chạy vừa sửa

Sửa file trong `QUALITY_IMPLEMENTATION_FILES` giữa lúc đang chạy làm đổi `quality_policy_hash`, khiến
candidate đã commit thành lạc hậu. Trước đây điều đó buộc phải chọn: hoặc chạy, hoặc sửa.

Nay có `D:\Novels\Ebook Reader_dev` (git worktree, branch `dev/alpha13`), dùng chung venv và model qua
junction `_internal/runtime`. Cây chính chạy, cây dev sửa.

**Giới hạn cần biết:** junction dùng chung venv, nên **nâng cấp package thì cả hai cây cùng đổi**.
Code thì cô lập, dependency thì không. Muốn thử nâng package trong lúc đang chạy thì phải tạo venv riêng.

### Vòng lặp phát triển đang dài 9 tiếng — và tại sao

App phân tích **trọn cuốn** rồi mới tổng hợp audio. Đo trên run 20 chương: 398 batch, 0,72 batch/phút
→ **8,8 giờ analysis trước khi có một giây audio nào**.

Nghĩa là một run 20 chương không dùng được để lặp chất lượng. Run phát triển nên lấy **4 chương**
(≈80 batch, ≈1,8 giờ) để còn nghe được đầu ra trong ngày.

### Nút thắt đổi theo giai đoạn

| Tài nguyên | Analysis | Synthesis | Tổng |
|---|---|---|---|
| GPU | 30–48% | 14–18% | 100% |
| VRAM | **6,66 GB (82%)** | 1,30 GB (16%) | 8,15 GB |
| CPU | 13 core | 0,8 core | 32 core |

Analysis nghẽn VRAM, synthesis rảnh mọi thứ. Số worker song song **không được** là hằng số.

Và analysis chạy với `OLLAMA_NUM_PARALLEL=1` — trần cứng, mọi request xếp hàng dù pipeline gửi bao
nhiêu. Project tự khởi động `ollama serve` với env kế thừa nên biến này đặt được.

**Output:** `D:\Novels\Audiobooks\_versions\v0.2.0-alpha.12\alpha12_beafd838b2` (chương 000–019,
dừng giữa chừng ở analysis batch 15/398 — cố ý, để đo Ollama khi GPU rảnh).

## v0.2.0-alpha.11 — bỏ giọng miền Trung, một tên một cách đọc

**Bỏ giọng miền Trung khỏi phân vai** (quyết định của người dùng, người nghe được tiếng Việt). Bằng chứng
gián tiếp tôi đo được: preset Trung sai thanh ở **từ thường** chứ không ở tên riêng — `khốn kiếp` → `khôn kiêp`,
`thuần khiết` → `thuân khiệt`, `chân lý` → `trấn lý` — khác hẳn giọng Nam vốn chỉ sai ở tên và ở phụ âm s/x,
d/gi. Thanh điệu mang nghĩa từ vựng nên đây là chi phí cho **người nghe**, không riêng ASR.

Cách làm: preset vẫn nằm trong catalog (VieNeu có chúng, sách cũ có thể đã khóa chúng nên `preset_by_name`
vẫn phải resolve), chỉ không bao giờ được cast. Gộp về **một allowlist vùng miền duy nhất** `CASTING_REGIONS`
cho mọi vai — tham số `include_regional` trước đây chỉ có tác dụng duy nhất là thêm giọng Trung cho NPC.

**Chỗ suýt hỏng:** nhánh fallback trong `choose()` cho trường hợp cạn preset đúng giới tính quét **cả
catalog**, tức là sẽ đưa giọng Trung quay lại sách. Test mới phủ mọi đường dẫn tới preset chứ không chỉ
đường thông thường.

Giá phải trả: 45 giọng nhân vật phân biệt được giảm còn **36**.

Kèm theo: fix pronunciation lưu **theo từng từ** (xem mục trước) để một tên chỉ có một cách đọc.

### Bài học quy trình: tôi đã tự vi phạm quy tắc của chính mình

Commit này sửa `analysis.py` **trong lúc run alpha.10 đang chạy** — đúng thứ mà `DEPENDENCIES.md` và
`AGENTS.md` đã cấm. Hậu quả đã kiểm chứng: pipeline tính policy hash **một lần lúc khởi tạo** nên run đang
chạy không chết, và tag `v0.2.0-alpha.10` vẫn trỏ đúng tree mà run khởi động từ đó, nên provenance của kết
quả vẫn đúng. Rủi ro duy nhất: **nếu run đó crash thì không resume được nữa.**

Quy tắc rút ra, cụ thể hơn cái đã ghi: sau khi khởi động một run, **không commit gì vào
`QUALITY_IMPLEMENTATION_FILES` cho tới khi run kết thúc.** Việc phát hiện thêm lỗi trong lúc chờ là bình
thường — hãy ghi nó vào file này và để đó, đừng sửa ngay. Một phiên bản = một tập thay đổi mạch lạc + đúng
một lần chạy chứng minh nó.

### Điều tra: giọng địa phương có phải vấn đề không? — Không, biến thể pitch mới là

Câu hỏi xuất phát từ việc Whisper mắc lỗi thanh điệu hệ thống. Đo trên 199 segment của alpha.9:

| Vùng | n | WER trung vị | MOS trung vị | delta so với baseline của chính nó |
|---|---|---|---|---|
| Bắc | 178 | 0,046 | 2,995 | **−0,339** |
| Nam | 17 | 0,250 | 2,487 | **−0,178** |
| Trung | 4 | 0,309 | 2,949 | **+0,433** |

Thoạt nhìn giọng Nam tệ hơn hẳn. Nhưng ba lần kiểm chéo lật lại kết luận đó:

1. **Loại nhiễu narrator**: chỉ so thoại với thoại, giọng Nam vẫn có WER 0,250 so với 0,089 của Bắc.
   Vậy chênh lệch WER là thật.
2. **Nhưng MOS tuyệt đối thấp là do trần của preset, không do vùng.** Baseline preview:
   `Phạm Tuyên 3,389 · Thục Đoan 2,959 · Đoan Trang 2,842 · Ngọc Linh 2,770 · Thanh Bình 2,534 ·
   Quang Sơn 2,529 · Ngọc Trân 2,503 · Xuân Vĩnh 2,489 · Thái Sơn 2,427`.
3. **So với baseline của chính nó, giọng Nam bám sát hơn giọng Bắc** (−0,178 so với −0,339). Pipeline
   không làm hỏng giọng Nam.

**Kết luận: WER cao của giọng Nam là thiên lệch của thước đo, không phải lỗi audio.** Whisper được
huấn luyện chủ yếu trên giọng Bắc chuẩn. Bỏ giọng tốt để chiều một thước đo lệch là tối ưu nhầm đối tượng.

### Thủ phạm thật: biến thể pitch, và giới hạn hiện tại đặt sai tiêu chí

Tách baseline theo từng mức pitch mới lộ ra vấn đề:

| Preset | pitch 0 | pitch −1 | mất |
|---|---|---|---|
| **Ngọc Linh** (Bắc) | 2,770 | **1,599** | **−1,17** |
| Trúc Ly (Bắc) | 2,596 | 1,875 | −0,72 |
| Đoan Trang (Bắc) | 2,842 | 2,124 | −0,72 |
| Thanh Bình (Bắc) | 3,052 | 2,534 | −0,52 |
| Thục Đoan (Nam) | 2,959 | 2,532 | −0,43 |
| Xuân Vĩnh (Nam) | 2,821 | 2,489 | −0,33 |

`PRESET_MIN_PITCH_SEMITONES` giới hạn pitch theo **khả năng dịch cao độ** đo trên preview, chứ không theo
**cái giá phải trả về độ tự nhiên**. Ngọc Linh được phép xuống `-2` trong khi chỉ `-1` đã mất 1,17 MOS —
lớn hơn cả ngưỡng review `-0,80` của pipeline.

Cần thêm ràng buộc: loại tổ hợp (preset, pitch) có baseline tụt quá ngưỡng so với pitch 0 của chính preset
đó. Số liệu này đáng tin vì baseline là thuộc tính của **chính file preview**, đo tất định, không phụ thuộc
nội dung sách — nên tái lập được mà không cần chạy lại cả cuốn.

Cảnh báo về cỡ mẫu: `Nam n=17`, `Trung n=4` là quá nhỏ để kết luận về vùng miền. Nhưng bảng pitch ở trên
không chịu hạn chế đó, vì mỗi ô là một phép đo tất định trên một file preview cố định.

## v0.2.0-alpha.10 — gỡ hai lỗi chặn xuất bản

Chốt sau khi đọc hết evidence của lần chạy alpha.9. Chi tiết bằng chứng nằm ở mục alpha.9 bên dưới.

**1. Anchor tên riêng thôi giữ quyền chặn publish.** Whisper viết lại tên đọc đúng theo âm Việt thành chính
tả tiếng Anh, nên chính tả nó chọn không phải bằng chứng về phát âm. Bốn thay đổi đi cùng nhau:

- So khớp **chuỗi phoneme tiếng Việt**: `Giôn` và `dôn` cùng ra `zˈon` nên khớp. Vẫn là phép so bằng —
  `Lucy` (`lˈuːsi`) vẫn không thỏa anchor của `Lucien` (`lˈuːʃən`).
- Metric canonical canonical hóa anchor **không khớp** ở cả hai vế, để bất đồng về tên thôi bị tính lỗi hai
  lần. Trước đây nó vừa bị anchor bắt vừa làm phồng WER — chính điều này làm câu như
  *"Lúc chia tay, Iven len lén hỏi Lucien đầy tò mò"* fail ở WER 0,357 dù **mọi từ thường đều đúng**.
- Miễn trừ chỉ áp dụng khi còn ≥ 4 token thường. Bỏ tên khỏi *"Anh Lucy"* thì không còn gì để kiểm, nên câu
  ngắn giữ nguyên quyền hard-fail.
- Repair vẫn chạy đủ vòng; chỉ trạng thái cuối đổi từ `failed` sang publish kèm
  `ASR_LOCKED_NAME_ANCHOR_REVIEW`.

Dự đoán trên chính dữ liệu alpha.9: 9/15 segment fail sẽ pass nhờ hạ anchor xuống review, và phần lớn 6 ca
còn lại sẽ pass nhờ thôi tính lỗi tên hai lần — chỉ ca hỏng thật (`Simon` → "sái mưu", cùng
*"báo tin tới trang viên"* → *"bảo tiếng tự trắng viếng"*) là vẫn fail, đúng như mong muốn.

**Rủi ro đã biết và chấp nhận:** một tên bị TTS đọc sai thật, mà mọi từ còn lại vẫn đúng, giờ sẽ publish kèm
cảnh báo thay vì bị chặn. Không có cách nào phân biệt nó với ca từ chối nhầm chỉ từ transcript. Đổi lại là
sản phẩm xuất bản được chương; trước đó tỉ lệ fail 7,5%/segment nghĩa là **không chương nào từng publish**.

**2. Target loudness vượt quá khả năng vật lý của trần peak.** Cân mức là
`min(loudness_gain, peak_safe_gain)`, mà giọng nói có crest factor 17–20 dB:

| | đo được | target cũ | kết quả |
|---|---|---|---|
| Segment | crest median 17,6 dB, xấu nhất 20,6 dB | `normal -19,0` @ trần `-2 dBFS` | 77% chạm trần, lệch tới `-4,09 dB` |
| Chương | `-19,91 LUFS`, crest 17,91 dB | `-18,0 LUFS` @ TP `-2 dBFS` | cao hơn khả năng **1,91 dB** |

Chương ghép thử từ chính WAV của alpha.9 cho thấy lỗi thứ hai này tồn tại độc lập — chương sẽ fail loudness
ngay cả khi mọi segment đều đạt ASR. alpha.9 không lộ ra vì chương chết vì ASR trước.

Sửa: hạ đều anchor segment 6 dB (`soft -28,0 / normal -25,0 / loud -23,8`) và hạ target chương về `-20,0 LUFS`.
Vì chương được master về một mức chung ở cuối nên chỉ tương quan giữa các segment mới quan trọng; hạ đều thì
tương quan giữ nguyên nguyên vẹn và mọi segment đạt đúng anchor. **Không dùng nén động hay limiter** — thí
nghiệm cho thấy UTMOSv2 bất biến với mức âm lượng (lệch MOS trung bình `-0,006` ở `-6 dB`), nên không có lý do
gì phải làm méo waveform.

Tách `segment_endpoint_floor_dbfs` (`-51,0`, đo **sau** gain) khỏi `segment_active_floor_dbfs` (`-45,0`, đo
**trước** gain). Gộp chung sẽ âm thầm làm gate "endpoint còn hoạt động ở trần frame" mất độ nhạy đúng 6 dB —
mà log alpha.9 cho thấy gate này bắt lỗi thật.

`test_loudness_targets_stay_inside_the_peak_ceiling_speech_allows` khóa ràng buộc vật lý này lại bằng chính
crest factor đo được, để không ai đặt lại một target bất khả thi.

**Dependency:** `sea-g2p==0.7.20` thành pin trực tiếp vì `asr.py` giờ import thẳng.

## v0.2.0-alpha.9 — chịu được lỗi mạng Ollama, có công cụ chấm audio

**Bằng chứng dẫn tới thay đổi.** Lần chạy đầu tiên trên `Text_Tmp/000..007` chết ở
`stage=unrecoverable_error` với `last_error="Response ended prematurely"` sau khi mới phân tích được
2/805 segment. Đây là `ChunkedEncodingError` của urllib3: kết nối tới Ollama rớt giữa stream. Một sự cố
mạng thoáng qua đã giết cả job không người trông — đúng thứ mà một studio audiobook không được phép có.

**Thay đổi.**

- `analysis.py` chia lỗi Ollama thành hai lớp. Kết nối chết **trước khi nhận được ký tự response nào**
  là replay an toàn và được gửi lại tối đa `OLLAMA_TRANSPORT_RECONNECT_ATTEMPTS` lần. Stream đã sinh
  output thì không bao giờ replay.
- Transport fault vượt qua lớp replay trong một attempt critic đã reserve giờ tiêu đúng attempt đó
  (giống hệt crash sau reserve), ghi `ANALYSIS_CRITIC_TRANSPORT_FAULT`, rồi để vòng lặp durable đi tiếp.
  Ngân sách attempt vẫn chặn vòng lặp vô hạn và hết ngân sách vẫn rơi vào nhánh terminal/split cũ.
- `scripts/run_book_job.py` được đưa ra khỏi `runtime/` (thư mục bị gitignore) và reconfigure stdout sang
  UTF-8. Trước đó thread drain message chết ngay ở dòng log tiếng Việt đầu tiên vì stdout mặc định cp1252.
- Thêm `scripts/audit_audiobook.py`: chấm khách quan phần mà gate per-segment không nhìn thấy — độ tản
  tốc độ đọc trong chương, khoảng lặng **thực tế nghe được** ở mỗi mối nối, độ đồng đều loudness giữa
  narration và dialogue, và tính nhất quán voice/pitch theo nhân vật.

**Đã biết, chưa xử lý.** `AnalysisOutputBudgetError`, `AnalysisWallTimeoutError` và
`OllamaStreamIncompleteError` phát sinh **trong** lượt critic bền vẫn raise xuyên pipeline. Ngữ nghĩa
durable của chúng giống hệt transport fault (attempt đã bị tiêu), nên nhiều khả năng chúng cũng nên đi
tiếp thay vì kết thúc book. Chưa sửa vì chưa quan sát được trường hợp thật; đừng sửa mù, hãy đợi bằng chứng
từ một lần chạy.

### Số liệu đo được trong lần chạy alpha.9

Trên 29 batch đầu của chapter 000–001:

- **72% batch phải retry ít nhất một lần** (8 batch qua ngay, 14 batch cần 2 lượt, 7 batch cần cả 3 lượt).
- 46/53 lần từ chối đến từ `semantic delivery validation` — model đề xuất `emotion=neutral` cho câu có
  cue cảm xúc trực tiếp; 4 lần từ host affect adjudication, 3 lần từ director critic.
- Nghĩa là phân tích đang tốn khoảng **2,1× số lời gọi model** so với trường hợp lý tưởng.

**Đây là chi phí có chủ đích, đừng "tối ưu" nó đi.** Cách rẻ nhất để giảm retry là gửi sẵn cue mà host đã
phát hiện được vào prompt lần đầu. Nhưng làm vậy thì semantic gate không còn là một phép kiểm độc lập —
nó biến thành "model có làm theo gợi ý của host không". Giá trị của gate nằm ở chỗ model tự quyết rồi host
đối chiếu. `AGENTS.md` đã quy định: khi throughput xung đột với toàn vẹn output thì chọn toàn vẹn output.
Advisory `allowed_emotions` vì thế chỉ được gửi **sau** khi một candidate `neutral` bị từ chối.

Con số cần nhớ khi ước lượng thời gian: ở profile `high_quality`, phân tích chạy khoảng **4 segment/phút**
trên RTX 5060 Laptop với `qwen3:8b` (~24 token/s, GPU ~47%, VRAM 6,5/8 GB).

### Phát hiện chất lượng: peak cap đang vô hiệu hóa toàn bộ ý đồ loudness

Đo 107 segment đã commit của chapter 000–001:

| | |
|---|---|
| Segment chạm trần peak `-2 dBFS` | **82/107 = 77%** |
| Lệch trung bình so với target LUFS | **-1,22 dB** |
| Lệch xấu nhất | **-4,09 dB** |
| Crest factor (peak − LUFS) | median 17,6 dB · p95 19,7 dB · max 20,6 dB |

`normalize_segment_level` tính `gain = min(desired_gain, peak_safe_gain)`. Target segment hiện tại
(`normal -19,0`, `loud -17,8`, narrator `+0,5`) nằm quá sát trần peak `-2 dBFS`, trong khi crest factor
tự nhiên của giọng nói là 17–20 dB. Hệ quả: **peak cap thắng, và mức cuối của mỗi segment do crest factor
quyết định chứ không do quyết định của đạo diễn.**

Hậu quả nghe được, không chỉ là sai số:

- Hai segment `volume=loud` (target `-17,30`) ra `-19,41` và `-20,21` — **nhỏ hơn** narration `volume=normal`
  ở `-19,14`. Quyết định "đọc to hơn" tạo ra audio nhỏ hơn.
- Anchor `segment_narrator_offset_db = 0,5` bị xoá sạch.
- Loudness giữa các segment tản `3,04 LU` vì lý do không liên quan gì tới nội dung.

Vì chương được master lại về `-18 LUFS` ở cuối, **chỉ tương quan giữa các segment mới quan trọng**. Nên cách
sửa đúng là hạ đều toàn bộ anchor cho tới khi peak cap không còn chạm: mô phỏng cho thấy `-4 dB` đưa
99,1% segment về đúng target, `-5 dB` đưa 100%.

**Đã kiểm chứng trước khi chọn cách sửa:** UTMOSv2 gần như bất biến với mức âm lượng tuyệt đối. Hạ
`-2/-4/-6 dB` trên 8 segment cho lệch MOS trung bình `-0,008/-0,009/-0,006`, xấu nhất `-0,032` — so với
ngưỡng review `-0,8`. Nghĩa là hạ anchor **không** phải trả giá bằng điểm tự nhiên, nên không cần đụng tới
limiter hay nén động (vốn sẽ làm méo waveform).

**Cần đo tiếp trước khi sửa:** cùng ràng buộc vật lý đó có thể tái xuất hiện ở tầng master chương —
`-18 LUFS` với true peak `-2 dBTP` đòi crest factor ≤ 16 dB, thấp hơn crest thực tế của giọng nói.
Phải đo MP3 chương thật rồi mới chốt.

### `pace` không tới được audio — nhưng đo xong thì thấy chưa đáng sửa

`vieneu_sampling_for_segment` ánh xạ `pace` thành đúng hai thứ: lệch temperature `±0,03/0,04` và
`silence_p` (`slow 0,20 / normal 0,15 / fast 0,08`). Không có tham số tốc độ đọc nào cả — thư viện Python
của VieNeu không có (xem `DEPENDENCIES.md`). Đo trên 104 segment có audio:

| pace | n | articulation (âm tiết/s) | tỉ lệ lặng |
|---|---|---|---|
| fast | 4 | 5,41 | 20% |
| normal | 98 | 5,29 | 19% |
| slow | 2 | **5,60** | 23% |

`slow` đọc **nhanh hơn** `normal`. Quyết định `pace` của đạo diễn bị vứt đi.

**Nhưng chưa sửa, vì phân bố nói khác.** Trên toàn bộ 199 segment đã phân tích: `pace` là
**193 normal / 4 fast / 2 slow — 97% normal**. Hiện thực hóa `pace` bằng hậu xử lý tempo sẽ chạm tới
**3% segment**, trong khi lỗi loudness ở trên chạm tới **77%**. Xây hạ tầng tempo bất biến (candidate riêng,
provenance, dual-decode, test) cho một ca 3% là đặt sai chỗ công sức.

Ghi lại để người sau cân nhắc: khác với `emotion`, **`pace` và `volume` không có host gate tất định**.
Prompt có dặn "không mặc định mọi câu là normal", nhưng không có gì kiểm chứng. `emotion=neutral` bị từ chối
46 lần trong lần chạy này; `pace=normal` thì chưa bao giờ bị chất vấn. 97% có thể đúng với văn xuôi kể chuyện —
người đọc audiobook thật cũng không đổi nhịp liên tục — nên đừng ép nó đa dạng khi chưa có bằng chứng là nó sai.
Muốn kết luận thì phải nghe đối chiếu, không phải nhìn phân bố.

Phân bố các quyết định delivery khác trong cùng lần chạy, để tham chiếu:
`volume` 177 normal / 20 loud / 2 soft; `emotion` 143 neutral / 19 angry / 16 afraid / 9 sad / 6 surprised /
4 tired / 2 happy; `intensity` 106 số 0 / 42 số 1 / 39 số 2 / 12 số 3.

### Kết quả cuối lần chạy alpha.9: 15/199 segment fail, 0/2 chapter publish

| | |
|---|---|
| Segment đạt | 184 / 199 |
| Segment fail | 15 — **tất cả** đều `ASR_LOCKED_NAME_ANCHOR_MISMATCH` |
| Chapter publish | **0 / 2** |

#### Anchor tên riêng đang từ chối chính cách đọc đúng

Đọc evidence của cả 15 segment (bản `locked_spoken_v1` cuối cùng), 23 anchor trượt:

| surface | đọc là | Whisper nghe | đánh giá |
|---|---|---|---|
| Joel | Giô-en | `joanne` ×5 | TTS đúng, Whisper viết bằng chữ Latinh |
| Lucien | Lu-si-en | `lucienne`, `lucianne` | TTS đúng |
| Iven | Ai-vân | `ivan` ×3 | TTS đúng |
| Alisa | A-li-sa | `alyssa` ×2 | TTS đúng |
| John | Giôn | `dôn`, `dốn` | TTS đúng — `gi` và `d` **đồng âm** /z/ trong tiếng Việt |
| Wayne | Uên | `nè`, `warner` | lỗi thật |
| Lucien | Lu-si-en | `rusien` | lỗi thật |
| Alisa | A-li-sa | `xá` | lỗi thật |

Khoảng **13/23 là từ chối nhầm**. Nguyên nhân gốc là **sai lệch dụng cụ đo**: gate so *chính tả*
mà Whisper chọn cho một cái tên ngoại quốc đọc theo âm Việt, trong khi Whisper là model đa ngữ có
thiên lệch tiếng Anh nên viết lại thành tên tiếng Anh. Chính tả của Whisper **không phải bằng chứng
về cách phát âm**.

Hệ quả với sản phẩm: 7,5% segment fail, và chỉ cần một segment fail là cả chapter bị giữ lại. Với
915 chapter thì **không chapter nào từng được publish**. Đây là blocker số 1, trên cả lỗi loudness.

Bằng chứng cho thấy `Aalto`, `Alisa` khớp ổn định ở `locked_spoken_v1`; chuyển sang variant
`source_spelling_v1` thì chính chúng lại trượt (`An-tô` bị đòi phải nghe ra `aalto`). Nghĩa là nhánh
repair đổi variant đang làm tình hình xấu đi chứ không cứu được.

#### Lỗi rõ ràng, không cần bàn: cùng một tên có hai cách đọc đã khóa

| surface | spoken_form |
|---|---|
| `Lucien` | `Lu-si-en` |
| `Evans` | `E-vân` |
| `Lucien Evans` | `Lư-xi-ên Ê-van` |

Entry nhiều từ tạo ra cách đọc khác hẳn cho chính hai tên đó (`u`→`ư`, `si`→`xi`, `en`→`ên`).
Đã xác nhận nó thực sự được áp dụng vào `spoken_text`. Người nghe sẽ nghe cùng một nhân vật được gọi
là "Lu-si-en" ở chương này và "Lư-xi-ên" ở chương khác. Vi phạm thẳng invariant *"cùng một tên không
đổi cách đọc theo giọng, chapter, confidence threshold hoặc lần resume"*.

#### Bài học quy trình

**Không di chuyển thư mục project.** SQLite lưu đường dẫn WAV tuyệt đối; chuyển đi là mọi công cụ
audit mất dấu file. Từ alpha.10, tạo project thẳng trong `_versions/<tag>/` bằng `--output-root`.

**Output:** `D:\Novels\Audiobooks\texttmp_iter1_cbde22ef6b` (chapter 000–001).

## v0.2.0-alpha.16 — 2026-09-01

**Lần đầu một run đi trọn vẹn tới cùng.** 2/2 chương xuất MP3, exit 0, 76 verified + 3
cảnh báo cần nghe lại. Trước đó `VERSIONS.md` ghi "với 915 chapter thì không chapter nào
từng được publish".

### Bốn lỗi chặn xuất bản, tất cả đều có sẵn từ trước

Không lỗi nào do TTS song song gây ra — đã chứng minh bằng một run đối chứng chạy hoàn toàn
tuần tự (`parallel_workers: 1`) thất bại với **đúng cùng một lỗi đầu tiên**.

1. **Anchor phát âm lệch giữa hai biến thể** (`PRONUNCIATION_VARIANT_DRIFT.md`) — một cặp
   tự mâu thuẫn ship cùng commit `f5c8dd2`. 17/79 segment chết tất định.
2. **Cổng tốc độ đọc đo nhầm đại lượng** (`PACE_METRIC.md`) — nó đo mật độ dấu câu chứ không
   đo tốc độ. Câu ngắt nghỉ đúng bị phạt nặng gấp 260 lần.
3. **Cổng ASR chặn trên câu trả lời không ai lấy được** — Whisper không phiên âm nổi nhãn
   2–3 ký tự và bịa ra câu kêu gọi đăng ký kênh YouTube. Ngưỡng 10 ký tự đo từ 4528 segment.
4. **Cùng lỗi ASR đó ở nhánh thứ hai của cùng một hàm** — bản vá đầu chỉ chạm một trong hai.

### Hiệu năng: TTS song song

3 tiến trình, **2,16×**, GPU **23% → 76–90%** đo trong run thật. Đầu ra byte giống hệt bản
tuần tự, chứng minh trên 9 segment thật qua đúng đường `synthesize_atomic`. Bất biến "chỉ
tiến trình cha ghi SQLite" được bảo đảm bằng cấu trúc (`ReadOnlyVoiceDB`), không bằng quy ước.

### Giọng

Bé gái Ngọc Linh → Đoan Trang → Trúc Ly; bé trai Phạm Tuyên dẫn đầu. Đúc giọng trẻ em không
phân biệt giới. Thanh Bình, Thái Sơn, Thục Đoan đồng hạng đáy. Cơ chế mới: **phán quyết của
người nghe xếp trên mọi phép đo tính toán** — cần thiết vì các phép đo đã sai hai lần theo
hai hướng ngược nhau trong cùng một phiên.

### Bài học lặp đi lặp lại trong phiên này

- **Một sự thật viết ở hai nơi** gây thêm hai lỗi nữa (nâng tổng lên năm trong lịch sử dự án):
  bản vá ASR đầu tiên đặt cùng phán quyết ở hai lớp, và `publish_with_review` gọi tên nhánh
  thay vì suy từ phán quyết nên nhánh mới âm thầm không xuất bản.
- **Đo trên tập con sai thì kết luận ngược**: segment đầu tiên thử để chẩn lỗi phát âm lại
  PASS vì tình cờ không chứa lớp dữ liệu gây lỗi.
- **Benchmark quá ít việc thì đo tốc độ nạp model, không đo throughput**: 12 job báo 1,42×,
  48 job báo 2,16×.
- **Test soi văn bản mã nguồn là test dễ vỡ**: hỏng ba lần liên tiếp trong khi hành vi vẫn
  đúng. Đã thay bằng unit test cho chính hàm quyết định.
- **Một stand-in vi phạm vật lý là quả bom hẹn giờ**: audio giả trong test nhanh gấp 6 lần
  người thật, im lặng suốt cho tới khi có người siết phép đo.

**Output:** `D:\Novels\Audiobooks\_versions\v0.2.0-alpha.16\alpha16-pool_c05e09eb67`

## alpha.43 — kết quả cuối (2026-09-04 05:22)

`asr.engine = faster`, `num_ctx = 9.216`, NOAH khoá giới tính. Chạy xong: **2/10 chương xuất
bản**, 8 chương hỏng.

### Tốc độ

| | tổng | nghỉ | **làm việc** |
|---|---|---|---|
| alpha.32 | 7,41h | 1,41h (4 lần dừng, dài nhất 33 phút) | **6,00h** |
| alpha.43 | 3,34h | **0h** | **3,34h** |

**1,80× tính trên thời gian làm việc.** Không phải 2,2× của đồng hồ treo tường — alpha.32
có 1,41h dừng vì cổng tài nguyên, và alpha.43 chạy trên máy rảnh nên không dừng lần nào.
Biến kiểm (thời gian TTS mỗi việc, không dính engine ASR) cho 1,22×, nên phần quy được cho
engine và cho khối lượng việc nó tiết kiệm là khoảng **1,48×**.

Chi tiết theo pha: `docs/THROUGHPUT.md` — vòng sửa 8.016s → 3.860s, kiểm candidate
2.325s → 536s. Pha phân tích thì **chậm hơn** (3.851s → 4.490s) vì num_ctx, xem
`docs/VRAM_AND_CONTEXT.md`.

### Chất lượng: 9/10 chương giống hệt

| ch | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| alpha.32 | MP3 | hỏng | hỏng | MP3 | hỏng | **MP3** | hỏng | hỏng | hỏng | hỏng |
| alpha.43 | MP3 | hỏng | hỏng | MP3 | hỏng | **hỏng** | hỏng | hỏng | hỏng | hỏng |

**Chỉ chương 6 khác**, và alpha.32 xuất bản được nó *vì Whisper ảo giác* — bản ghi vô nghĩa
được miễn trừ, còn bản ghi gần đúng của faster-whisper thì bị chặn. Cơ chế và cả lớp 9
segment ấy: `docs/WHERE_A_RUN_SPENDS_ITS_TIME.md`.

### Engine có đổi điều máy nghe không: **1,6%**

So cả sách thì 88/944 bản ghi khác nhau (9,3%), nhưng con số ấy trộn hai chuyện. Tách theo
checksum âm thanh:

| | segment | bản ghi khác |
|---|---|---|
| **cùng một file âm thanh** | 837 | **13 = 1,6%** ← thuần tuý do engine |
| âm thanh khác nhau | 107 | 75 = 70,1% ← bản thu khác, không quy cho engine |

**Trên cùng một âm thanh, faster-whisper đồng ý với openai-whisper 98,4%.** Khớp với ước
lượng 1,3% đo trên chương 1-2 lúc đang chạy. Con số 9,3% bị thổi lên bởi 107 segment
(11,3%) có *âm thanh khác* — hệ quả của num_ctx đổi phân tích, không phải của engine.

Ảo giác giảm rõ: `TIMELINE_IMPOSSIBLE` 9 → 5, `UNVERIFIABLE_SHORT_TEXT` 6 → 4,
`ANCHOR_REVIEW` 41 → 37. Đổi lại: +1 `ANCHOR_MISMATCH`, +1 `MISMATCH_UNRESOLVED`,
+3 `PERCEPTUAL_NATURALNESS_REVIEW` (cái sau là do âm thanh khác, không phải engine).

### Kết luận

**Giữ `asr.engine = faster`.** Nó trả về 1,48× cho lần chạy, giảm ảo giác, và giữ nguyên
điều máy nghe được ở mức 98,4% trên cùng âm thanh. Cái giá là một chương — một chương trước
đó chỉ xuất bản được nhờ một bản ghi vô nghĩa được miễn trừ, và giờ chỉ cần một lệnh
`accept` là xong.

**Nhưng `num_ctx = 9.216` thì không giữ.** Nó làm pha phân tích chậm 16%, và nó đổi đầu ra
của phân tích đủ để 107 segment có âm thanh khác và một segment mất sạch audio vì bị gán dải
`fast`. Xem mục 3 và 7 của `docs/OPTIMISATION_QUEUE.md`.

## alpha.44 — kết quả cuối (2026-09-04 11:47)

`asr.engine = faster` (mặc định), `num_ctx = 7.168`, `tts.max_retries = 10`, cổng lùi dải
nhịp, sentinel tách khỏi hằng số. **3/10 chương xuất bản** — bằng alpha.32, hơn alpha.43.

### Con số thật sự đổi không phải số chương

| | chương xuất bản | **segment không có audio** | chỉ cần nghe là xong |
|---|---|---|---|
| alpha.32 | 3/10 | **3** | 7/10 |
| alpha.43 | 2/10 | 4 | 6/10 |
| **alpha.44** | **3/10** | **1** | **9/10** |

`max_retries = 10` cứu 2 trong 3 segment chưa từng có bản thu, nên chương 5 và 10 rời nhóm
"cần bản thu mới" sang nhóm "chỉ cần tai người nghe". **Một tối nghe giờ đưa sách từ 3/10 lên
9/10 thay vì 7/10.** Chỉ chương 9 ở lại, vì thang bậc `C » B » A » S » SS » SSS` là sai loại
văn bản cho thước đo nhịp, không phải thiếu lượt thử.

### Thời gian: nhanh hơn ở phân tích, chậm hơn ở tổng hợp - và lý do là một lỗi

| | tổng | nghỉ | làm việc | phân tích | sinh tok/s |
|---|---|---|---|---|---|
| alpha.32 | 7,41h | 1,41h | 6,00h | 3.846s | 56,4 |
| alpha.43 | 3,34h | 0h | 3,34h | 4.475s | 50,1 |
| alpha.44 | 4,08h | 0,27h | **3,81h** | **3.733s** | **57,6** |

Pha phân tích nhanh nhất trong ba lần (−742s so với alpha.43), nhưng tổng thời gian làm việc
lại **chậm hơn 0,47h**. Không phải do `max_retries`: cả sách chỉ thêm 7 lần thử lại.

Lý do là **pool TTS tắt vĩnh viễn sau một lần đọc VRAM**. `_synthesis_pool` từ chối dựng pool
khi VRAM không đủ hai worker, và chốt `_tts_pool_failed` - cùng cái chốt dùng cho lỗi thật.
alpha.44 đọc được 4.467 MiB đúng một lần, ngay sau chương 2, rồi tổng hợp **chương 3-10 tuần
tự**: TTS chính 2.233s → 4.270s, mất khoảng **2.037 giây** vì một khoảnh khắc.

Đã sửa trên `dev/alpha13` (`c0b70e3`), kèm một lỗi thứ hai mà test của nó lôi ra: khối
`except` báo `{"workers": workers}` trong khi `workers` được gán *bên trong* `try`, nên một
lỗi import hoặc lỗi đọc tài nguyên sẽ làm chính khối xử lý lỗi ném `UnboundLocalError` - biến
"không dựng được pool" thành "hỏng cả quyển sách", đúng thứ docstring của hàm hứa không bao
giờ xảy ra.

### Cổng lùi dải nhịp: đường thường gặp chạy, đường thật chưa

Không segment nào kích hoạt nó. Dòng lỗi của `c00009_s0000008` kết thúc bằng
`pace_band=already normal`, tức cổng được gọi và từ chối đúng cách mà không tốn lần tổng hợp
nào. Đường *thật sự hạ dải* vẫn chưa chạy trong một lần chạy thật.

---

### Kết quả chạy alpha.45: chết ở chương 2 sau 1h56, vì một hồi quy do chính bản sửa trước gây ra

Chạy 07:43 → 09:39 UTC. Phân tích **xong toàn bộ 948 segment**, tổng hợp xong chương 1, chết
giữa chương 2 với circuit breaker:

```
TTS circuit breaker opened after 3 identical failures:
  split part pronunciation materialization changed its boundary text
```

Số lần xuất hiện chuỗi lỗi đó: **alpha.43 = 0, alpha.44 = 0, alpha.45 = 7.** Hồi quy mới,
không phải lỗi tiềm ẩn lâu ngày.

#### Ba thứ phải xếp thẳng hàng mới nổ

`_synthesize_split` cắt một segment dài thành mảnh của text **đã materialize**, rồi
materialize lại từng mảnh và đòi kết quả không đổi. Chuỗi nhân quả:

1. `spoken_symbols_to_words` đổi `(Legendary)` thành `, Legendary,` — **thêm ký tự**.
2. Segment vì thế dài 174 ký tự, vượt cap 170 của bộ cắt.
3. Bộ cắt bèn cắt tại **dấu phẩy mà chính hàm ấy vừa tạo ra**.
4. Mảnh 0 kết thúc bằng dấu phẩy. Lượt materialize thứ hai gặp luật
   `,(\s*(?:[.!?…]|$))` — dấu phẩy đứng ngay trước `$` — và cắt nó đi.
5. `expected_part_text != piece` → hỏng. Ba lần → breaker.

alpha.43 và .44 không dính vì trước bản sửa ấy **không có dấu phẩy mới nào cho bộ cắt cắt vào**.

#### Bất biến bị bỏ sót: hàm phải ổn định trên mảnh của chính đầu ra của nó

Đây là điều tôi không nghĩ tới khi viết. Idempotent trên *cả chuỗi* là chưa đủ — đường sửa
chữa cắt chuỗi ra rồi chạy lại trên từng mảnh, mà **một luật neo `^`/`$` nhìn thấy biên của
mảnh, không phải biên của đoạn nó sinh ra từ đó**. Biên là thứ duy nhất một mảnh không thừa
hưởng từ đoạn cha.

Sửa bằng cách **bỏ mọi luật đọc biên chuỗi**. Việc dọn dẹp mà chúng làm nay làm *trước* khi
chuyển đổi: ký tự phân cách nằm ở hai đầu bị bỏ đi thay vì đổi thành dấu phẩy rồi cắt lại.
Cùng kết quả, nhưng ổn định theo cấu trúc — mảnh của text đã chuyển không còn ký tự phân cách
nào, nên luật ấy không thể bắn lần hai.

Đo trên cả sách thay vì trên ví dụ:

| | code cũ | code mới |
|---|---|---|
| segment kiểm tra | 948 | 948 |
| segment cắt được | 204 | 204 |
| **lệch biên** | **3** | **0** |
| không idempotent | 0 | 0 |

#### Hai thứ rơi ra từ bản sửa

- **Trim hai đầu suýt ăn mất vocal cue.** Ngoặc bao `[thở dài]` cũng là ký tự phân cách; bỏ
  ngoặc mở làm cue không còn được nhận ra và biến thành hai từ đọc thành tiếng. Đúng cái bẫy
  test anchor đã bắt lần trước — nó bắt được lần này nữa.
- **Bỏ trim dấu phẩy hai đầu thôi xoá dấu câu của tác giả.** 10 segment là câu thơ kết thúc
  bằng dấu phẩy (`'Sinh ra từ bóng tối, mang trên mình lời nguyền,'`); `.strip(",")` cũ xoá
  mất nhịp nghỉ mà tác giả cố ý đặt. Toàn bộ 10 khác biệt cũ↔mới đều là dấu phẩy được giữ lại.

#### Xác nhận được: chốt pool của alpha.44 đã hết chốt

Trong 1h56, pool TTS dựng thành công **4 lần** với 3 tiến trình, và đúng **một lần** tụt xuống
tuần tự:

```
VRAM còn 3798 MiB, không đủ cho pool TTS (3 worker mong muốn); tổng hợp tuần tự chương này.
```

`(3798 − 2733) / 917 = 1` worker, mà pool một worker thì vô nghĩa. Lúc đó máy đang mở Unity
(3 tiến trình) và Rider — đúng kịch bản chủ nhân từng phàn nàn là "mở Unity lên cái là fail".
**Nó không fail.** Nó hạ xuống tuần tự cho một chương rồi thôi; VRAM sau đó về 5343 MiB. Ở
alpha.44 chính khoảnh khắc này đã khoá pool suốt 8 chương và tốn 2.037 giây.

Giá phải trả cho một chương tuần tự là nhỏ: pool 3 worker chỉ nhanh hơn 1,12× (đo trong
docstring `TTS_POOL_MIN_BATCH`), nên không đáng phức tạp hoá bằng cách dựng lại pool giữa chương.

#### Vẫn chưa chạy lần nào trong thực tế

- **Phát hiện đọc 2 lần** (`repeated_utterance_score`): không segment nào chạm ngưỡng 0,35.
- **Lùi dải nhịp**: vẫn chưa segment nào đi vào đường hạ dải thật (giống alpha.44).

Ba dòng "repeated a critic-rejected candidate projection" trong log là chuyện khác — bộ phân
tích tự cắt batch, không liên quan tới âm thanh.

---

### Kết quả chạy alpha.46: lần chạy tốt nhất từ trước tới nay, và hai lỗi nó phơi ra

Chạy 05→06/09/2026. **Lần đầu tiên không segment nào thiếu bản thu.**

| phiên bản | segment có audio | MP3 xuất được |
|---|---|---|
| alpha.32 | 945 | 3/10 |
| alpha.43 | 944 | 2/10 |
| alpha.44 | 947 | 3/10 |
| **alpha.46** | **948** | **5/10** |

#### ASR tất định tuyệt đối trên audio giống hệt — và điều đó sửa lại một con số cũ

So alpha.44 với alpha.46: **947 segment chung, 837 (88,4%) có audio giống hệt từng byte.**
Trên toàn bộ 837 đoạn ấy, **bản ghi ASR trùng khít 837/837 — không một khác biệt nào.**

Điều này sửa lại cách dùng con số "~1,6% bản ghi khác nhau" vẫn được trích: nó đo **hai
engine khác nhau trên cùng audio** (openai-whisper so với faster-whisper), **không phải**
nhiễu giữa hai lần chạy. Giữa hai lần chạy, với cùng một engine và audio giống hệt, nhiễu
bản ghi là **0**. Đừng dùng 1,6% làm ngưỡng bỏ qua cho việc so sánh run-với-run nữa.

Hệ quả: **mọi khác biệt bản ghi đều truy được về khác biệt audio.** 82 bản ghi khác nhau,
tất cả đều nằm trong 110 đoạn có audio khác. Không có ngoại lệ nào.

#### Vì sao 110 đoạn có audio khác — quy tới cơ chế

| nguyên nhân | đoạn | |
|---|---|---|
| chỉ dẫn diễn xuất khác | **87** | 79% — nhiễu của pha phân tích |
| chuyển đổi ký tự (`»`, `↓`, ngoặc) | **15** | thay đổi thật, cố ý |
| **cách đọc tên đổi** | **7** | ba chỉnh âm chủ sách yêu cầu, xem dưới |
| cả hai | 1 | |

Nhóm thứ ba ban đầu bị tôi ghi là "chưa giải thích được". Truy tiếp thì hoá ra là kết quả
tốt nhất trong cả phép so sánh: **8/112 tên đổi cách đọc, và cả 8 đều là cải thiện**, không
có cái nào là trôi ngẫu nhiên.

| tên | alpha.44 | alpha.46 | chỉnh âm nào |
|---|---|---|---|
| `Spirit Essence Units` | E-xen **Du**-nít | **U-nít** | *"u-nít chứ không phải du-nít"* |
| `Hunters` | Hăn-**tờt** | **Hăn-tờ** | *"vờt là cái gì? tiếng việt làm gì có"* |
| `Arthur/Samael Kaizer Theosbane` | thê-ô-xờ-ban | **The-ô-bên** | đường ghép từ điển |
| `Lily Elderwing` | ê-lờ-đê-rờ-uinh | Eo-đờ-guynh | cụm phụ âm đầu |
| `Michael Godswill` | gô-đờ-xờ-uin | Gót-guyn | |
| `Soulbound Artifacts` | Xao-lờ-baon | Xôn-bao | |
| `Kim Luxara` | lu-xa-ra | Lu-xa-ra | viết hoa |

Cả ba câu chủ sách nói ngày 04/09 đều nghe được trong bản thu thật. `Theosbane` sẽ đổi lần
nữa ở alpha.47 thành **Theo-bên** (hai âm tiết) nhờ bản sửa đường ghép từ điển merge sau khi
alpha.46 đã chạy.

> Bài học nhỏ: đừng để một dòng "chưa giải thích được" nằm lại trong tài liệu. Bảy đoạn ấy
> nhìn như nhiễu còn sót, thực ra là bằng chứng ba yêu cầu của chủ sách đã thành hiện thực.

Bài học phương pháp: cách đo ngây thơ ("8,8% bản ghi khác nhau") **gán sai gấp năm lần**.
Nhóm chứng đối đúng không phải cả sách mà là *segment không chứa ký tự bị đổi* — nhóm ấy
cũng đổi 8,4%, nên phần quy được cho bản sửa chỉ là 2,9 điểm phần trăm. Truy tới audio rồi
tới nguyên nhân mới ra con số thật: 16/110.

#### Bản sửa `↓` chạy thật, nghe được

```
văn bản       : ↓ 10.000.000 Đơn vị Tinh hoa Linh hồn
alpha.44 nghe : 10 triệu đơn vị tinh hoa linh hồn          ← ký tự bị nuốt
alpha.46 nghe : giảm 10 triệu đơn vị tinh hoa linh hồn     ← đọc thành "giảm"
```

similarity 0,816 → 0,837. Đúng điều chủ sách yêu cầu.

#### Hai lỗi alpha.46 phơi ra, cả hai đều nghiêm trọng hơn bất kỳ tinh chỉnh nào

1. **`yield_light` chặn CPU vô điều kiện** trong khi `yield_heavy` chỉ chặn khi có sức ép
   thật. Chế độ "nhẹ" hoá ra khắt khe hơn chế độ "nặng", và pipeline xử lý bằng
   `time.sleep(2.0)` lặp vô hạn. Đo được: **0,38 segment/phút** so với 5,60 ở `maximum` —
   chậm 14,7 lần, kéo dài 112 phút chỉ vì chủ sách đang dùng máy. Xem
   `docs/WHERE_A_RUN_SPENDS_ITS_TIME.md`.

2. **Phán quyết của người nghe bị lần `resume` kế tiếp xoá sạch.** Acceptance nằm ở
   `listener_audio_acceptances`, hai cổng quyết định đọc `quality_checks`, và không cổng nào
   tra bảng kia. Bức tường mà `accept` sinh ra để gỡ quay lại sau đúng một lần resume. Xem
   commit `1f0ce37`.

Ngoài ra `build_review_page.py` có hàm `_accepted` được viết và **không bao giờ được gọi**,
nên trang review đưa 4/9 thẻ là những bản thu chủ sách đã duyệt rồi.

#### Vì sao alpha.46 dừng ở 5/10

Bản sửa lỗi (2) bắt buộc đổi vân tay chất lượng, mà resume dưới vân tay mới thì bị từ chối —
đúng thiết kế. Nó **không làm mất gì đạt được**: một lần resume *trước khi* sửa đã re-fail
đúng ba chương ấy, và chính lần thử đó lộ ra lỗi.

### alpha.48: bản sửa dấu `/` gỡ được một chương mà hai lần chạy trước phải hỏi tai người

`c00002_s0000037` — `Rare (Hiếm - B): Mạnh hơn / khó tìm hơn.` — chặn chương 2 ở **cả
alpha.46 lẫn alpha.47**. Nguyên nhân tìm ra từ chính dòng "máy nghe" trên trang review:

| | alpha.47 | alpha.48 |
|---|---|---|
| máy nghe | mạnh hơn **trên** khó tìm hơn | mạnh hơn**,** khó tìm hơn |
| similarity | 0,80 | **0,914** |
| cảnh báo | `PERCEPTUAL_NATURALNESS_REVIEW` — **chặn** | `ASR_LOCKED_NAME_ANCHOR_REVIEW` — được phép |

Chữ "trên" không phải giọng đọc bịa: tiếng Việt đọc phân số bằng "trên", và giọng áp cách ấy
cho mọi dấu `/`. Bản sửa chỉ đổi khi hai bên là chữ cái, nên `8.5/10` giữ nguyên.

Đáng ghi vì hai lẽ. Thứ nhất, **nó đổi hạng cảnh báo chứ không chỉ đổi điểm số** — từ loại
chặn sang loại chỉ ghi nhận — nên chương tự xuất mà không cần một lần nghe nào. Thứ hai, lỗi
này chỉ lộ ra khi đọc dòng "máy nghe" của trang review như một **nguồn dữ liệu**, không phải
như một thứ để người nghe đối chiếu rồi bỏ qua.

#### alpha.48 kết thúc: 7/10 chương có audio, và một cổng thứ năm lộ ra ở lần resume

Run chính (08:13 → 11:01) xuất **6 chương**, resume xuất thêm chương 8 khi mã hoá lại rơi
xuống dưới ngưỡng 1,0s. Trên đĩa: **1, 2, 4, 6, 7, 8, 9**. Thiếu 3, 5, 10.

**Watcher phán quyết đã làm đúng việc của nó.** Ba lần bắt kịp cửa sổ, mỗi lần trước cổng
chưa tới một phút:

| giờ | phán quyết chuyển | chương bị xét | cách |
|---|---|---|---|
| 10:07:13 | `c00005_s0000052` | 10:07:57 | 44s |
| 10:23:29 | `c00007_s0000074` | 10:24:35 | 66s |
| 10:50:00 | `c00009_s0000066` | 10:50:59 | 59s |

Chương 7 là bằng chứng rõ nhất: alpha.47 chết đúng ở segment ấy, alpha.48 xuất ngay lần đầu.
Biên 44–66 giây cũng cho thấy hạ nhịp poll từ 45s xuống 15s là đúng — ở 45s thì hai trong ba
lần là may rủi.

**Cổng thứ năm.** `resume` lúc 11:04 không xuất được chương 3; thay vào đó chương 7 và 9 —
đã xuất một tiếng trước — quay về `warning: MP3 must be rebuilt`. `recovery.py` quét mọi
segment ở mỗi lần resume và đòi một `quality_check` đạt; acceptance thì cố ý để phán quyết
của máy ở `fail`, nên nó requeue đúng những bản thu chủ sách đã nghe. Bốn cổng trước đã được
dạy đọc bảng acceptance; đây là cổng thứ năm.

**Không mất phán quyết nào** — requeue chỉ chạy lại ASR trên cùng bản thu, và cả 7 acceptance
vẫn khớp checksum sau khi dừng run. Nhưng vòng sửa chạy *sau* một lần ASR trượt thì **có**
cắt lại, và bản cắt lại làm phán quyết mất hiệu lực vĩnh viễn. Đã dừng run tại đó.

**Hai bản sửa cho alpha.49** (`c40215a`, `513ef1a`): chặn trần lặng hai đầu ở khâu ghép, và
cho `recovery.py` đọc bảng acceptance. Cả hai đổi vân tay chất lượng
(`b63e95be` → `9f7c21ce`), nên alpha.48 không resume được nữa — đánh đổi đã chấp nhận, vì
mỗi lần resume lại tiến gần hơn tới chỗ xoá mất công nghe của chủ sách.

**Còn chờ tai người:** `c00005_s0000013` ("Samael Kaizer Theosbane") và `c00010_s0000017`
("Arthur Kaizer Theosbane") — cả hai đều là anchor tên bị Whisper viết theo chính tả tiếng
Anh, xem `SHORT_NAME_PRONUNCIATION.md`.

### alpha.49: dừng giữa chừng vì một cái tên đọc hai kiểu

Chạy 11:33 → 12:45, xuất chương 1, đang dựng chương 2 thì dừng. **Cố ý dừng**, không phải sập.

Pha phân tích 3.845s (64,1 phút) — điểm dữ liệu thứ ba ở `num_ctx` 7.168, xem
`OPTIMISATION_QUEUE.md` mục 3.

**Lý do dừng.** `Theosbane` — họ của nhân vật chính — bị khóa hai cách đọc trong cùng một
quyển:

| | `Theosbane` đứng một mình | nguồn |
|---|---|---|
| alpha.47 | `theo-bên` | **`listener_choice`** — chủ sách sửa tay bằng `pronounce` |
| alpha.48 | `Theo-bên` | máy, **trùng nhờ may** (chỉ khác hoa/thường) |
| alpha.49 | `Thê-ô-ban` | máy, **lệch thật** |

Trong khi đó `Samael Kaizer Theosbane` và `Arthur Kaizer Theosbane` đều đọc `...theo-bên`.
Đếm trên văn bản: **11 lần đứng một mình** (chương 5, 7, 8, 10) so với **7 lần trong tên đầy
đủ**. Bốn trên mười chương sẽ đọc họ nhân vật chính sai so với cách chủ sách đã chọn.

**Vì sao dừng chứ không chạy nốt.** Còn khoảng 2 tiếng dựng audio để cho ra 4 chương đã biết
chắc là hỏng, và bản sửa động vào `analysis.py` nên đổi vân tay — tức không resume vào được
dù có muốn. Chạy tiếp là tiêu 2 giờ GPU cho thứ phải bỏ đi.

Bản sửa: commit `d919474`, xem `LISTENER_VERDICTS.md` và test
`tests/test_name_component_relock.py`. Điểm cốt lõi: `relock_machine_pronunciation` vạch ranh
giới ở **nguồn** chứ không ở khóa — máy được sửa phỏng đoán của chính nó, `listener_choice`
thì tuyệt đối không.

**Bài học chung.** Cách đọc một cái tên **không ổn định giữa các lần chạy**. Ba lần chạy cho
ba kết quả, và lần duy nhất đúng chắc chắn là lần có người sửa tay. Nên bất cứ cái gì phụ
thuộc "máy sẽ đọc tên này giống lần trước" đều là giả định sai.


### alpha.50: bản sửa tên được trang bị nhưng chưa có dịp dùng

Pha tên chạy lúc 15:17, khóa 19 tên còn lại. `name_component_corrections` tìm được **0 chỗ
mâu thuẫn** và `_reconcile_name_components` không sửa gì — **đúng như nó nên làm**:

| bề mặt | alpha.50 đọc |
|---|---|
| `Theosbane` | `Theo-bên` |
| `Samael Kaizer Theosbane` | `Xa-men cai-dờ **theo-bên**` |
| `Arthur Kaizer Theosbane` | `A-thờ cai-dờ **theo-bên**` |

Lần này máy bốc ra `Theo-bên`, chỉ khác `theo-bên` ở chữ hoa — mà bộ dò cố ý bỏ qua khác
biệt hoa/thường, nên không có gì để sửa.

**Nói thẳng: alpha.49 bị dừng để sửa một lỗi mà alpha.50 không tái hiện.** Bản sửa vẫn đúng
— lỗi có thật ở alpha.47 và alpha.49 — nhưng riêng lần chạy này thì không cần tới nó, và
~70 phút phân tích của alpha.49 là giá phải trả cho một quyết định dựa trên một lần bốc thăm.
Nếu gặp lại tình huống ấy: đếm xem cái tên xuất hiện bao nhiêu lần *và* nhớ rằng lần chạy sau
có thể tự bốc đúng.

Hệ quả: **reconciler vẫn chưa từng chạy thật.** Nó có test, nhưng chưa có bằng chứng sống.
Bốn lần bốc cho cùng một cái tên tới giờ: `theo-bên` (người sửa), `Theo-bên`, `Thê-ô-ban`,
`Theo-bên`. Cách chặn đứng cái xổ số ấy không phải reconciler mà là
`port_pronunciations.py` — gieo sẵn cách đọc trước khi chạy, dùng từ alpha.51.

## Casting trôi giữa các bản, và nó đắt hơn trôi cách đọc tên (đo 2026-09-06)

Đối chiếu `voice_profile_id` của cả 948 đoạn:

| đối chiếu | số đoạn đổi giọng |
|---|---|
| alpha.46 ↔ alpha.48 | 80 (**8,4%**) |
| alpha.47 ↔ alpha.48 | **0** |
| alpha.50 ↔ alpha.48 | 27 (**2,8%**) |

Ví dụ: `c00006_s0000028` đi từ `preset_ngoc_linh_f093_p+00` sang `preset_doan_trang_f108_p+00`
— khác cả giọng lẫn cao độ.

**Vì sao đắt.** `generation_seed = stable_int("segment::{stable_id}::{voice_key}::{salt}")`,
nên đổi giọng là **đổi seed là đổi audio**. Mỗi đoạn trôi kéo theo:

- phán quyết của chủ sách trên đoạn ấy **hết hiệu lực** (phán quyết gắn với bản thu);
- toàn bộ bằng chứng QA của đoạn phải chấm lại;
- và nếu đoạn ấy nằm trong chương đang chờ xuất, chương ấy quay lại vạch xuất phát.

27 đoạn nhiều hơn hẳn 3 cái tên trôi ở `port_pronunciations.py`, và cùng một hậu quả.

**Nguyên nhân đã tìm ra, và nó nằm trong code chứ không phải trong nhiễu.**

Hai tầng trôi, tầng dưới kéo tầng trên:

1. **Tập nhân vật trôi.** alpha.48 nhận diện 23 nhân vật có thoại, alpha.50 chỉ 19; chỉ 17
   tên chung. `THEOSBANE` và `RAM` là nhân vật ở alpha.48 mà không ở alpha.50; `IVEN` thì
   ngược lại.
2. **Bộ phân giọng phụ thuộc thứ tự.** Trong 17 tên chung, **17/17 giữ nguyên giới và tuổi**
   — thứ mà casting lẽ ra dựa vào — nhưng chỉ **12/17 giữ nguyên giọng**.

Đọc `character_registry.py` là rõ: hàm `rank` xếp theo `usage[name]`, tức **số lần preset đã
được dùng**, rồi `selected = min(candidates, key=rank)` và `usage[name] += 1`. Đó là một bộ
cấp phát **tham lam, có trạng thái**: giọng của một nhân vật phụ thuộc vào những nhân vật
được cast **trước** nó.

Nên chuỗi nhân quả là:

> phân tích ra tập nhân vật khác → thứ tự cấp phát dịch → 5/17 nhân vật chung đổi giọng →
> 27 đoạn đổi seed → đổi audio → phán quyết và bằng chứng QA mất hiệu lực

Điều này cũng giải thích vì sao alpha.47 → alpha.48 trôi **0 đoạn**: tập nhân vật y hệt nhau.

**Bản sửa: mang `canonical_name → voice_key` sang, gieo trước khi cast.** Nó đi vòng qua bộ
cấp phát cho mọi nhân vật đã biết, nên **miễn nhiễm với việc tập nhân vật trôi** — mỗi cái
tên tự mang giọng của nó. Bộ cấp phát chỉ còn lo những nhân vật thật sự mới. Cần mang cả
`pitch_semitones` và `formant_ratio`, vì hai cái đó cũng nằm trong voice_key.

Một nhân vật ứng **đúng một giọng** ở cả hai bản (0 nhân vật dùng >1 giọng trên 948 đoạn),
nên phép ánh xạ không mơ hồ.

#### Hai hướng sửa, và cái đắt hơn có lẽ đúng hơn

**A — mang casting sang** (`port_casting.py`, song sinh với `port_pronunciations.py`).
Gieo `canonical_name → voice_key + pitch + formant` trước khi cast. Rẻ, nằm trong `scripts/`,
không đụng file bị khoá, và giải quyết đúng triệu chứng. Nhưng nó là **một lớp băng**: bộ
cấp phát vẫn phụ thuộc thứ tự, và bất cứ nhân vật mới nào cũng vẫn có thể xê dịch những
nhân vật sau nó *trong cùng lần chạy đó*.

**B — bỏ tính phụ thuộc thứ tự khỏi bộ cấp phát.** `rank()` hiện xếp theo `usage[name]`, tức
trạng thái tích luỹ. Nếu thay tiêu chí phá hoà bằng một hàm băm ổn định của
`canonical_name`, thì giọng của một nhân vật chỉ phụ thuộc **chính nhân vật ấy** — mất một
nhân vật ở đầu không còn kéo cả dãy sau dịch, và casting tái lập được mà **không cần mang gì
sang cả**.

Cái giá của B: mất bảo đảm "trải giọng đều", vì hai nhân vật có thể trúng cùng preset. Nhưng
chính codebase đã nói cái đó xử lý được — *"Formant, not pitch, is what makes a reused preset
sound like a different person"* — và thang formant đã tồn tại sẵn cho việc dùng lại preset.

B đụng `character_registry.py` (file bị khoá) và **đổi giọng của cả quyển một lần**, nên phải
là một phiên bản riêng, có đối chiếu bằng tai trước sau. A làm được ngay và không mất gì.
Làm A trước để bảo vệ công nghe, nhưng **đừng nhầm A là đã sửa xong**: nguyên nhân gốc là
trạng thái tích luỹ trong `rank()`, và chừng nào nó còn thì casting vẫn là hàm của tập nhân
vật chứ không phải của nhân vật.

**Hướng sửa có sẵn hình dạng.** `book_status` đã có cờ `casting_finalized`, tức casting *đã*
được khóa trong phạm vi một project. Việc còn thiếu là mang nó **sang project mới**, đúng như
`port_pronunciations.py` mang cách đọc tên — gieo trước khi chạy thì audio ổn định, và công
nghe của chủ sách sống qua được các bản. Chưa làm; ghi ở đây vì nó là ứng viên lớn nhất còn
lại cho việc bảo vệ thứ tài nguyên khan hiếm nhất.

### alpha.50 khép lại: 6/10 chương, và bốn chương hỏng đều đoán trước được

Xuất được **1, 2, 4, 6, 8, 9** — 56 phút audio. Bốn chương hỏng:

| chương | chết vì | gỡ bằng |
|---|---|---|
| 3 | cổng thứ sáu (`c00003_s0000029`) | bản sửa code |
| 5 | `c00005_s0000013` chưa ai nghe | tai chủ sách |
| 7 | cổng thứ sáu (`c00007_s0000074`) | bản sửa code |
| 10 | cổng thứ sáu (`c00010_s0000016`) | code **+** tai (`c00010_s0000017`) |

**Cả bốn đều đã được dự báo đúng từ 17:15**, bằng quy tắc "chỉ phán quyết họ ASR mới chạm cửa
thứ sáu" (xem `LISTENER_VERDICTS.md`) — chứ không phải phát hiện dần qua ba tiếng.

**Thắng lợi đã kiểm chứng:** chương 8 xuất ngay lần đầu với lặng dài nhất **0,72s**, so với
1,02s (hỏng) ở alpha.48. Bản chặn lặng-hai-đầu cắt đúng 0,65s khỏi đúng bản thu đã khoanh
vùng. Xem `ONSET_CLICK.md`.

**Máy bận chi phối thời lượng.** Trên 263 phút chạy thật:

| | |
|---|---|
| bị siết | **147,8 phút — 56,1%** |
| trong đó `yield_heavy` | 92,5 phút |
| chờ RAM ở checkpoint | **34 phút** |

Nên **đừng so tổng thời lượng alpha.50 với bản nào khác**. Hơn một nửa lần chạy là nhường
máy cho chủ sách, và đó là bộ quản lý tài nguyên làm đúng việc — không phải ba bản sửa làm
chậm đi.

**Watcher phán quyết**: chuyển 21 lượt trong suốt run, thoát đúng lúc run kết thúc (bản sửa
chiều nay thay việc đọc `state.json` bằng đọc heartbeat trong SQLite — xem
`fix: reading a state file must not be able to kill the run writing it`).
