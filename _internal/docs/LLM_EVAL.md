# Tìm LLM phân tích tốt nhất: đo, đáp án chuẩn, huấn luyện

Việc thường trực từ 19-09-2026, chủ sách giao: *"tìm ra llm tốt nhất, bất kể là có sẵn hay tự huấn luyện"*.
Tôi (Claude) chịu trách nhiệm làm **bộ đáp án chuẩn** (gold) cho khâu phân tích, rồi dùng nó để
1. so các model có sẵn với nhau, trên đúng việc của dự án;
2. huấn luyện model chuyên (LoRA) và so với model gốc;
3. chọn model cho sản xuất. Đổi model = đổi chỉ đạo diễn xuất, nên chỉ đổi ở chỗ nối hai cuốn,
   hoặc đổi giữa cuốn nếu con số cho thấy lợi ích đủ lớn (quyết định ghi lại ở đây).

Việc chạy CPU (gom sách, làm gold, dựng kho, viết script) làm liên tục. Việc chạy GPU (đo, huấn luyện)
phải chen vào ranh giới lô, vì sản xuất dùng GPU gần như suốt ngày.

## Công cụ (`scripts/model_eval/`)

| file | việc |
|---|---|
| `make_eval_project.py MODEL` | project nháp: 4 chương cố định, `settings_json` của lô 8 chỉ đổi `analysis.model`, gieo dàn nhân vật từ đúng project đã gieo cho lô 8 |
| `analysis_only.py PROJECT` | chạy riêng khâu phân tích bằng mã sản xuất (chia đoạn, `analyze_all`, hoà giải NPC, cách đọc tên), dừng trước phân vai |
| `score_models.py [PROJECT...]` | chấm theo `gold/*.txt`; không đối số thì chấm mọi project trong `D:/Novels/Audiobooks/_model_eval` |
| `gold/351.txt` ... | đáp án chuẩn (cú pháp ở đầu mỗi file) |

Project đo nằm ở `D:/Novels/Audiobooks/_model_eval/<model>/`, ngoài `book2/_versions`, nên nhịp tim,
watchdog và chuỗi gieo của sách không nhìn thấy chúng.

## Đề bài và đáp án (19-09)

Bốn chương cuốn 2 (tên file nguồn; tiêu đề trong file lệch một số), chọn vì mỗi chương khó một kiểu:

| chương | đoạn | vì sao |
|---|---|---|
| 351 | 97 | nhiều người nói nhất lô 8 (13): hội đồng Arcanist, thư từ, họp Bàn tay Nhợt nhạt |
| 363 | 82 | độc thoại + nguồn hỏng dấu nháy ở đoạn 68 (parser khoá cả 68..81 thành thought) |
| 378 | 120 | gần như toàn nhân vật MỚI (người lùn, ma cà rồng), nhiều câu cả đám cùng nói |
| 381 | 104 | "thanh âm" trên trời (Lucien đóng thần), đại trưởng lão chỉ được gọi tên ở đoạn 48 |

Đáp án làm KHÔNG nhìn nhãn sản xuất. Mỗi dòng cho **tập** lựa chọn chấp nhận được (cảm xúc, nhịp, âm
lượng, khoảng cường độ); người nói thì khắt khe: chỉ tên liệt kê mới có điểm, `~` là nửa điểm. Điểm tổng =
45% người nói + 15% cảm xúc + 10% loại đoạn + 10% cường độ + 5% nhịp + 5% âm lượng + 10% giới tính.

## Kết quả đầu tiên: `qwen3:8b` trong sản xuất (lô 8 thật) — 19-09 22:5x

    model      điểm  người nói  cảm xúc  loại  c.độ  nhịp  âm l.  g.tính
    qwen3:8b   76,6       58,7     84,0  100   92,5  99,2  99,0    84,3

**Người nói đúng 58,7%** trên 4 chương khó. Lần ngược từng lỗi qua `analysis_candidates` (đề xuất của
model → bản sau phản biện → giá trị cuối): gần như mọi lỗi là của **chính model**, lượt phản biện không sửa
cái nào. Hai kiểu lỗi chiếm gần hết:

1. **Lời thoại/nội tâm gán cho NARRATOR** - đọc bằng giọng người kể: đoạn giảng dài của Lucien (351:33,
   43-45), lời cầu nguyện của Harold (378:36-37, 110-111), đại trưởng lão khóc (378:87, 95), "thanh âm" trên
   trời (381:11, 15, 28), suy nghĩ của Lucien (381:87-89), Bellak (363:58, 68), Lucien nói (363:81).
2. **Không chắc thì chộp tên quen nhất trong danh sách đã biết**: Bellak → LUCIEN (363:34-37), đại trưởng lão
   → NATASHA / VICTOR (378:91, 93), Felipe và Sousa → FELICIA (351:83, 86), Galata → Tess (378:11, 13),
   Wells → "Lo" (lấy từ chữ "Lo lắng", 378:25).

Lượt **hoà giải NPC** (`reconcile_local_speaker_identities`, cũng do `qwen3:8b`) thêm lỗi riêng: NPC "người
lùn" → VICTOR (378:79, 84), "thần hơi nước" → "Lo" (378:116-117), "đại trưởng lão" → Quinns (378:1).

Cảm xúc/nhịp/âm lượng thì tốt (84-99%): model thận trọng, hay chọn neutral/normal, mà gold chấp nhận
neutral ở phần lớn lời kể. Chỗ yếu thật là **ai nói**.

## Ứng viên có sẵn (vừa 8 GB VRAM, tải 19-09 22:2x)

`qwen3:8b` (mốc), `qwen3:4b`, `qwen3.5:2b`, `qwen3.5:4b`, `qwen3.5:9b`, `gemma4:e2b-it-qat`,
`gemma4:e4b-it-qat`, `gemma4:12b-it-qat`, `ministral-3:8b`. (`qwen3.6` chỉ có 27b/35b - không vừa;
`granite4.1` không hỗ trợ tiếng Việt.) Lịch đo: cửa sổ GPU sau khi lô 9 thu xong, trước ranh giới 9.

## Kho dữ liệu (`D:/Novels/Ebook Reader/Corpus/`)

Gom 19-09 (chỉ SAO CHÉP; bản trong Tools và Thùng rác giữ nguyên):

| truyện | chương | nguồn |
|---|---|---|
| Young Master's PoV (cuốn 1) | 478 | `Ebook Reader/Text` (nguồn sản xuất, không chép) |
| Throne of Magical Arcana (cuốn 2) | 915 | `Ebook Reader/Text_Tmp` (nguồn sản xuất, không chép) |
| Nise Seiken Monogatari | 158 | Tools |
| Two Childhood Friends ... Dungeon ... | 119 | Tools |
| Đã bảo là cùng nhau tự sát, cớ sao lại thành sống chung | 254 | Tools |
| Yamiyo no Hotaru | 310 | Thùng rác (C:) |
| Hướng dẫn sinh tồn trong học viện | 175 | Thùng rác (D:) |
| Nageki no Bourei wa Intai Shitai | 97 | Thùng rác (D:) |
| Năng lực bá đạo của tôi trong game tử thần ... | 1.590 | Thùng rác (D:) |
| Love Unseen Beneath the Clear Night Sky | 14 | Thùng rác (D:) |

Tên nhận ra bằng nội dung chương đầu và số chương khớp số mp3 trong `D:/Novels/Reading`. Thêm truyện từ Hako
bằng `scripts/corpus/hako.py` (khảo sát: `data/corpus/hako_survey_*.json`; ba mục: dịch bởi người, AI dịch,
sáng tác), **né các truyện đã có trong `Reading`/`Completed`** theo lệnh chủ sách.
