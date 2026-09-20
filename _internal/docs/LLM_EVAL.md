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
| `make_eval_project.py MODEL [--chapters ...] [--book <thư mục Corpus>] [--root]` | project nháp. Mặc định: cuốn 2 (`Text_Tmp`), `settings_json` của lô 8 chỉ đổi `analysis.model`, gieo dàn nhân vật của lô 6. `--book`: truyện bất kỳ trong `Corpus/`, không gieo |
| `analysis_only.py PROJECT [--segment-only]` | chạy riêng khâu phân tích bằng mã sản xuất (chia đoạn, `analyze_all`, hoà giải NPC, cách đọc tên), dừng trước phân vai |
| `score_models.py [PROJECT...] [--gold <thư mục>] [--misses N] [--json]` | chấm theo `gold/<truyện>/*.txt`; chỉ chấm chương có trong project |
| `gold_replay.py PROJECT --gold <thư mục> [--out x.jsonl]` | chạy đúng bộ phân tích sản xuất nhưng Ollama giả **trả lời bằng đáp án**: ra JSONL (prompt sản xuất, câu trả lời đúng) để huấn luyện, và mọi chỗ trượt khi chấm là một **luật host đè đáp án đúng** |
| `replay_all.py --root <thư mục mới>` | phát lại MỌI chương đáp án một lượt: JSONL huấn luyện cho từng truyện + bảng kiểm host (dưới 100% người nói = luật host đè đáp án) |
| `build_training_set.py <root>/train_*.jsonl --out <dir>` | gom JSONL thành train/dev/test chia theo CHƯƠNG; test cố định = các chương dùng so model (không bao giờ vào train) |
| `dump_segments.py PROJECT` | văn bản nguồn cho người gán nhãn: `[seq] p<đoạn> <N/D/T bị khoá> \| chữ` |
| `merge_gold.py compare A B` / `merge A B --out` | so hai bản gán nhãn làm mù; hợp nhất (hợp các tập chấp nhận, ưu tiên theo A) |
| `gold/<truyện>/<chương>.txt` | đáp án chuẩn; luật trong `docs/GOLD_GUIDE.md`, mọi tranh chấp trong `gold/ADJUDICATION.md` |

Project đo nằm ở `D:/Novels/Audiobooks/_model_eval*/`, ngoài `book2/_versions`, nên nhịp tim, watchdog và
chuỗi gieo của sách không nhìn thấy chúng.

## Đáp án chuẩn (20-09 02:2x): 38 chương, 10 truyện, ~4.550 đoạn

| truyện | chương | cách làm |
|---|---|---|
| Throne of Magical Arcana (cuốn 2) | 344-347, 351, 363, 378, 381, 385, 396, 399, 400, 407, 415, 418-420, 426, 436 | A làm, B làm mù hoặc soát; hoặc B làm, A soát |
| Young Master's PoV (cuốn 1) | 134, 188, 199, 248 | như trên (134, 188: B làm, A soát) |
| Đã bảo là cùng nhau tự sát | 020, 050, 143 | như trên (143: B làm, A soát) |
| Hướng dẫn sinh tồn trong học viện | 060, 090 | cả hai làm mù (060); B làm, A soát (090) |
| Nise Seiken Monogatari | 030, 111 | cả hai làm mù (030); B làm, A soát (111) |
| Nageki no Bourei wa Intai Shitai | 20, 73 | cả hai làm mù (20); B làm, A soát (73: nhóm giả mạo tên na ná - bẫy cho model) |
| Yamiyo no Hotaru | 155, 189 | làm mù (155), B làm - A soát (189); **chỉ khớp bộ tách đoạn sau bản vá ngoặc 「」** |
| Năng lực bá đạo ... | 0135 | B làm, A soát đối kháng |
| Love Unseen Beneath the Clear Night Sky | 09 | B làm, A soát đối kháng |
| Two Childhood Friends ... Dungeon ... | 013, 082 | B làm, A soát đối kháng |

A = Claude, B = một agent review (chủ sách cho phép dùng subagent riêng cho việc này, 20-09: *"cả 2 phải thật
khắt khe"*). Mỗi dòng cho **tập** lựa chọn chấp nhận được (cảm xúc, nhịp, âm lượng, khoảng cường độ); người nói
khắt khe: chỉ tên liệt kê mới có điểm, `~` là nửa điểm. Điểm tổng = 45% người nói + 15% cảm xúc + 10% loại đoạn +
10% cường độ + 5% nhịp + 5% âm lượng + 10% giới tính.

Độ đồng thuận giữa hai người gán nhãn làm mù:

| vòng | chương | người nói ưu tiên | tập chấp nhận | loại đoạn | cảm xúc ưu tiên |
|---|---|---|---|---|---|
| 1 | 378, 248 | 97,9% | 100% | 100% | 89,1% |
| 3 | 344, 345 | 98,6% | 100% | - | 94,8% |
| 4 | hdst 060, nise 030 | 87,2% | 100% | 234/238 | 95,0% |
| 5 | 407, nageki 20 | 100% | 100% | 285/285 | 92,9-96,5% |
| 6 | 419, yamiyo 155 | 100% | 100% | 215/215 | 84,0-93,6% |
| 8 | 418 | 97,0% | 97,0% | 89/89 | 98,9% |
| 9 | 436 | 100% | 100% | 83/85 | 88,2% |

Chỗ lệch còn lại gần như chỉ là "lời kể hay tiếng lòng" (`N` hay `N,T`) và bí danh; không vòng nào hai bên chọn
hai NGƯỜI khác nhau cho một câu mà không phân xử được bằng văn bản. Luật mới sinh ra từ tranh chấp đều ghi vào
`GOLD_GUIDE.md` (nội tâm của người nghĩ - quyết định chủ sách 20-09; văn bản viết; nhập xác/cải trang; lời dẫn nêu
hai người; tên bị cắt; ...).

**Chi phí làm gold** (đo 19-09, TMA 344-347, 11.307 từ): 4,3 token/từ (đọc 3,2 + viết 0,45 + nghĩ ~0,6), tức
~130 token/đoạn. Cửa sổ 5 giờ nhích 0 → 1%, tuần giữ 36%.

## Mốc: `qwen3:8b` trong sản xuất, chấm theo đáp án hiện hành

| phạm vi | điểm | người nói | chỉ câu thoại | cảm xúc | giới tính |
|---|---|---|---|---|---|
| cuốn 2, lô 8, 8 chương | 79,0 | 65,7% | 67,7% | 85,5% | 78,4% |
| cuốn 1, 4 chương (từng chương: 134 lô 5 / 188 lô 7 / 199 lô 8 / 248 lô 9) | 62,9 / 71,4 / 83,4 / 68,9 | 31,2% / 52,9% / 68,8% / 40,4% | - | - | - |
| cuốn 2, lô 9 (thu 20-09), 9 chương 385, 396, 399, 400, 407, 415, 418, 419, 420 | 79,7 | 68,4% | - | 82,1% | 83,7% |

(Con số 58,7% người nói ngày 19-09 là trên bản đáp án đầu, trước ba vòng soát.) Kiểu lỗi của model, xếp theo số câu ở
lô 9: **lấy người ĐƯỢC GỌI TÊN làm người nói** ("Haha, Andris, mày..." -> ANDRIS; "Chờ đã, Aska, ..." -> ASKA; "Fil, hôm nay anh
lạ lắm nhé." -> LUCIEN vì Fil là lốt của Lucien; "Hân hạnh được gặp cậu, Evans." -> một nhân vật ma EVANS có giọng riêng, 6
câu ở 417-419); nội tâm gán cho NARRATOR (một phần do host, đã vá); thuật ngữ/tiếng động giữa câu kể gán cho nhân vật; tên
viết sai thành nhân vật mới ("JOCLEYN"); không chắc thì chộp tên quen nhất; lượt hoà giải NPC gộp nhầm. Luật host
`_speaker_is_directly_addressed` chỉ bắt tên gọi ở ĐẦU câu hoặc sau danh xưng, nên sót cả ba kiểu gọi trên - việc kế
tiếp để điều tra (không vào ranh giới 9: khi bắt được, nó cũng chỉ đổi sang một NPC "người gọi X").

Cuốn 1 lô 5 (chương 134) cho thấy pipeline cũ: phần lớn câu của một cảnh hai người được gán cho nhãn vai trò trơn
"NGƯỜI TRẢ LỜI", "THỦ LÃNH" (không phải NPC cục bộ) - 31% người nói. Khi cuốn 1 chạy tiếp, các lô đầu là ứng viên đúc lại. Cảm
xúc, nhịp, âm lượng tốt (model thận trọng, hay chọn neutral/normal). Chỗ yếu thật là **ai nói**.

## Host đè câu trả lời đúng - kiểm bằng `gold_replay` (20-09)

Phát lại MỌI chương đáp án qua đúng bộ phân tích sản xuất, với câu trả lời đúng: năm truyện ra 100 điểm, cuốn 2
chỉ ra **92,8% người nói** - tức một model hoàn hảo cũng không vượt trần ấy. Mỗi chỗ trượt là một luật host:

| luật | đè thế nào | bản vá (hàng chờ ranh giới 9) |
|---|---|---|
| `_validate` | mọi câu nội tâm về NARRATOR (21 câu / 10 chương) - sót từ 7e4d74c, trái quyết định chủ sách | `patch_a_thought_keeps_its_thinker.py` |
| `_explicit_speaker_attribution` | chữ Việt không dấu đầu câu là "tên" ("Lo lắng" -> Lo); "X còn chưa kịp đáp..." khoá cho X | `patch_the_name_after_a_quote_is_not_always_its_speaker.py` |
| `_repair_same_paragraph_speakers` | thuật ngữ trích giữa câu kể ("dây chuyền lắp ráp") thành giọng người nói của đoạn | `patch_a_quoted_term_is_not_the_paragraphs_line.py` |
| `_trailing_speech_attribution` | "Levski quay sang **Lucien** nói:" khoá cho người NGHE; "Triết Gia hỏi:" -> "Gia" (~29 câu cuốn 2) | `patch_the_one_being_looked_at_is_not_the_speaker.py` |
| `_generic_speaker_attribution` + khoá theo đoạn | lời dẫn có tên vẫn khoá cho nhãn chung ("…một người phụ nữ, James chỉ vào Lucien rồi nói:" -> "người phụ nữ"; trên đáp án 2/2 lần sai; cuốn 2: 157/304 lần có tên); lượt ngắt lời trong một đoạn ("Florencia liền … cắt ngang:") bị gán cho người nói trước | `patch_a_named_tag_beats_a_generic_one.py` |

Với đủ tám bản vá, phát lại **cả 28 chương đáp án** (10 truyện) được 100% người nói; chỉ còn hai câu nửa điểm đúng
như đáp án muốn (385:123 lời dẫn dùng tên giả "Aska"; Love Unseen 09:54 lời dẫn viết nhầm "Naurmi"). Cùng đợt, kho truyện lộ lỗi bộ tách đoạn: ngoặc
góc 「…」 của bản dịch light novel Nhật bị khoá là lời kể (Yamiyo no Hotaru: 30.941 dòng thoại) -
`patch_a_corner_bracket_is_a_quote.py`; hai cuốn sản xuất không có 「 nên không đổi một đoạn nào (chứng minh bằng
chia đoạn lại cả 1.393 chương).

Hệ quả cho việc so model: mọi lượt đo trước ranh giới 9 chạy trên host cũ, nên điểm tuyệt đối bị chặn trần; so
TƯƠNG ĐỐI giữa các model vẫn công bằng (cùng trần). Đo lại sau ranh giới để có con số thật.

## Một lỗ của chính thước đo: đáp án chuẩn KHÔNG có trục TUỔI (20-09 13:3x)

Đáp án chuẩn chấm bảy trục: người nói, cảm xúc, loại đoạn, cường độ, nhịp, âm lượng, giới tính. **Tuổi không có
trong đó** - và tuổi là thứ chọn HỌ GIỌNG (trẻ con đọc bằng preset nữ kéo cao, người già bằng preset khác), nên
một nhãn tuổi sai đổi giọng mạnh hơn nhiều nhãn cảm xúc sai.

Ca thật, tìm ra bằng `scripts/voice_matches_the_person.py` chứ không phải bằng đáp án: **CHRISTOPHER**, chủ tịch
Hiệp hội Nhạc sĩ, một ông già ("ngài Chủ tịch", "bậc thầy", "bậc tiền bối", đã có buổi hòa nhạc cuối cùng trong
sự nghiệp), bị model gán `age=child` ở 13 chương và vì thế đọc bằng giọng nữ kéo cao 39 câu. Đáp án chuẩn KHÔNG
BAO GIỜ thấy được lỗi ấy: nó không hỏi về tuổi.

Hai cách đọc con số này, và cả hai đều đúng: (1) đừng tưởng "đáp án 100%" nghĩa là "phân tích đúng" - nó nghĩa là
đúng trên bảy trục ấy; (2) công cụ đúng cho tuổi là bản kiểm giọng trên cuốn sách đã ghép, không phải đáp án -
mỗi thứ đo được một thứ. Chưa thêm trục tuổi vào đáp án vì 41 file đáp án đang viết theo đúng cú pháp hiện tại
và đổi cú pháp là viết lại cả 41; nếu sau này thêm, phải thêm cùng lúc cho cả bộ.

## Còn sai chỗ nào sau năm bản vá, và cửa host cuối cùng (20-09 11:1x)

Phân loại 115 chỗ CÒN sai người nói của lô 9 (sau khi phát lại qua cây 5 bản vá) theo **câu kể cùng đoạn văn có nêu
đúng tên người nói hay không**:

| | số chỗ | nghĩa |
|---|---|---|
| câu kể cùng đoạn CÓ nêu tên đúng | **57** | host còn cửa - lời dẫn nằm ngay đó mà luật không đọc được |
| không có câu kể cùng đoạn | 38 | model phải suy từ ngữ cảnh xa; host không giúp được |
| có câu kể nhưng không nêu tên đúng | 20 | như trên |

Một nửa số 57 là **nội tâm**, và phần ấy đã được sửa bằng prompt (bảng đếm câu trả lời thô ở mục dưới). Nửa còn lại
là một dạng lời dẫn chưa ai khai thác: câu kể kết bằng `<động từ nói>:` nhưng cái tên **sát động từ** lại là người
NGHE, còn người nói là **chủ ngữ mở câu**:

    "Một lúc sau, Inke thấy Aska mặt tươi roi rói bước ra, bèn tò mò hỏi:"   -> INKE, không phải Aska
    "Nhân sư cái Sana nhìn Lucien và nhỏ giọng nói:"                          -> SANA, không phải Lucien

Tôi đã viết luật ấy (lấy tên đầu câu, với bốn chốt đo ra từng cái: bỏ mảnh vụn chữ Việt "Nhìn" -> "Nh" và
"Ham muốn" -> "Ham"; giới từ/động từ tri giác liền trước tên - "của Lucien", "cao hơn Fil", "Nghe Levski";
`NOT_YET_SPOKEN_PATTERN` - "Lucien chưa kịp đáp lại, Artil đã ... nói:"; và đứng trước nhãn chung chung).

**Và đã LOẠI nó, sau khi hai phép đo trả lời trái nhau. Đây là bài học đáng giữ hơn cả bản vá.**

| phép đo | kết quả |
|---|---|
| phát lại CÂU TRẢ LỜI CỦA MODEL (lô 9 thật, 915 đoạn) | luật nổ 27 lần, đúng 25; đối chiếu từng đoạn: **được 5, mất 1**; người nói 73,1% -> **74,1%** |
| phát lại ĐÁP ÁN CHUẨN (41 chương) | **host đè 7 đoạn đáp án ĐÚNG**: `351:29-32` (4 đoạn, "Grand Arcanist" - một danh hiệu, đáp án LUCIEN), `418:82` (James/LILLIAN), `420:84` (Lucien/NPC*), `426:25` (Levski/LUCIEN) |

Hai phép đo **đo hai thứ khác nhau**, và một luật host phải qua CẢ HAI:

  - phát lại câu trả lời của model nói *"luật này sửa được bao nhiêu lỗi của model"*;
  - phát lại đáp án chuẩn nói *"luật này phá bao nhiêu câu trả lời ĐÚNG"* - và con số ấy phải bằng **0**. Cả tám bản
    vá ranh giới 9 sinh ra chính vì cổng ấy: host đè đáp án đúng là lỗi im lặng, model sai là lỗi ồn ào, và lỗi im
    lặng thì không ai đi tìm.

Lãi 5 ăn 1 trên lỗi của model không mua được quyền phá 7 câu trả lời đúng. Nếu sau này muốn làm lại: chốt danh hiệu
(4 trong 7 chỗ là "Grand Arcanist") xoá được hơn một nửa số hại, nhưng ba chỗ còn lại là chủ ngữ làm một việc KHÔNG
phải nói với người nói xuất hiện sau - không tách được bằng mặt chữ, nên luật này chỉ đúng khi có thêm tín hiệu
ngoài câu kể ấy.

## Sáu bản vá ranh giới 10, đo trong SẢN XUẤT THẬT (20-09 19:0x) - không cần đáp án, không cần GPU

Lô 11 là lô đầu chạy với chúng. Cách đo: tính lại chính vị từ của bản vá trên các đoạn ĐÃ phân tích của hai lô, rồi
xem người nói trong sổ có khớp không. Không cần đáp án chuẩn, vì câu hỏi ở đây là *"host có làm đúng điều nó hứa
không"*, chứ không phải *"ai mới là người nói thật"*.

| bản vá | lô 10 (host cũ) | lô 11 (đã vá) |
|---|---|---|
| cụm trích giữa câu kể phải là NGƯỜI KỂ | 23 đoạn khớp vị từ, **chỉ 1** gán NGƯỜI KỂ | 16 đoạn, **16/16** |
| trạng ngữ giữa tên và động từ nói | 32 chỗ nhận ra lời dẫn, **26** khớp người nói | 14 chỗ, **14/14** |

Sáu chỗ lệch của lô 10 ở hàng thứ hai chính là những ca tôi đã phân xử tay: `426:3` host nói *Neeshka* mà sổ ghi
*LEVSKI*, và nguồn viết thẳng *"Neeshka đằng hắng rồi nói:"* - tức host đúng, model sai, và lô 11 nay lấy đúng.

Con số tuyệt đối khác nhau (23 so với 16, 32 so với 14) vì hai lô là hai vùng chương khác nhau; thứ đáng đọc là tỉ
lệ khớp: **1/23 -> 16/16** và **26/32 -> 14/14**.

Ba bản vá còn lại chỉ chạy ở bước **phân vai**, nên đo khi lô 11 cast xong (22:0x):

| bản vá | kết quả trong sản xuất |
|---|---|
| giọng mang pitch trẻ con không thuộc người lớn | `Bỏ giọng ghim của KAELYN: preset_ngoc_linh_f109_p+04 mang pitch trẻ con mà người nghe đã ghim tuổi adult` - đúng 1 ca, cùng với CHRISTOPHER bị luật cũ bỏ |
| văn bản thắng phiếu CHIA về giới tính | **Nika**: model bỏ phiếu 5 nữ / 1 nam, văn bản 44 nam / 1 nữ -> sổ ghi `male`. Kiểm nguồn: *"đừng tìm đến tên Nika điên. **Hắn** đơn giản chỉ là một ác ma điên cuồng"* - đè ĐÚNG |
| tên lệch hai ký tự vẫn là một người | **không nổ lần nào**: lô 11 chỉ có `NATHASHA` -> `Natasha`, mà đó là lệch MỘT ký tự nên luật cũ đã lo. Không có nhãn nào lệch hai ký tự trong lô này |

Hàng cuối là cách đọc đúng của một bản vá phòng ngừa: nó không nổ nghĩa là lô này không có ca ấy, không phải nó vô
dụng - `ARTELI` của lô 10 vẫn còn nguyên trong sổ nhân vật lô ấy như một người thứ hai bên cạnh `ARTIL` (41 lần).

Hai chốt của luật giới tính cũng chạy đúng ở lô 11: `ASIN` (phiếu 2 nam/5 nữ, văn bản 63/22 nhưng tỉ lệ 2,9 < 3)
KHÔNG bị đè - ngưỡng giữ nó lại; `HATHAWAY` giữ `female` vì **người nghe đã ghim**, và ghim của người nghe đứng
trên cả văn bản.

Dấu vết host (`ADDRESSEE_REPAIR_NOTE` và họ hàng) **không** được lưu vào cột `analysis_notes` - cả lô 10 lẫn lô 11
đều 0 dòng có dấu `;` - nên đừng đếm chúng ở đó như tôi đã thử; chúng chỉ sống trong lượt phân tích để phản biện
đạo diễn biết host đã sửa. Cách đo đúng là tính lại vị từ như trên.

## Phát lại câu trả lời ĐÃ GHI: đo bản vá host trong sản xuất mà không cần GPU (20-09 10:4x)

`scripts/model_eval/replay_from_candidates.py`. Mỗi lô phân tích để lại `analysis_candidates.candidate_json`,
trong đó `critic_rows[].candidate` là **câu trả lời thô của model**. Nạp lại nó, chạy đúng `_validate` của cây
đang có, rồi chấm theo đáp án: thế là so được luật host cũ với luật host mới **trên cùng một câu trả lời**, không
phải chạy lại LLM, không tranh GPU với sản xuất.

Kiểm tính đúng của chính công cụ: phát lại lô 10 (chương 426+429, 45 lô, 178 đoạn có đáp án) qua cây 8 bản vá của
ranh giới 9 cho **79,4 / người nói 71,3%**, còn bản ghi thật của project là **79,6 / 71,7%** - lệch đúng vì 2 đoạn
thiếu. Công cụ tái hiện được sản xuất.

Và đây là mức lợi của 5 bản vá ghim cho ranh giới 10, đo trên cùng 178 đoạn ấy:

| cây | điểm | người nói | cảm xúc | loại |
|---|---|---|---|---|
| 8 bản vá (ranh giới 9) - đang chạy | 79,4 | 71,3% | 87,1% | 100% |
| + 5 bản vá ghim ranh giới 10 | **82,0** | **77,0%** | 87,1% | 100% |

Đo lại trên mẫu LỚN hơn - lô 9, 915 đoạn có đáp án trên 9 chương (lô 9 chạy bằng host CHƯA vá, nên đây là
"nếu hồi ấy đã có các bản vá này thì sao"):

| cây | điểm | người nói |
|---|---|---|
| host cũ (bản ghi thật của lô 9) | 79,7 | 68,4% |
| 8 bản vá ranh giới 9 | 79,9 | 69,0% |
| + 5 bản vá ranh giới 10 | **81,7** | **73,1%** |

Tổng hai mẫu: 1.093 đoạn có đáp án, 5 bản vá ranh giới 10 đáng **+4 đến +6 điểm** độ chính xác người nói.

**Giới hạn lớn nhất, và nó giải thích một con số trông như thất bại:** công cụ chỉ đo được bản sửa CHẠY SAU khi
model trả lời. Tám bản vá ranh giới 9 phát lại chỉ thêm 0,6 điểm, nhưng không phải vì chúng vô dụng - phần lớn giá
trị của chúng đến từ chỗ khác: `patch_a_thought_keeps_its_thinker.py` đổi **chính sách trong prompt**, và phép đếm
câu trả lời THÔ cho thấy nó hiệu nghiệm hẳn trong sản xuất:

| lô | model thô gán nội tâm cho | |
|---|---|---|
| lô 9 (host cũ) | NARRATOR **208/208** | 0 nhân vật |
| lô 10 (8 bản vá) | NARRATOR 4/39 | **nhân vật 35/39** |

Phát lại nạp đúng câu trả lời đã ghi, nên nó không bao giờ tái hiện được một thay đổi ở prompt. Hai loại bản vá,
hai cách đo: sửa-sau-câu-trả-lời thì phát lại; đổi-prompt thì phải chạy một lô mới rồi đếm câu trả lời thô.

Ba giới hạn nhỏ hơn: chỉ chương có đáp án; cột GIỚI TÍNH đi thẳng từ bản đã ghi (host không quyết trường ấy -
`resolve_gender` quyết ở bước lập sổ nhân vật); và bản vá GOM TÊN (`ARTELI` -> `Artil`) chạy ở bước lập sổ nhân vật
nên KHÔNG hiện ở đây - điểm người nói đo cái nhãn model viết ra, bản vá ấy sửa cái giọng.

## Điều tra kiểu lỗi lớn nhất của model (20-09 09:0x): host có thể tự sửa bao nhiêu?

`score_models.py --dispute-out` trên bản thu lô 9 (`qwen3:8b`, 79,7 - người nói 68,4%) cho 134 chỗ lệch; phân loại ở
`gold/ADJUDICATION.md` vòng 14. Hai kiểu lớn nhất đều là chỗ host ĐÁNG RA biết mà không biết:

**(1) Trạng ngữ chen giữa tên và động từ nói - ĐÃ VÁ, ghim ranh giới 10.** `SPEECH_ATTRIBUTION_PATTERN` đòi động từ
dính liền tên, nên "Arthen nghiêm nghị hỏi:", "James mỉm cười nói:", "Lucien từ tốn nói:" đều không khớp: trong 9
chương đáp án của lô 9, luật cũ chỉ bắt được **2** lần, còn 122 câu thoại có câu kể liền trước thì host mù hoàn toàn.
Nới cho phép 1-3 chữ thường ở giữa (không dấu phẩy) + hai chốt mới (giới từ liền trước tên; chữ hướng tới người nghe
nằm ở giữa). Đo trên **cả 41 chương đáp án**: **17 câu gán ĐÚNG thêm, 0 câu gán SAI thêm**.
Bản vá: `patch_a_modifier_between_a_name_and_said_still_names_the_speaker.py`.

**(2) Tên người nghe không ở đầu câu thoại - ĐO RỒI, CỐ Ý CHƯA VÁ.** `_speaker_is_directly_addressed` chỉ thấy tên ở
đầu câu (`^Tên,`) hoặc danh xưng + tên. Thử 9 lối gọi tên thật: **6 lối bị bỏ sót** - sau thán từ ("Chờ đã, Aska,"),
cuối câu ("Sao vậy, Beaulac?", "Cảm ơn nhé, Lucien.", "Hân hạnh được gặp cậu, Evans."), giữa câu ("Thôi được rồi,
Lazar, giờ tôi..."). Đây chính là nguồn "EVANS ma" - model lấy người ĐƯỢC GỌI làm người nói.

Nhưng nới ra **không được điểm nào**: luật này không đoán ai nói, nó thay người nói bằng `người gọi X` (một NPC vô
danh), mà đáp án thì muốn người nói thật. Và đo mức HẠI trên 41 chương: luật nới nổ trên chính NGƯỜI NÓI THẬT **2
lần**, cả hai là tự giới thiệu - `347:51 "Bạn của cô, Derrick Douglas."` và `446:48` (Dạ Oanh xướng tên mình trên
sóng) - **cùng mặt chữ với lối gọi tên**, không tách được bằng văn bản: câu trước dấu phẩy vẫn có đại từ ngôi hai
("của **cô**").

**Đo xong bằng phát lại (20-09 11:0x), trên toàn bộ 3.668 đoạn của lô 9** (`replay_from_candidates.py`, cây 5 bản vá
so với cây ấy + luật nới): điểm người nói 73,1% -> 73,4% (gần như không đổi, đúng như dự đoán), và **đúng 11 đoạn đổi
người nói**:

| | số đoạn | ví dụ |
|---|---|---|
| giọng nhân vật SAI -> giọng vô danh (lợi) | **9** | `418:39 "Hân hạnh được gặp cậu, Evans."` EVANS -> người gọi EVANS; `420:52 "Chào, Lazar..."`; `409:109 "Chúc mừng cậu, Beaulac..."`; `385:109 "Chờ đã, Aska..."` |
| giọng nhân vật ĐÚNG -> giọng vô danh (hại) | **2** | `417:71-72` lời của ARTHUR có nhắc ", Evans," giữa câu -> người gọi EVANS |

Tỷ lệ 4,5:1 nghiêng về lợi, nhưng cả hai phía đều không phải điểm số: nó là **đổi ai đọc câu ấy**. Câu hỏi thuộc về
tai chủ sách, không thuộc về thước đo: *"một câu bị nhân vật SAI đọc" tệ hơn hay nhẹ hơn "một câu của người ĐÚNG bị
giọng vô danh đọc"?* Chín ăn hai. Chưa vá, chờ câu trả lời.

## Lượt đo đêm 20-09 (host CHƯA vá, 4 chương 351/363/378/381) - và bài học về công cụ đo

| model | chạy trọn | điểm | người nói | cảm xúc | c.độ | g.tính | giây |
|---|---|---|---|---|---|---|---|
| `qwen3:8b` (mốc) | có | 77,3 | 59,6% | 86,0 | 91,5 | 85,5 | 1.711 |
| `gemma4:e2b-it-qat` | có | 76,6 | **61,9%** | 81,0 | 85,2 | 82,9 | **771** |
| `gemma4:e4b-it-qat` | KHÔNG (quá 40 phút) | 74,2* | 57,1%* | 86,0 | 95,7 | 61,7 | - |
| `gemma4:12b-it-qat` | KHÔNG (rơi ID ở lô 8) | 58,0* | 14,7%* | - | - | - | - |
| `ministral-3:8b` | KHÔNG (rơi ID ở lô 7) | 56,6* | 14,7%* | - | - | - | - |
| `qwen3:4b`, `qwen3.5:4b`, `qwen3.5:9b` | KHÔNG (0 ID từ lô 1) | 46,5* | 9,0%* | - | - | - | - |

`*` = chấm trên phần đã phân tích trước khi đổ, KHÔNG so được. Hai điều rút ra:

1. **Độ tin cậy là cổng trước độ chính xác.** `analyze_all` coi một lô trả thiếu ID là lỗi bắt buộc và ném lỗi - trong
   sản xuất là một lô đứng. Bốn model trả 0 ID ngay lô 1 (dòng qwen3 mới nghĩ trước khi trả JSON: yêu cầu của dự án
   KHÔNG gửi `think: false`); hai model rơi ID giữa chừng.
2. **`gemma4:e2b-it-qat` là ứng viên thật**: chạy trọn, người nói CAO HƠN mốc 2,3 điểm, nhanh gấp 2,2 lần, đổi lại cảm
   xúc/cường độ/giới tính thấp hơn 3-6 điểm. Cần đo lại đàng hoàng trước khi kết luận.

Công cụ đo vì thế viết lại (`eval_models.py`, 20-09): MỖI CHƯƠNG một project, trần giờ cho từng chương, độ tin cậy =
chương chạy trọn / chương thử + số lần thử lại vì thiếu ID; `analysis_only.py --no-think` gửi `think: false`. Lượt đo
tiếp (ranh giới 10): cả 20 chương TMA có đáp án, host ĐÃ vá, và chỉ những model qua cổng tin cậy mới được xếp hạng.

## Ứng viên có sẵn (vừa 8 GB VRAM, tải 19-09)

`qwen3:8b` (mốc), `qwen3:4b`, `qwen3.5:2b`, `qwen3.5:4b`, `qwen3.5:9b`, `gemma4:e2b-it-qat`,
`gemma4:e4b-it-qat`, `gemma4:12b-it-qat`, `ministral-3:8b`. (`qwen3.6` chỉ có 27b/35b - không vừa;
`granite4.1` không hỗ trợ tiếng Việt.) Lượt đo đầu: chuỗi đêm 19-09 (`run_night_19_09.sh`), 8 model trên 4
chương TMA ngay sau khi lô 9 thu xong, trước ranh giới 9; kết quả ở `runtime/model_eval_19_09.{log,json}`.

## Huấn luyện: dữ liệu đã dựng, script đã có, chờ cửa sổ GPU (20-09 11:3x)

`build_training_set.py` trên bộ phát lại mới nhất (cây 5 bản vá, 41 chương đáp án): **train 1.727 mẫu / dev 76 /
test 230**, chia theo CHƯƠNG nên không mẫu nào của một chương nằm ở hai tập. Đo bằng tokenizer Qwen3:

| | trung vị | p90 | p99 | tối đa |
|---|---|---|---|---|
| cả mẫu (prompt + đáp) | 3.213 | 3.730 | 4.069 | **4.276** |
| riêng câu trả lời | 369 | | | 784 |

Một epoch = **5,29M token**. `--max-length 4352` để giữ TRỌN mẫu dài nhất: cắt ở đây là cắt mất câu trả lời, tức
huấn luyện trên một đề bài không có đáp án.

`scripts/model_eval/train_lora.py`: QLoRA 4-bit (nf4, double quant, bf16), LoRA r=16 alpha=32 trên bảy phép chiếu,
`paged_adamw_8bit`, gradient checkpointing, `packing=False` (mỗi mẫu là một lượt hỏi trọn, ghép lại là trộn hai đề
bài), và `assistant_only_loss=True` - không có nó thì model học cả việc sinh lại prompt sản xuất, thứ nó sẽ luôn
được cho sẵn.

Model nền **`Qwen/Qwen3-4B-Instruct-2507`**: cùng họ với `qwen3:8b` đang chạy nên prompt không phải viết lại, vừa
8 GB VRAM ở 4-bit, và bản `-Instruct-2507` không có chế độ nghĩ - chính chế độ ấy làm `qwen3.5:9b` trả "0/5 IDs"
đêm 19-09. Nếu một model 4B huấn luyện riêng đánh bại mốc 8B thì đó là kết quả đáng giá gấp đôi: đúng hơn và nhẹ hơn.

Script **TỪ CHỐI chạy khi có lượt sản xuất đang bay** (dùng lại `_runs_in_flight` của `apply_all.py` thay vì viết
bộ canh thứ hai - docstring hàm ấy ghi hai lần bộ canh tự viết đã sai). Đã thử: nó chặn đúng lô 10. Máy 8 GB VRAM,
huấn luyện chen vào giữa một lượt thu là ném cả lượt ấy vào OOM.

### Đường phục vụ model tự huấn luyện: đã thử trọn mắt xích, KHÔNG phỏng đoán (20-09 12:0x)

Muốn chấm model chuyên trong CÙNG điều kiện với mốc `qwen3:8b` thì nó phải chạy qua đúng bộ phân tích sản xuất,
tức qua Ollama (cùng prompt, cùng lược đồ JSON bắt buộc, cùng `num_ctx`). Ba điều đo được:

1. **Ollama 0.33.2 không nhập được safetensors Qwen3.** `ollama create` từ thư mục safetensors trả
   `Error: unsupported architecture "Qwen3ForCausalLM"`. Đây là lý do phải qua GGUF - đã thử, không suy đoán.
2. **`convert_hf_to_gguf.py` bản mới KHÔNG còn tự chứa**: nó import package `conversion` (94 file trong repo
   llama.cpp), nên tải một file là không đủ. Cách gọn: sparse clone chỉ `conversion/` + `gguf-py` vào
   `D:/Novels/LLM_Train/llama.cpp` - **3,5 MB**.
3. **Mắt xích chạy thông**, thử bằng `Qwen/Qwen3-0.6B`: safetensors -> GGUF f16 (1,5 GB) -> `ollama create` ->
   `POST /api/generate` kèm `format` là lược đồ JSON -> trả **JSON hợp lệ**, `done=True`, `eval_count=61`, 6,4s
   khi nạp nguội. Đúng hợp đồng `OllamaBookAnalyzer` đọc (`response`/`done`/`done_reason`/`eval_count`).

`scripts/model_eval/serve_lora.py` làm ba bước ấy trong một lệnh (gộp adapter trên CPU ~8 GB RAM, chuyển GGUF,
`ollama create`). Gộp và chuyển KHÔNG cần GPU nên chạy được giữa lúc lô đang thu; chỉ bước chấm mới cần GPU.

Việc còn lại cho cửa sổ GPU, theo đúng thứ tự: `train_lora.py --smoke 8` (kiểm đường ống, 3 bước) -> một epoch ->
`serve_lora.py` -> chấm bằng `eval_models.py` trên tập TEST (230 mẫu / 5 chương mà model chuyên chưa từng thấy).

## Huấn luyện

- Dữ liệu: `gold_replay.py --out` ra từng cặp (prompt sản xuất đúng như model thấy, câu trả lời đúng) cho cả
  generator lẫn lượt phản biện: `D:/Novels/Audiobooks/_model_eval_gold/train_*.jsonl`. Chia train/dev/test theo
  CHƯƠNG (không trộn đoạn của một chương vào hai tập); test giữ nguyên để so model gốc với model đã huấn luyện.
- Môi trường: `D:/Novels/LLM_Train/.venv` (torch 2.11.0+cu128, transformers 5.17.0, peft 0.21.0, trl 1.13.0,
  bitsandbytes 0.50.2). QLoRA 4-bit trên RTX 5060 8 GB, chạy trong cửa sổ GPU giữa hai lô.
- Chọn model gốc sau lượt đo các model có sẵn.

## Kho dữ liệu (`D:/Novels/Ebook Reader/Corpus/`)

Gom 19-09 (chỉ SAO CHÉP; bản trong Tools và Thùng rác giữ nguyên), đẩy lên repo:

| truyện | chương | nguồn |
|---|---|---|
| Young Master's PoV (cuốn 1) | 478 | `Ebook Reader/Text` |
| Throne of Magical Arcana (cuốn 2) | 915 | `Ebook Reader/Text_Tmp` |
| Nise Seiken Monogatari | 158 | Tools |
| Two Childhood Friends ... Dungeon ... | 119 | Tools |
| Đã bảo là cùng nhau tự sát, cớ sao lại thành sống chung | 254 | Tools |
| Yamiyo no Hotaru | 310 | Thùng rác (C:) |
| Hướng dẫn sinh tồn trong học viện | 175 | Thùng rác (D:) |
| Nageki no Bourei wa Intai Shitai | 97 | Thùng rác (D:) |
| Năng lực bá đạo của tôi trong game tử thần ... | 1.590 | Thùng rác (D:) |
| Love Unseen Beneath the Clear Night Sky | 14 | Thùng rác (D:) |

`data/corpus/manifest.json` (`scripts/corpus/manifest.py --check`): 10 truyện, 4.110 chương, 12,95 triệu từ.
Tên nhận ra bằng nội dung chương đầu và số chương khớp số mp3 trong `D:/Novels/Reading`. Thêm truyện từ Hako
bằng `scripts/corpus/hako.py` (khảo sát: `data/corpus/hako_survey_*.json`; dịch bởi người, AI dịch, sáng tác),
**né các truyện đã có trong `Reading`/`Completed`** theo lệnh chủ sách.
