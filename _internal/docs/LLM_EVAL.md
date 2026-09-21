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

## Lượt đo 21-09 (host đã vá 14 bản, 4 chương 351/363/378/381): `qwen3:4b` không kém mốc 8B

| model | tin cậy | rơi ID | điểm | người nói | cảm xúc | giây | VRAM |
|---|---|---|---|---|---|---|---|
| `qwen3:4b` | **4/4** | 0 | **80,0** | **65,7%** | 85,0 | **1.573** | 3,7 GB |
| `qwen3:8b` (mốc, đang chạy sản xuất) | 4/4 | 0 | 79,4 | 64,1% | **85,5** | 2.156 | 5,2 GB |
| `gemma4:e2b-it-qat` | 4/4 | 0 | 77,2 | 62,2% | 82,0 | **842** | 1,8 GB |

**Cả ba rơi 0 ID** - cổng tin cậy sạch, và đó cũng là bằng chứng cờ `--no-think` làm việc: đêm 19-09 dòng
`qwen3` trả "0/5 IDs" vì nghĩ trước. Bốn đường gửi yêu cầu (sinh, phản biện, nhận diện nhân vật, cách đọc
tên) đều đi qua `_stream_json_response`, chỗ bị monkeypatch, nên cờ phủ trọn.

**Đọc con số cho đúng, đừng tuyên vô địch.** 80,0 so với 79,4 là **0,6 điểm**, và người nói 65,7 so với
64,1 là 1,6 điểm ≈ **6 đoạn** trên tập này. Một lượt chạy của một model không tất định thì 6 đoạn nằm
trong nhiễu. Điều phát biểu được là: **`qwen3:4b` KHÔNG kém mốc 8B**, mà nhanh hơn **27%** và nhẹ hơn
1,5 GB VRAM. Điều KHÔNG phát biểu được: nó tốt hơn.

### CHỌN CHƯƠNG chi phối mạnh hơn CHỌN MODEL - đo được, và nó đổi cách đọc mọi bảng ở trên

Lượt 6 chương mới (21-09 06:0x) cho cùng `qwen3:8b`, cùng host, cùng cờ:

| tập chương | điểm | người nói |
|---|---|---|
| 4 chương tập test (351/363/378/381) | 79,4 | **64,1%** |
| 6 chương mới (385/396/399/400/407/415) | 81,8 | **75,9%** |

**11,8 điểm người nói** giữa hai tập chương của MỘT model - lớn gấp bảy lần chênh lệch giữa các model
(1,6 điểm). Bốn chương tập test khó hơn trung bình rõ rệt.

Hai hệ quả, cả hai đều là luật cho mọi lượt đo sau:

  - **chỉ so trên CÙNG tập chương.** Bảng ba model ở trên thoả điều này (cả ba chạy đúng bốn chương ấy),
    nhưng một bảng gộp hai tập chương khác nhau là vô nghĩa dù trông đầy đặn hơn;
  - **chênh lệch nhỏ chỉ đáng tin khi tập đủ lớn.** 4 chương = 399 dòng có đáp án người nói; thêm 6 chương
    thành **1.034 dòng**, nên 1,6 điểm chuyển từ ~6 đoạn thành ~17 đoạn. Đó là lý do chạy thêm 6 chương
    thay vì kết luận từ 4.

Vì sao cấu trúc KHÔNG giải thích được: đếm trên đáp án thì hai tập gần như trùng nhau - thoại 32,3% so với
33,1%, nội tâm 5,5% so với 7,3%, dòng có >1 đáp án 11,8% so với 13,7%; chỉ số người nói khác nhau mỗi
chương (10 so với 8) và dòng nhận NPC (8,3% so với 5,0%) nghiêng nhẹ về phía khó. Cũng không phải một
chương ngoại lai: `qwen3:8b` theo từng chương ra **51,5 / 54,8 / 67,0 / 76,7** ở tập khó và
**66,7 / 75,0 / 78,0 / 78,8 / 81,0 / 84,6** ở tập dễ - cả tập thấp hơn, và phương sai trong mỗi tập cũng lớn.

### Phép so ĐÚNG là so theo cặp từng chương, không phải so hai trung bình

Mười giá trị theo chương ấy có độ lệch chuẩn **~11 điểm**, nên sai số chuẩn của trung bình dù trên 10
chương vẫn **~3,5 điểm**. Một chênh lệch 1,6 điểm giữa hai model nằm gọn trong đó - *nếu* đọc bằng hai
trung bình độc lập.

Nhưng cả hai model chạy **đúng cùng những chương ấy**, nên đây là thiết kế **theo cặp**: lấy hiệu từng
chương rồi đếm model nào thắng bao nhiêu chương. Cách ấy triệt tiêu phần lớn phương sai do chương - thứ
vừa đo được là to gấp bảy lần hiệu ứng cần tìm. Thắng 8/10 chương là tín hiệu; thắng 5/10 là nhiễu, dù
trung bình nhích lên.

### Và phép so theo cặp LẬT LẠI kết luận 4 chương (21-09 06:5x)

| chương | `qwen3:8b` | `qwen3:4b` | hiệu |
|---|---|---|---|
| 351 | 76,7 | 85,6 | **+8,9** |
| 363 | 51,5 | 45,5 | -6,0 |
| 378 | 67,0 | 64,9 | -2,1 |
| 381 | 54,8 | 59,7 | +4,9 |
| 385 | 81,0 | 76,2 | -4,8 |
| 396 | 66,7 | 76,1 | **+9,4** |
| 399 | 78,8 | 75,0 | -3,8 |
| 400 | 75,0 | 69,6 | -5,4 |
| 407 | 78,0 | 70,7 | -7,3 |
| 415 | 84,6 | 84,6 | 0,0 |

**Thắng theo chương: 8b 6 - 4b 3 - hoà 1.** Hiệu trung bình **-0,62** điểm, độ lệch chuẩn 6,22, sai số
chuẩn **1,97** - không đáng kể. Gộp 10 chương: `qwen3:8b` **81,6** / người nói **72,3**; `qwen3:4b` 81,2 /
71,7. Thời gian 94 phút so với **69 phút**.

Nói thẳng: **con số 4 chương ("4b hơn 1,6 điểm người nói") là nhiễu** - đúng thứ mục trên đã gắn cờ trước
khi có dữ liệu. Phát biểu đúng: `qwen3:4b` **không phân biệt được về chất lượng** với mốc 8B
(-0,6 ± 2,0), mà nhanh hơn **27%** và nhẹ hơn 1,5 GB. Lý lẽ đổi model chuyển từ "tốt hơn" sang "ngang
chất lượng, rẻ hơn rõ" - yếu hơn, nhưng đây là lý lẽ chịu được một lượt đo thứ hai.

Vì sao vẫn đáng theo: phân tích chiếm **40% giờ máy một lô** (`docs/THROUGHPUT.md`), nên -27% ở khâu ấy là
lô nhanh hơn ~11%, và 1,5 GB VRAM trả lại là đúng thứ kế hoạch "chồng lấn giai đoạn" đang thiếu. Bước kế
ở cửa sổ GPU sau: chạy lại `qwen3:4b` so `qwen3:8b` trên **10 chương** đáp án thay vì 4, để tách 0,6 điểm
kia khỏi nhiễu trước khi bàn đổi model sản xuất.

`gemma4:e2b-it-qat` là sàn tốc độ: nhanh **2,6 lần** mốc với 1,8 GB, đổi lấy 2,2 điểm.

## Nguồn dữ liệu MỚI: lỗi mà nhiều model CÙNG mắc là lỗi của host (21-09 04:3x)

Một lượt so model cho nhiều hơn một bảng điểm: ba model trả lời **cùng** bốn chương đáp án, nên so chúng
với NHAU tách được hai loại lỗi.

    177 đoạn cả ba model đều trả lời và có đáp án người nói
        17  MỌI model cùng sai   <- luật host còn thiếu; vá một lần thì mọi model đều lợi
        28  chỉ một số sai       <- chuyện của từng model

Lớp lớn nhất trong 17 chỗ ấy đã thành một bản vá (xếp cho ranh giới 12): lời kể ngôi ba mà bộ tách đoạn gán
`thought`, cả ba model cùng nêu một người nghĩ - `363:70-72`, "Một tia không màu… bắn thẳng vào Bellak" đọc
bằng giọng LUCIEN. Xem `scripts/pending_patches/patch_a_thought_outside_every_quote_belongs_to_the_narrator.py`
cho cả ba phép thử, **hai cái đầu bị loại** (một cái lợi = 0, một cái PHÁ 29 dòng đáp án vì tiếng Việt cho
trống chủ ngữ), và cho hồi quy mà cổng bắt được: `yamiyo_no_hotaru` viết nội tâm bằng **dấu ngoặc đơn**.

Lớp còn lại chưa vá được: `363:34-36`, một lượt thoại dài của BELLAK mà cả ba model gán cho LUCIEN,
NARRATOR hoặc UNKNOWN - **thiên lệch về nhân vật được nhắc nhiều nhất**. Không có mặt chữ nào trong đoạn
chỉ ra BELLAK; đây là lỗi model thuần, và nó là lý do tốt nhất để huấn luyện model chuyên.

### Giả thuyết: chính PROMPT của chúng ta phát cái thiên lệch ấy (21-09 05:4x) - CHƯA đo, cờ đã có

Đo hạng của nhân vật bị chọn trong bảng `mention_count` của chính project, chuẩn hoá 0 = nổi tiếng nhất:

| model | khi chọn SAI | khi chọn ĐÚNG |
|---|---|---|
| `qwen3:4b` | **0,022** (n=34) | 0,205 (n=52) |
| `gemma4:e2b-it-qat` | **0,062** (n=13) | 0,233 (n=43) |
| `qwen3:8b` | **0,101** (n=26) | 0,251 (n=45) |

Đoán sai rơi vào **top 2-10%** bảng nổi tiếng; đoán đúng thì rải rộng hơn gấp 2-10 lần. Giống nhau ở cả
ba model. Và chỗ đáng ngờ nằm trong chính prompt: `_known_summary` liệt kê 80 nhân vật **xếp theo số lần
gặp giảm dần**, mỗi dòng kèm `số lần đã gặp=<n>`. Tức ta tự tay đưa cho model một **bảng xếp hạng độ nổi
tiếng** - cả con số lẫn thứ tự - trong khi luật của prompt chỉ đòi nhất quán **tên** và **giới tính**.

Chưa kết luận được nhân-quả từ tương quan này: model có thể nghiêng về nhân vật nổi bật dù prompt không
nói gì. Tách được bằng một phép thử, và nó chỉ chạy được trên GPU thật (phát lại KHÔNG đo được bản vá đổi
prompt):

    python scripts/model_eval/eval_models.py qwen3:8b --chapters 351 363 378 381 385 396 399 400 407 415 \
        --known-list no-counts --root D:/Novels/Audiobooks/_model_eval_v2/21-09-no-counts

Cờ `--no-mention-counts` (cả ở `analysis_only.py`) bỏ con số và xếp danh sách theo TÊN, **giữ đúng mức
chặn 80** người. So theo CẶP với mốc `qwen3:8b` 10 chương ở mục trên (điểm 81,6 / người nói 72,3).

**Giới hạn của phép thử, nói trước khi có kết quả.** Giữ mức chặn 80 không đủ để giữ độ dài: 80 dòng
`số lần đã gặp=<n>` là chừng **500 token**, và đo lúc chạy thì prompt xuống 2.528-3.181 token so với
~3.172 của mốc. Không thể bỏ thông tin mà không bỏ token, nên lượt này trả lời đúng MỘT câu: *"bỏ tín
hiệu nổi tiếng (cùng độ dài kèm theo) có giúp hay không?"* Nếu KHÔNG giúp thì giả thuyết đóng lại và
hết chuyện. Nếu GIÚP thì còn phải tách hai nửa bằng hai lượt nữa, và **cả hai cờ đã viết sẵn** (`--known-list`):

| biến thể | thứ tự | con số | độ dài | tách được gì |
|---|---|---|---|---|
| `baseline` | theo độ nổi tiếng | có | - | mốc |
| `no-counts` | theo TÊN | bỏ | **-~500 tok** | (cả hai nửa lẫn độ dài) |
| `sorted-by-name` | theo TÊN | **giữ** | gần như nguyên | chỉ THỨ TỰ |
| `masked-counts` | theo độ nổi tiếng | thay bằng `?` | gần như nguyên | chỉ CON SỐ |

Đã kiểm văn bản prompt sinh ra của cả bốn biến thể mà không cần GPU (gọi hàm đã vá với một đối tượng giả),
và cổng `analysis_only.py` từ chối khi chọn hai biến thể cùng lúc. **Đừng công bố "prompt gây thiên lệch"
trước khi có `sorted-by-name` hoặc `masked-counts`.**

### Bài học ĐO: đừng chấm một project khi các bước sau phân tích chưa xong

Tôi chấm `gemma4:e2b-it-qat` hai lần trên **cùng bốn chương** và ra **74,8** rồi **77,2**. Không phải nhiễu:
sau `analyze_all` còn `local_identities` - bước hợp nhất NPC vô danh vào nhân vật có tên - và nó **ĐỔI trường
`speaker`**. Đọc sổ lúc ấy là đo một mục tiêu đang di chuyển, và tôi đã kịp báo một khoảng cách sai (4,6
điểm thay vì 2,2) trước khi tự bắt.

Dấu hiệu xong của MỘT chương là **`model_eval_run.json`** trong thư mục project, không phải "đã phân tích đủ
số đoạn". Điều kiện chờ nào dùng số đoạn cũng sẽ thức sớm.

**Và chỉ báo tiến độ phải là `segments.status`, KHÔNG phải `segments.speaker`.** Tôi theo dõi cả một lượt đo
bằng `count(*) where speaker is not null and speaker<>''` và nó luôn trả về "đủ 100%" ngay khi chương vừa
chia đoạn - vì `speaker` **có giá trị mặc định**: lúc đang chạy, một project 97 đoạn với 85 đoạn `pending`
vẫn hiện `NARRATOR` 52, `UNKNOWN` 40. Truy vấn đúng là `status<>'pending'` (`pending` / `analyzed`) - và đó
tình cờ là truy vấn tôi viết ĐẦU TIÊN rồi tự đổi sang cái sai.

Ba cái bẫy trong một buổi, cùng một hình dạng - **một dấu hiệu trông như câu trả lời nhưng không phải**:
dòng log `Đã dừng Ollama ẩn...` đọc thành nguyên nhân; `ollama show --template` in `{{ .Prompt }}`; và cột
`speaker` có mặc định. Cách chống duy nhất đã hiệu quả: hỏi "dấu hiệu này SAI thì trông thế nào?" rồi đo
đúng câu ấy - probe `system`, so bản gốc với bản vá, đếm `status` thay vì `speaker`.

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

**Một cái bẫy đọc, kiểm trước khi tin một điểm số (21-09 04:5x).** `ollama show gemma4:e2b-it-qat --template` in
ra đúng `{{ .Prompt }}` - không có `{{ .System }}`. Đọc nguyên văn thì nghĩa là Ollama BỎ khối `system`, tức
quyển luật 1.190 token không đến tay model và mọi điểm của gemma đo một thứ khác. Đo thử thay vì suy luận:

    POST /api/generate  system="chỉ được trả lời đúng một từ: DUALIEU"  prompt="Hôm nay trời thế nào?"
    gemma4:e2b-it-qat -> 'DUALIEU'      qwen3:8b -> 'DUALIEU'

Cả hai tôn trọng `system`. Ollama 0.33 dùng renderer dựng sẵn cho model mới và `--template` chỉ in chỗ giữ chỗ,
nên dòng ấy không nói gì về việc `system` có được ghép hay không. Cùng họ với cái bẫy log đã ghi ở
`docs/WHAT_BLOCKS_A_CHAPTER.md`: **thứ tự và hình thức trong đầu ra của công cụ không phải là hành vi.**

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

### BỨC TƯỜNG: 8 GB VRAM không huấn luyện được model 4B ở độ dài prompt của dự án (21-09 03:1x)

Tôi ước một epoch mất 2-3 giờ. **Sai một bậc độ lớn**, và đây là số đo:

| cấu hình | mỗi mẫu (~3,2k token) | quy ra | một epoch (1.727 mẫu) |
|---|---|---|---|
| Qwen3-4B 4-bit, `paged_adamw_8bit`, accum 8 | 85 s | **38 token/s** | **~40 giờ** |
| cùng thế + `adamw_8bit` (không paged) + `expandable_segments` | 254 s | **12,6 token/s** | còn tệ hơn |

Giới hạn TÍNH TOÁN của máy này vào khoảng 1.000 token/s cho việc ấy (7,7e13 FLOP mỗi mẫu với gradient checkpointing,
~15 TFLOPs bf16 hiệu dụng). Chạy ở 12-38 token/s tức chậm gấp **17-80 lần** giới hạn, và `nvidia-smi` chỉ đúng chỗ:
**7.723 / 8.151 MiB (95%)**. Đó là tràn VRAM, không phải thiếu FLOP - và cái giá của nó lớn hơn mọi mẹo tinh chỉnh.

Hai đường thoát hiển nhiên, cả hai bị chính phép đo chặn:

  - **giảm `max_length`**: ở 1024, TRL loại **mọi mẫu** (`num_samples=0`) - cắt prompt là cắt mất câu trả lời, đúng
    điều đã ghi trong docstring của `train_lora.py` trước khi chạy;
  - **model nền nhỏ hơn**: `Qwen/Qwen3-1.7B` là model **hybrid thinking**, và khuôn chat của nó tự chèn
    `<think>

</think>` trước nội dung assistant. Huấn luyện qua khuôn ấy là dạy model sinh khối think, rồi
    `json.loads` ở sản xuất vỡ - đúng cái đã làm `qwen3.5:9b` trả "0/5 IDs" đêm 19-09. Dòng `-Instruct-2507` (bỏ chế
    độ nghĩ) chỉ có ở 4B và 30B.

Vậy muốn tự huấn luyện trên máy này thì phải chọn một trong ba, và cả ba đều là **quyết định của chủ sách**:

  1. **rút ngắn prompt sản xuất** - 2,9k trong 3,2k token là prompt (ngữ cảnh + danh sách nhân vật đã biết). Ngắn
     hơn thì huấn luyện được, nhưng đó là đổi chính prompt đang cho 68-77% người nói, tức một quyết định chất lượng;
  2. **model nền cỡ 2B không có chế độ nghĩ** (ví dụ `gemma-4-e2b-it`) - phải viết lại phần dựng dữ liệu vì khuôn
     chat của gemma không có vai `system` riêng;
  3. **bỏ tự huấn luyện**, dồn sức chọn model có sẵn tốt nhất - việc đang chạy ở mục dưới.

Tối nay tôi chọn (3) để không đốt cả đêm vào một epoch 40 giờ, và ghi lại (1)(2) kèm số đo để chủ sách quyết.

#### Mổ prompt: 42,5% mỗi token huấn luyện là MỘT TRONG HAI khối chỉ dẫn tĩnh (21-09 04:2x)

Câu "2,9k trong 3,2k token là prompt" ở trên đúng nhưng còn thô. Đếm bằng chính tokenizer của model nền
(`Qwen/Qwen3-4B-Instruct-2507`, đo trên `D:/Novels/LLM_Train/data/train.jsonl`):

| lượt | mẫu | token trung vị | **khối `system` tĩnh** | phần thay đổi theo chương | đáp án |
|---|---|---|---|---|---|
| generator | 864 | 2.488 | **1.190 (47,8%)** | 948 | 360 |
| phản biện | 863 | 3.290 | **1.399 (42,5%)** | 1.298 | 596 |
| cả tập | 1.727 | 3.198 | **2,235 M / 5,265 M = 42,5%** | | |

Và chỉ có **đúng hai** khối `system` khác nhau trên 1.727 mẫu (864 + 863), giống nhau từng byte. Đó là quyển luật
- không phải ngữ cảnh truyện.

Việc này **sửa lại lựa chọn (1)**: rút prompt KHÔNG nhất thiết là đổi nội dung đang cho 68-77% người nói. Phần
mang chất lượng (danh sách nhân vật đã biết, `previous_text`/`next_text`, văn bản đoạn) nằm trong vai `user` và
giữ nguyên; thứ bỏ đi là quyển luật, mà huấn luyện chính là chuyển quyển luật ấy từ prompt vào trọng số - rồi
sản xuất dùng đúng prompt ngắn ấy. Không đổi một chữ nội dung.

Nhưng nó **không phá nổi bức tường**, và đây là chỗ phải nói thẳng: bỏ hết khối tĩnh còn 3,03 M token/epoch,
ở 38 token/s đã đo là **~22 giờ** thay vì ~40. Gấp 1,7 lần, mà bức tường cần gấp 13. Ẩn số duy nhất còn lại là
**38 token/s ấy đo ở mức VRAM 95%** - chuỗi ngắn hơn thì bớt tràn, tốc độ có thể nhảy hơn tỉ lệ token. Đó là một
phép đo GPU, chưa làm, và làm được trong 20 phút ở cửa sổ GPU kế tiếp:

    # cắt khối system còn một câu, giữ nguyên vai user + đáp án, rồi đo lại giây/mẫu
    python scripts/model_eval/train_lora.py --smoke 8 --max-length 2560 --short-system

Nếu tốc độ chỉ nhích theo tỉ lệ token thì (1) chết hẳn và chỉ còn (2)(3). Chưa có cờ `--short-system`: viết sau
khi có phép đo, đừng viết trước.

#### Số phụ cho câu hỏi khác của chủ sách: nếu CHÍNH TÔI làm LLM phân tích

Cùng dữ liệu ấy đếm theo chương (59 chương có dữ liệu thật, gồm cả lượt sinh và lượt phản biện):

| | trung vị mỗi chương |
|---|---|
| lượt gọi LLM | 39 |
| token vào | 107.531 (trong đó khối tĩnh 50.381) |
| token ra | 18.135 |

Quy ra giá Sonnet 5 (vào 3 $/M, ra 15 $/M, đọc lại cache 0,30, ghi cache 3,75): **0,59 $/chương**, còn
**0,47 $** nếu bật cache tiền tố (-21%, vì khối tĩnh chỉ phải ghi hai lần). Cả cuốn 2 (915 chương) là
**544 $**, hay **428 $** có cache; phần chưa đúc (460-915) là **271 $** / **213 $**. Đây là số để chủ sách
biết bậc độ lớn, không phải một đề xuất.

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
