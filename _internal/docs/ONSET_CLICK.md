# Tiếng "tóp" đầu câu — lỗi âm tiết mở đầu

## Triệu chứng

Người nghe báo: chữ **"Mẹ"** ở **đầu câu** bị một tiếng động ngắn đè lên, *"như giọt nước
rơi vào bát inox"*, làm không nghe ra chữ. Cùng chữ đó **ở giữa câu thì nghe rất tốt**.

Đây là cùng một lỗi với thứ trước đó được ghi là "lỗi âm tiết đầu câu" — âm tiết mở đầu
nghe bị *lướt qua nhanh*, không trọn vẹn.

## Nguồn gốc: xổ số lúc sinh, không phải khuyết tật của giọng

Cùng preset (Thanh Bình), cùng câu, cùng mọi tham số — **chỉ đổi seed**:

| seed | bùng năng lượng đầu câu | bề rộng xung |
|---|---|---|
| 111111 | 2,89× | 10,8 ms |
| 333333 | 3,56× | 9,3 ms |
| 222222 | 3,74× | 13,9 ms |
| **424242** (người nghe báo lỗi) | **4,00×** | **5,8 ms** |
| **555555** | **6,03×** | **5,5 ms** |

Kết luận: lỗi nằm trong **đầu ra thô của model**, nên **hậu xử lý không sửa được**. Cách
chữa duy nhất là *phát hiện rồi sinh lại với seed khác* — và pipeline đã sẵn có cơ chế đó
(`_segment_candidate_seed_salt` đổi seed mỗi lần thử lại).

## Vì sao sáu phép đo trước đều trượt

Đã thử và **đều không bắt được**: lỗi quãng tám, đệm im lặng đầu file, jitter thanh điệu,
HNR, tỉ lệ transient toàn file, độ dài nhóm âm đầu tiên (phép cuối còn cho kết quả **ngược
chiều**, 1,76×, vì phân đoạn theo năng lượng gộp các âm tiết lại nên không cô lập được một
âm tiết).

Lý do chung: lỗi là **một xung ~5 ms**. Mọi phép đo trung bình hoá theo cả file hoặc theo
khung dài hơn đều làm loãng nó đến mức vô hình.

## Phép đo đúng: cao VÀ hẹp — thiếu vế nào cũng sai

`onset_click_metrics()` trong `audio_io.py` trả về hai số tại xung mạnh nhất trong **450 ms
đầu tiếng nói**:

1. **Tỉ lệ bùng** — năng lượng cửa sổ 5 ms so với cửa sổ 60 ms bao quanh
2. **Bề rộng** — thời gian xung còn ở trên nửa đỉnh

**Biên độ một mình vô dụng.** Trên 2500 đoạn thật đã được chấp nhận:

| phân vị | tỉ lệ bùng |
|---|---|
| 50% | 2,70× |
| 90% | 4,06× |
| 99% | 8,94× |
| max | 11,66× |

Đặt ngưỡng 4,0× đơn thuần sẽ bắt sinh lại **10,8% toàn sách**. Lý do: **phụ âm bật (t, k,
p) vốn LÀ một bùng năng lượng hợp lệ**.

**Phổ phẳng cũng vô dụng** — giả thuyết "tiếng tóp là dải rộng" đã bị bác bỏ bằng đo đạc:
độ phẳng phổ ≈ 0 ở *mọi* file kể cả file lỗi, vì tiếng nói luôn giàu hài âm ở cửa sổ này.
Bộ lọc theo phổ phẳng bắt được **0 đoạn** — vô hại nhưng cũng vô dụng.

**Bề rộng mới là thứ tách được.** Phụ âm bật kéo theo hơi bật và chuyển tiếp formant nên ở
trên nửa đỉnh **9–14 ms**; tiếng tóp xong trong **5 ms**.

Ngưỡng hiện tại: `ratio > 4.0` **và** `width < 6.0 ms`, chỉ xét trong 450 ms đầu (vì chính
người nghe xác nhận cùng chữ đó ở giữa câu thì tốt).

## Trạng thái: ĐÃ BỊ BÁC BỎ — chỉ ghi số, KHÔNG chặn

Nghe A/B đã bác bỏ bộ dò này. 12 đoạn nó chấm nặng nhất (9,8–11,7×) được người nghe trả
lời: **"a, b có tiếng gì đâu?"** — không phân biệt được với nhóm đối chứng sạch. Trên giọng
kể người lớn nó chỉ đang bắt phụ âm bật bình thường.

`onset_click_metrics()` vẫn còn và vẫn ghi số vào metrics, nhưng **không được phép làm hỏng
một đoạn nào**. Có test `test_the_measurement_never_fails_a_segment` khoá điều đó lại.

## UTMOSv2 cũng không bắt được lỗi này

Đã thử dùng UTMOSv2 làm trọng tài thay cho phép đo tự chế. Nó **xếp hạng ngược với tai
người nghe**:

| seed | UTMOS (sau biến đổi) | tai người nghe |
|---|---|---|
| 424242 | 1,942 (hạng 2) | **có tiếng tóp** |
| 333333 | 1,549 (hạng cuối) | **sạch tóp** |

Kết luận: với lớp khuyết tật này, **chưa có phép đo tự động nào đáng tin**. Mọi thay đổi
nhắm vào nó phải được tai người xác nhận trước khi vào đường chạy thật.

## Bài học phương pháp

Ghi lại vì đã trả giá: **chạy đối chứng trước, sửa sau**. Tiếng rè chữ "mẹ" đã bị đuổi qua
ba lần sửa hậu xử lý trước khi ai đó nghĩ đến việc nghe thử file thô — và file thô đã có
sẵn lỗi. Ba lần sửa đó đều vô nghĩa ngay từ đầu.

## Lặng ở hai đầu bản thu: cái hố một giây ở chương 8 (đo 2026-09-06)

alpha.48 chương 8 trượt `chapter_post_encode_v1` với "unexpected silence 1.02s". Con số ấy
**là lặng đầu của chính một bản thu**, nằm trước khoảng nghỉ 0,38s và sau đuôi 0,17s của bản
trước — tổng cộng **1,57 giây chết** giữa chương.

Không phải lỗi cách đọc:

| | seed | dài | lặng đầu |
|---|---|---|---|
| alpha.46 | 1878932885 | 2,08s | 0,51s |
| alpha.47/48 | 1670529513 | 2,64s | **1,02s** |

Cùng `text_sha256`, cùng `spoken_text_sha256`. Chỉ khác seed — mọi lần sửa file trong
`QUALITY_IMPLEMENTATION_FILES` đều đổi muối seed, và lần bốc mới giữ dấu ba chấm đầu câu lâu
gấp đôi. Câu đó mở đầu bằng "…", nên **nghỉ là đúng**; chỉ là nghỉ quá tay.

Phân bố trên 841 bản thu của alpha.48:

| | lặng đầu | lặng cuối |
|---|---|---|
| p50 | 0,11s | 0,17s |
| p90 | 0,12s | 0,21s |
| p99 | 0,22s | 0,23s |
| max | 1,02s | 0,44s |

**Đúng 2 bản** vượt 0,5s, và cả hai đều mở đầu bằng dấu ba chấm (bản thứ ba, 0,46s, cũng thế).

**Cách chữa: chặn trần ở khâu ghép, không phải thu lại.** Thu lại không chắc khỏi — alpha.46
bốc seed khác cho đúng câu ấy và vẫn ra 0,51s, tức vẫn quá ngưỡng. Cắt sạch thì mất đi cái
ngập ngừng mà dấu ba chấm đang đòi. `_cap_segment_edge_silence` cắt phần vượt quá **0,35s**
và chỉ cắt bản sao tạm: **file trên đĩa không bị đụng tới**, vì checksum của nó là khoá mà
một nửa bằng chứng trong dự án này được lưu theo, và lặng ở đầu không phải lý do để xét lại
cách đọc. Phần đã cắt được ghi vào `ChapterQualityMetrics.trimmed_segment_edges`.

0,35s + 0,38s nghỉ = 0,73s, vẫn nghe rõ là một quãng ngập ngừng.

### Kiểm trên chính chương đã trượt

Chạy `_cap_segment_edge_silence` qua đúng 151 bản thu thật của chương 8 alpha.48:

| | khoảng chết lớn nhất | lặng đầu lớn nhất |
|---|---|---|
| trước | **1,52s** — chương trượt | 1,00s |
| sau | **0,88s** — chương đạt | 0,36s |

**Đúng 1 trên 151 bản thu bị cắt**, tổng cộng 0,65 giây. Đó là toàn bộ can thiệp: một file,
0,65 giây, và chương từ trượt thành đạt. Cách đo lại: `scratchpad/verify_cap_on_chapter8.py`.

Đã nhập vào production ở `c40215a`.

### Nó bắn thật, và tôi đã mô tả quá nhẹ

Bốn chương đầu của alpha.50, đối chiếu với alpha.48:

| chương | lặng dài nhất (48 / 50) | đã cắt |
|---|---|---|
| 1 | 0,18 / 0,18 | – |
| 2 | 0,56 / 0,56 | – |
| 4 | 0,62 / 0,62 | `0000047.wav: đuôi 0,42s → cắt 0,07s` |
| 6 | 0,66 / 0,66 | – |

Docstring của test viết "trên hầu như mọi chương đây là đường không ai đi". **Sai ở mức độ**:
nó đi 1 trên 4 chương. Cắt ở **đuôi**, không phải đầu — phân bố đuôi có p99 0,23s nhưng đỉnh
0,44s, nên vượt trần 0,35s là chuyện thỉnh thoảng xảy ra, không phải ngoại lệ hiếm.

Điều đáng chú ý hơn: chương 4 ra **đúng 0,62s ở cả hai bản**, dù alpha.50 đã cắt 0,07 giây.
Nghĩa là khoảng lặng dài nhất của chương ấy nằm ở chỗ khác, và bản cắt **không đụng tới con
số nó sinh ra để bảo vệ**. Can thiệp đúng như thiết kế: nhỏ, đúng chỗ, không kéo theo gì.

Bốn chương giống hệt nhau giữa hai bản (0,18 / 0,56 / 0,62 / 0,66) cũng là thêm một lần xác
nhận pipeline tái lập được.
