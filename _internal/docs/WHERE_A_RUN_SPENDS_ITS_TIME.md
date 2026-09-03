# Một lần chạy tiêu thời gian vào đâu

Đo trên alpha.25 (10 chương, 948 segment, 5.100 giây tổng). `quality_checks` không có cột
thời lượng, nên thời gian được quy theo đúng cách một pipeline tuần tự tiêu nó: mỗi khoảng
trống giữa hai check liên tiếp trong cùng một chương thuộc về giai đoạn của check sau.
Khoảng trống trên 600 giây bị loại vì đó là lúc nghỉ giữa các pha, không phải công việc.

## Bảng

| giai đoạn | lượt | giây | phần |
|---|---:|---:|---:|
| `segment_asr_decode_v1` | 2.032 | **3.870,4** | **60%** |
| `segment_perceptual_v1` | 979 | 2.537,9 | 39% |
| `chapter_post_encode_v1` | 10 | 50,1 | 1% |
| `segment_audio_v1` | 1.074 | 31,8 | 0% |

## Điều bất ngờ: ASR đắt hơn TTS

Cả dự án vẫn ngầm coi TTS là phần đắt nhất. Không phải. **Whisper tốn 3.870 giây, còn TTS
tốn 2.055 giây** — ASR gần gấp đôi TTS và là khoản lớn nhất của một lần chạy.

2.032 lượt giải mã cho 948 segment, tức 2,14 lượt mỗi segment. Đây **không** phải lãng phí:
lượt xác nhận chỉ chạy khi lượt đầu cho verdict MISMATCH hoặc INCONCLUSIVE
(`pipeline.py`, `verify_rows(..., confirmation=True)`), và các vòng sửa chữa thì đương nhiên
phải giải mã lại bản thu mới. Đã kiểm tra trước khi kết luận.

Đòn bẩy còn lại của ASR là `beam_size = 5` ở lượt chính (lượt xác nhận mới là greedy). Đảo
lại - greedy trước, beam khi nghi ngờ - có thể cắt lớn, nhưng nó đổi cả tập segment được
cho qua, nên đó là thay đổi ảnh hưởng chất lượng và phải đo, không phải khoản lấy không.

## Khoản lấy không: chồng lấn cảm thụ với ASR

Chấm điểm cảm thụ là **đọc thuần túy** - vào một file WAV, ra một con số - và chạy trên
**CPU**. Whisper chạy trên **GPU**. File WAV đã có từ lúc TTS xong, tức là trước khi Whisper
bắt đầu. Nhưng hiện tại chúng xếp nối tiếp: ASR xong hết chương mới tới chấm cảm thụ.

Trong **chín trên mười chương, thời gian ASR dài hơn thời gian cảm thụ**, nên toàn bộ phần
chấm điểm lọt được vào trong đó:

| chương | ASR (GPU) | cảm thụ (CPU) | lấy được |
|---|---:|---:|---:|
| 1 | 1,2s | 51,7s | 1,2s |
| 2 | 811,4s | 308,2s | 308,2s |
| 3 | 422,9s | 334,9s | 334,9s |
| 4 | 327,3s | 305,1s | 305,1s |
| 5 | 349,5s | 307,8s | 307,8s |
| 6 | 246,0s | 209,4s | 209,4s |
| 7 | 394,8s | 189,1s | 189,1s |
| 8 | 643,2s | 355,7s | 355,7s |
| 9 | 341,6s | 254,4s | 254,4s |
| 10 | 332,5s | 221,8s | 221,8s |
| **tổng** | | | **2.507,4s** |

Chương 1 là ngoại lệ vì đó là lần nạp model UTMOSv2 duy nhất (25,7s cho một check).

**Khoảng 42 phút mỗi lần chạy, không đổi một quyết định chất lượng nào**, vì các verdict
vẫn chạy trong tiến trình chính, theo đúng thứ tự cũ, với đúng ngưỡng cũ. Chỉ có việc chấm
điểm dời sớm lên.

## Cái bẫy phải tránh khi làm

Vòng sửa chữa của ASR **thu lại** segment, nên WAV đổi. Một điểm số chấm trước lúc sửa là
điểm của bản thu cũ. Hiện tại code không dính bẫy này chỉ vì prefetch xảy ra *sau* ASR;
dời nó lên trước thì bẫy mở ra. `prefetched_scores` đang khoá theo `wav_path`, mà đường dẫn
không đổi khi thu lại - **phải khoá theo `wav_sha256`** và bỏ mọi điểm có sha đã khác. Segment
bị sửa sẽ tự chấm trong tiến trình chính, đúng như đường đã có sẵn cho các file mà pool
không trả về.

Cách đo lại: `scratchpad/asr_vs_qa.py`. Lưu ý: check theo segment để `chapter_id` NULL và chỉ
ghi `segment_id`, nên phải nối qua bảng `segments`; và `created_at` là **float unix**, không
phải chuỗi ISO như tên cột gợi ý.

## Beam search: đo rồi, và nó không chỉ đắt - ở câu ngắn nó còn sai (2026-09-03)

Lượt giải mã chính dùng `beam_size = 5`; lượt xác nhận dùng greedy. Câu hỏi đặt ra không
phải "greedy nhanh hơn bao nhiêu" (hiển nhiên là nhanh hơn) mà **"hai lối có bất đồng về
bản thu nào chấp nhận được không"** - vì một lượt giải mã cho lọt bản tồi hoặc đánh trượt
bản tốt sẽ tốn một lần thu lại, xoá sạch phần tiết kiệm gấp nhiều lần.

Đo bằng `scripts/measure_beam_vs_greedy.py` trên chính WAV của alpha.25, cùng văn bản mong
đợi, qua đúng `verify()` mà pipeline dùng.

### 160 bản thu mọi độ dài

beam chậm hơn **1,84 lần** (0,92s so với 0,50s mỗi segment). Bất đồng đỗ/trượt 3/160.

| văn bản mong đợi | beam | greedy | ai đúng |
|---|---|---|---|
| "Hờ." | *"Hãy subscribe cho kênh Để không bỏ lỡ những video hấp dẫn"* | "Họ" | greedy |
| "tôi" | "Đôi." | "Tôi..." | greedy |
| câu dài về Rồng | nghe ra "rồng" | nghe ra "dòng" | **beam** |

### 120 bản thu ngắn hơn 2,5 giây

beam chậm hơn **1,47 lần**. Bảy bất đồng verdict, ba lần lật đỗ/trượt - **cả ba đều nghiêng
về greedy, không một ca nào beam thắng.** Thêm một ca nữa: tiếng thở dài "Haaa." được beam
đọc thành "Ah yeah.".

### Cơ chế, không phải trùng hợp

Beam mang nhiều giả thuyết rồi giữ chuỗi xác suất cao nhất. Với audio ít nội dung, **chuỗi
xác suất cao nhất là câu mẫu** - và câu mẫu của Whisper là câu mẫu YouTube. Đây là chế độ
hỏng đã được biết đến của Whisper, và phép đo tái hiện nó đúng như dự đoán.

### Đã làm

`beam_minimum_seconds = 2.5`: lượt chính dùng beam khi bản thu dài hơn ngưỡng, dùng greedy
khi ngắn hơn. Giữ tìm kiếm ở nơi có nội dung nuôi nó, bỏ ở nơi nó tự bịa nội dung. Nhanh
hơn là lý do nhỏ hơn; **đúng hơn mới là lý do chính**.

Lượt xác nhận vẫn greedy ở mọi độ dài - nó tồn tại để đưa ra một ý kiến *khác*, không phải
một ý kiến *dài hơn*.

### So hai lần chạy thì không kết luận được về bộ giải mã (alpha.32 vs alpha.25)

Chương 2, 77 segment, chỉ lượt giải mã đầu tiên (không xác nhận, không vòng sửa):

| | đỗ | lệch | không kết luận |
|---|---|---|---|
| alpha.25 (beam mọi độ dài) | 47 (61%) | 29 (38%) | 1 (1%) |
| alpha.32 (greedy dưới 2,5s) | 44 (57%) | 31 (40%) | 2 (3%) |

Thoạt nhìn tưởng thay đổi beam làm tệ đi. Xem từng ca thì **không ca nào chống lại greedy**:

- `c00002_s0000037` (2,48s): alpha.32 có similarity **cao hơn** (0,833 so với 0,800) nhưng
  vẫn trượt, vì trượt ở **neo tên khoá** chứ không ở similarity. Giọng đọc chữ "Rare" khác
  nhau giữa hai lần thu - alpha.25 nghe ra "ra", alpha.32 nghe ra "Gai".
- `c00002_s0000042` (**12,80s**): trên ngưỡng, nên **beam ở cả hai lần chạy**. Không thể do
  thay đổi này.
- `c00002_s0000067` (0,48s): văn bản chỉ là một chữ **"S"**. Cả hai đều cho ra vô nghĩa;
  alpha.25 ra "ừ ừ" và lọt qua, alpha.32 ảo giác một câu dài. Đây là lớp
  `ASR_UNVERIFIABLE_SHORT_TEXT` đã biết, không phải chuyện beam.

**Bài học về phương pháp:** alpha.32 thu lại toàn bộ âm thanh với seed và casting riêng, nên
đây là hai *tập bản thu* khác nhau chứ không phải hai *bộ giải mã* trên cùng bản thu. Một
so sánh giữa hai lần chạy không tách được bộ giải mã khỏi giọng đọc. Bằng chứng có kiểm
soát - 120 bản thu **giống hệt**, ba lần lật verdict, cả ba nghiêng về greedy - vẫn là bằng
chứng tốt hơn hẳn, và nó không mâu thuẫn với bảng trên.
