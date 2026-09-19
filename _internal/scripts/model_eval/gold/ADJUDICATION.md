# Sổ phân xử đáp án chuẩn

Mỗi tranh chấp giữa hai người gán nhãn (A = Claude, B = agent review) và kết luận. Quy tắc: `docs/GOLD_GUIDE.md`.

## Vòng 1 - làm mù (20-09 00:0x): B gán độc lập 378 (cuốn 2) và 248 (cuốn 1)

Độ khớp trước phân xử, trên 94 câu có người nói: người nói ưu tiên trùng 97,9%, tập đủ-điểm giao nhau 100%; loại đoạn
100% (248/248); giới tính 100% (81/81); cảm xúc ưu tiên trùng 89,1%, tập giao nhau 100%.

| câu | A | B | kết luận | lý do |
|---|---|---|---|---|
| 378:1, 48, 87, 91, 93, 95 | chỉ tên | tên + `NPC*~` | theo B | lúc nói, người ấy chỉ được gọi "đại trưởng lão"/ẩn danh; tên ở ngay đoạn kề - quy tắc 5 |
| 378:4, 33, 116, 117 | `NPC*,UNKNOWN` + ... | bỏ `UNKNOWN` | ~~giữ A~~ **bị vòng 2 thay**: `UNKNOWN~` | (cũ) câu cả đám: `UNKNOWN` đủ điểm |
| 378:61 | `NPC*,UNKNOWN` | + 4 người có tên đủ điểm | nửa đường | "Tất cả người lùn... hét lớn": không ai dẫn đầu, người có tên chỉ nửa điểm - quy tắc 6 |
| 378:79 "Aaaaah!" | `NPC*,UNKNOWN` | + `NARRATOR~` | theo B | tiếng thét là của nhân vật; người kể đọc thì chấp nhận được nhưng kém |
| 378:113 | thiếu Myrna, Quinns | có | theo B | câu 112 nêu tên họ đang cầu nguyện |
| 248:13 | `SAMAEL` | + `JULIANA~` | giữ A | câu 14 "Ngay cả Juliana cũng lộ vẻ bối rối" - câu 13 chưa phải của cô; cả B cũng chọn Samael |
| 248:32, 57, 72 | `NARRATOR` | + nhân vật `~` | giữ A | loại bị khoá lời kể; host ép NARRATOR nên nửa điểm nhân vật không bao giờ xảy ra |
| 248:48 "À, ra là..." | `N` | `N,T` + SAMAEL | theo B | câu tự nhủ trực tiếp - quy tắc 4 |
| 248:129 | `N,T` + SAMAEL | `N` | giữ A | cùng quy tắc 4 |
| 248:27..65 Ray/Vince | tên + tên đầy đủ | chỉ tên | giữ A | bí danh cùng người - quy tắc 10 |
| 248:77 "Samael, nằm xuống!" | âm lượng normal trước | loud | theo B | tiếng hét |
| 248:79, 101 "Rầm—!!" | surprised,neutral | excited | nới A | thêm excited |
| 248:81 "Á hự!" | sad trước | không có sad | nới A | surprised lên đầu; sad giữ ở cuối (đau) |
| 248:92 | nhịp normal trước | fast | giữ A | cả hai hợp lý, tập A đã có fast |

## Vòng 2 - soát đối kháng (20-09 00:1x): B đọc đáp án của A cho 351, 363, 381 và tìm lỗi

B không tìm ra người nói CHÍNH sai ở câu nào; ~28 câu tranh chấp về điểm của lựa chọn phụ, thứ tự loại, cảm xúc.

| câu | B đề nghị | kết luận | lý do |
|---|---|---|---|
| mọi câu có manh mối (41 dòng, mọi chương) | `UNKNOWN` -> `UNKNOWN~` | theo B | prompt dự án: UNKNOWN chỉ khi không có dấu hiệu gì |
| 381:13 | thêm MYRNA đủ điểm | theo B | câu 12: "dẫn dắt **Myrna** và những người lùn khác đáp lại" |
| 381:9, 378:4 | HAROLD (và MYRNA ở 378:4) đủ điểm | theo B | được nêu tên trong lời dẫn của câu cả đám |
| 381:17, 21, 31 | thêm MYRNA~, QUINNS~ | theo B | có mặt, không được nêu trong lời dẫn |
| 351:67 "mỉm cười" | bỏ MORRIS | theo B | từ trong ngoặc là mô tả, không phải lời |
| 351:13, 15, 17 | người gốc của từ -> nửa điểm | theo B | đổi giọng giữa một câu kể là sai |
| 381:79 khế ước | tác giả (thần = LUCIEN) đủ điểm, bỏ Augustus/Harold | theo B | tác giả văn bản; người ký không đọc to |
| 381:38 tựa sách | NARRATOR đủ điểm | theo B | văn bản trích |
| 363:69-78, 80 | `T,N` -> `N,T` | theo B | loại thật đứng trước; chính chú thích của A nói đây là lời kể |
| 363:68 | NARRATOR đủ điểm | theo B | đoạn nửa nghĩ nửa kể, loại N được chấp nhận |
| 363:42-43 | thêm neutral, happy; cường độ 1-2 | theo B | câu 40-41: hắn vừa "dằn được cảm xúc xuống" |
| 363:23 | thêm afraid | theo B | câu nói về nỗi sợ cơn giận của Fernando |
| 381:63 | `N,T` + NPC*~ | theo B (điểm yếu) | tiếng lòng chung của đám người lùn, như 363:48 |
| 381:11, 15, 19, 28 giọng "thần" | `NPC*` -> `NPC*~` | **giữ A** | thần chỉ xuất hiện trong arc này; một giọng NPC riêng, nhất quán trong chương là cách đọc đúng, không kém gán tên |

A tự áp cùng quy ước cho chương B chưa soát: 344:68, 93 (tựa luận án Chloe chỉ nhìn thấy) và 344:72, 95, 345:27, 38 (câu
trích luận án: tác giả Lucien đủ, người đọc ~); 050:61-62 (lời nhạc chuông: NPC*~).

## Vòng 3 (20-09 00:2x): B làm mù 344, 345; soát đối kháng 346, 347, 199, 020, 050

Làm mù 344/345 (74 câu có người nói): người nói ưu tiên trùng 98,6%, tập chấp nhận 100%; cảm xúc ưu tiên 94,8%, giao 100%.
Soát 5 chương: không có người nói chính sai; 28 câu tranh chấp.

| câu | kết luận | lý do |
|---|---|---|
| 381:11, 15, 19, 28 giọng thần | **A thua**: `NPC*` -> `NPC*~` | B dẫn chứng: thần nói lại ở chương 460 (585, 793 lộ là Lucien); nhãn NPC chỉ sống trong một chương (`_scope_local_speaker`, hai lượt gộp chỉ cùng chương) nên mỗi chương một giọng |
| 344:44, 345:15 | người đọc to + NARRATOR đủ, tác giả `~` | văn bản đọc to bằng giọng người đọc - quy tắc 7 mới |
| 344:68, 93 | + LUCIEN đủ | tiêu đề chỉ được nhìn thấy: tác giả đủ điểm |
| 344:75, 76 | + LUCIEN~ | câu của Lucien vang lại trong đầu Chloe |
| 344:82, "Aaaaah!" | + NARRATOR~ | như 378:79 |
| 344:4 | `N,T` + ERIC | tiếng lòng của Eric ("Tốc độ khiếp luôn!") |
| 345:84-85 kết luận hội đồng | `NPC*~` | người viết không tên - quy tắc 7 |
| 347:20 | NARRATOR đủ, người thì thầm `~` | **A sai**: cụm trích nằm giữa câu kể - quy tắc 8 |
| 346:78 Lauren, 347:27 Larry, 050:64/67/70 người gọi điện | + `NPC*~` | quy tắc 5 áp đều cho người chưa xác định lúc nói |
| 346:46 | + LAZAR~, HEIDI~, SPRINT~ | có mặt, không được nêu trong lời dẫn - quy tắc 6 |
| 347:48-51 thư Douglas | + DERRICK DOUGLAS (bí danh), HELLEN~ (người đọc) | quy tắc 7, 11 |
| 050:32 | bỏ CHÚ LƯU ĐẠT | prompt dự án cấm tiền tố vai vế |
| 346:38, 199:88, 103, 104, 020:41-43 | `N,T` + người nghĩ | câu tự nhủ trực tiếp - quy tắc 4 |
| 346:39 | **giữ A** (`N`) | câu giải thích của người kể, không phải tiếng lòng |
| 020:19 | **giữ A** (`N`) | có lời dẫn "Chu Mặc tán thưởng" - là lời kể |
| 346:5, 14, 199:86 | cường độ 1-3 -> 1-2 | văn bản nói rõ không phải cao trào ("có chút phấn khích") |
| 199:111, 137, 050:26, 29 | + whispering | lẩm bẩm |
| văn bản viết có người viết đứng đầu (345, 347, 351:73, 344:75-76) | giới tính của người viết | quy ước giới tính mới |

## Vòng 4 (20-09 00:3x): CẢ HAI làm mù hai truyện mới - hdst 060, nise 030

A (Claude) và B (agent review) gán độc lập, không xem bản của nhau. Hai truyện đều ngôi thứ nhất, bản dịch nghiệp dư
có lỗi (đại từ đảo, tên viết nhầm). Hợp nhất bằng `merge_gold.py merge` (hợp các tập chấp nhận, ưu tiên theo A) rồi phân
xử từng câu lệch dưới đây. 86 câu có người nói: người nói ưu tiên trùng 87,2%, tập chấp nhận tương thích 100%; loại trùng
hệt 234/238; cảm xúc ưu tiên 95,0%, giao 100%. Mọi câu lệch ưu tiên đều là `N` với `N,T` - không câu nào hai bên chọn
hai người khác nhau. gold_replay: 49 lượt generator + 49 critic, không LỆCH LUẬT; điểm replay 100.

| câu | kết luận | lý do |
|---|---|---|
| nise 12, 23, 25, 45 | **A thua**: `N` -> `N,T` + MAGALI đủ | A tự mâu thuẫn: đã cho `N,T` các câu cùng kiểu 7 ("Tại sao tôi phải giả vờ...? Vì thích? Không"), 18, 42. Trong lời kể ngôi thứ nhất ở hiện tại, phản ứng tức thời của người kể (câu hỏi tu từ, "Thôi chết.", nói thầm với người trước mặt "tôi muốn anh làm tường thịt") là tiếng lòng - quy tắc 4 |
| nise 13 ("Rõ ràng là lợi bất cập hại mà"), 11 ("mọi người hiểu mà đúng không?") | giữ `N` (hai bên cùng) | giải thích/nói với người đọc, không phải tiếng lòng tức thời |
| nise 5, 21, 41, 44, 49, 68, 75, 79 | bỏ THÁNH NỮ~ | **A sai**: danh hiệu trơn - prompt dự án cấm danh xưng trong nhãn, và nhãn danh hiệu tách thành một giọng thứ hai của cùng người. Quy tắc 11 mở rộng |
| hdst 151 | bỏ GIÁO SƯ GLAST~ | **A sai**: quy tắc 11 đã cấm tiền tố vai vế từ vòng 3 (CHÚ LƯU ĐẠT) |
| hdst 56, 60 | + `NPC*~` | B: Lucy chỉ được gọi tên ở 62 - quy tắc 5 |
| hdst 2, 36 "Hộc... hộc..." | + NARRATOR~ | B: tiếng thở của người là của người ấy - quy tắc 8 |
| hdst 20 "KÉTTTT!" (tiếng hét sắc lẻm, không rõ của ai) | NARRATOR, `NPC*` đủ; `UNKNOWN~` | B: có người/vật phát ra - quy tắc 8 |
| nise 16 | + ERIS~ | B: câu 17 dẫn câu này bằng "Eris" (lỗi dịch) - model đọc theo chữ vẫn đúng người |
| nise 48, 49 | + MAGALI~ / ERIA~ | B: bản dịch đảo đại từ ("em muốn ngài" là lời Eria); mạch truyện quyết định (50 "Đó là nói dối" = Magali nói 49), cách đọc theo đại từ nửa điểm |
| nise 83 "Tôi là Silk" | + `NPC*~` | B: thí sinh một lần - NPC chấp nhận được nửa điểm, dù cô tự xưng tên ngay trong câu |
| nise 58, 63 | + `UNKNOWN~` | A: có manh mối (kỵ sĩ hộ tống) - quy tắc 5 |
| cảm xúc, nhịp, âm lượng, cường độ | hợp hai tập | lệch nhỏ, không câu nào mâu thuẫn (giao 100%) |

## Vòng 5 (20-09 00:5x): cả hai làm mù TMA 407 (cuốn 2, chương 408) và Nageki 20 (truyện mới)

110 câu có người nói: người nói ưu tiên trùng **100%**, tương thích 100%; loại trùng hệt 285/285; cảm xúc ưu tiên 92,9% /
96,5%, giao 100%. gold_replay: Nageki 41 + 41 lượt, điểm replay 100; TMA 407 19 + 19 lượt, điểm replay 92,3 - 6 câu nội
tâm bị host ép NARRATOR (đã có `patch_a_thought_keeps_its_thinker.py` trong hàng chờ) và **407:78 bị luật host
`_explicit_speaker_attribution` đổi BEYER thành Lucien** (tên đầu câu kể sau: "Lucien còn chưa kịp làm gì khác, một giọng
nói... vọng đến") - lỗi sản xuất mới, xem `docs/LLM_EVAL.md`.

| câu | kết luận | lý do |
|---|---|---|
| 407:3-16 ghi chép rời | **A sai**: + THANOS đủ | B: 406 "ghi chép không hoàn chỉnh do Thanos để lại", 22 "ghi chép của Vua Mặt Trời Thanos" - A đọc sót chương trước |
| 407:78, 83 | + RUDOLF II~ | B: người trong xác Beyer là Hoàng đế Rudolf II (lộ ở chương 409); tên chương này gọi đủ điểm - quy tắc 13 mới |
| 407:80 "Beyer?" | + SOPHIA~ | B: Lucien là người nhìn, nhưng Sophia có mặt - chấp nhận nửa điểm |
| 407:63, 69 | **giữ A**: SOPHIA~ (B cho đủ) | đoạn kể NGÔI BA dài ("Nghe vậy, Sophia chợt... Cô nặng nề ngã xuống đất") chỉ có một câu tự nhủ ở đầu/cuối: đọc cả đoạn bằng giọng Sophia là sai giọng cho phần kể về chính cô. Quy tắc 4 bổ sung |
| Nageki 178 "Kill…" | + NARRATOR~ | B: tiếng rống của sinh vật là của nó - quy tắc 8 |
| Nageki 163 "nguyên liệu" | + SITRI SMART~ | bí danh |
| Nageki 102 | giữ SITRI~ của A | vô hại: host luôn đưa narration về NARRATOR |

Góp ý luật của B (đều nhận): quy tắc 4 bỏ chữ "ở hiện tại" (Nageki kể ở quá khứ mà các câu kêu thầm vẫn là tiếng lòng);
quy tắc 9 nói rõ nội tâm bị khoá D -> `T,D`, người nghĩ đủ điểm; quy tắc 7 nói rõ tác giả được gọi tên ở chương khác
hay trích dẫn thoáng qua; quy tắc 13 mới cho nhập xác/cải trang.

## Vòng 6 (20-09 01:0x): cả hai làm mù TMA 419 (chương 420) và Yamiyo no Hotaru 155 (truyện ngoặc 「」)

Yamiyo làm trên bộ tách đoạn SAU `patch_a_corner_bracket_is_a_quote.py` (54/107 đoạn là thoại; trước bản vá là 0). 113 câu
có người nói: người nói ưu tiên trùng **100%**, tương thích 100%; loại trùng hệt 215/215; cảm xúc ưu tiên 93,6% / 84,0%,
giao 100%. Mọi chỗ lệch là bí danh (HOTOYA TAMAKI, AKOU/AKO MURASAKI do B đếm trong kho) và nửa điểm:

| câu | kết luận | lý do |
|---|---|---|
| 419:47 | **A thua**: BAREK~ -> đủ | B: lời dẫn nêu cả hai ("Công tước James và pháp sư bậc bảy Barek... nhỏ giọng thở dài"); quy tắc 6 bổ sung |
| 419:69-70 danh sách "cách chết ngu ngốc nhất" | + BAREK~ | B: Barek vừa nói về pháp sư chết vì điện (67) - có thể đọc như ông trích |
| Yamiyo 80 "Ừ. … Đi thôi." | giữ IRUKA~ của A | Tamaki tự nhủ khi đứng dậy (81) nhưng câu "Ừ" cũng hợp lời Iruka |
| bí danh | hợp hai bên | quy tắc 11 |

replay TMA 419 (host hiện hành): 98,2 - **419:24, 26 ("dây chuyền lắp ráp", "tiêu chuẩn hoá", thuật ngữ trích giữa câu kể)
bị host đổi NARRATOR thành Arthur**, người nói của đoạn văn. Lượt kiểm toàn bộ (mọi chương đáp án phát lại) đang chạy.
Góp ý luật của B (nhận cả ba): quy tắc 6 cho lời dẫn nêu hai người, ví dụ Yamiyo 43 ở quy tắc 10, tiêu đề lặp ở đoạn 1.

## Vòng 7 (20-09 01:2x): B gán một mình, A soát đối kháng - TMA 396, Năng lực bá đạo 0135, Love Unseen 09

B làm nhanh hơn A nhiều (một chương ~3 phút), nên ba chương này B gán và A đọc lại từng câu với nguồn thay vì làm mù.
B tự liệt kê các câu kém chắc chắn nhất; A soát toàn bộ. B chắc tay: A chỉ đổi 6 dòng người nói trên 476 đoạn.

| câu | kết luận | lý do |
|---|---|---|
| TMA 396:16 "Ác quỷ…" | + ANDRIS~ | câu thì thầm có dấu lửng, khớp cách Andris đang quỳ nhìn Lucien ("con quỷ đáng sợ nhất thế giới", câu 1) hơn tiếng la của đám bỏ chạy |
| Năng lực 0135:31-114 (Trịnh Vĩnh Mong) | bỏ `NPC*~` | **B sai**: quy tắc 5 chỉ cho `NPC*~` câu nói TRƯỚC khi được gọi tên (9-16); từ câu 17 anh ta có tên. Trịnh lão giữ `NPC*~` (không có tên riêng, nói lại ở nhiều chương - lô-gic giọng thần vòng 3) |
| Love Unseen 09:28 | HAYASE đủ -> ~ | câu kể nêu hai người ở đoạn văn KHÁC và chỉ tả họ vẫy tay - không phải lời dẫn; Narumi là người châm pháo (30) |
| Love Unseen 09:42, 43, 50 | người thứ hai đủ -> ~ | hai câu liên tiếp sau "Hayase và Narumi gọi Fuyutsuki" là mỗi câu một người (42 gọi "Koharu" = lối Hayase), không phải một câu hai người cùng nói; quy tắc 6 bổ sung |

Góp ý luật của B (nhận): họ + kính xưng là tên khi nhân vật không có tên riêng (quy tắc 11); tên cải trang nửa điểm trên
câu nói, không điểm trên câu nghĩ (quy tắc 13).

## Vòng 8 (20-09 01:3x): TMA 418 cả hai làm mù; TMA 385, Two Childhood Friends 013 B gán - A soát

TMA 418 (làm mù): người nói ưu tiên trùng 97,0% (33 câu), loại 89/89, cảm xúc ưu tiên 98,9%.

| câu | kết luận | lý do |
|---|---|---|
| 418:32 "Chẹp. Thật là một thanh niên có tinh thần văn nghệ, à không, ông già mới đúng. Lucien cười thầm trong lòng." | **A thua**: LUCIEN~ -> đủ | B: phần lớn đoạn là tiếng lòng trực tiếp, lời dẫn ngắn. Khác 419:32, nơi phần kể gọi Lucien là "cậu" |
| 418:41 hai học trò cùng chào, gọi tên ở 44 | **A thua**: NPC* đủ -> `NPC*~` | quy tắc 5: người được gọi tên sau trong chương; LILLIAN, ISAAC đủ |
| 385:20, 95, 109 (Sana, Aska, Inke) | **B sai**: bỏ `NPC*~` | tên có ngay ở lời dẫn liền sau câu ("Nhân sư cái Sana nhìn Lucien và nhỏ giọng nói:") - lời dẫn thường, như 419:5 Lillian mà cả hai bên đều không cho NPC. 35 Helges giữ `NPC*~`: lời dẫn không nêu tên |
| 385:123 Lucien trong hình Aska | LUCIEN, ASKA đều đủ | quy tắc 13: chương gọi "Aska", nhưng đã lộ ngầm trước câu (Aska thật bất tỉnh ở 119) |
| Two Childhood 013 | không đổi | soát từng câu với nguồn |
| 385:123 (bổ sung) | ASKA đủ -> ~ | B tự đề xuất: lời dẫn dùng tên giả "Aska" nhưng danh tính thật đã lộ trước câu; tên giả nửa điểm như Beaulac - quy tắc 13 bổ sung |
| Yamiyo 189 | không đổi | B xác minh "sư phụ" = Kaede Tomoe (corpus 168); 29 câu của kẻ nhập xác Yuusei trong 『…』 bị khoá lời kể -> NARRATOR (quy tắc 10) |

Phát hiện sản phẩm từ vòng này (chưa vá): ngoặc 『…』 NGUYÊN DÒNG là một giọng nói ở ba truyện - kẻ nhập xác (Yamiyo, 6.185
dòng), loa/điện thoại (Two Childhood, 691), bảng hệ thống game (Năng lực bá đạo, 5.048) - nhưng bộ tách đoạn khoá lời kể.
Bản vá 「」 cố ý không đụng 『』 (thuật ngữ trong câu, ngoặc lồng). Cần đo riêng trước khi vá; không vào ranh giới 9.

## Vòng 9 (20-09 01:4x): TMA 436 cả hai làm mù; TMA 426, hdst 090 B gán - A soát

Hai chương TMA chọn vì có lời dẫn "X quay sang/nhìn Y nói:" mà host cũ khoá cho người NGHE; chúng thuộc lô 10, sẽ chạy
với host đã vá - đáp án để đo bản vá có ăn trong sản xuất thật. TMA 436 (làm mù): người nói ưu tiên trùng **100%** (39
câu), loại 83/85, cảm xúc ưu tiên 88,2%.

| câu | kết luận | lý do |
|---|---|---|
| 436:7, 16, 25, 64 | hợp hai bên (thêm `~`) | B: Heidi/Lazar có mặt ở 7, 25; Florencia/Raventi ~ ở 64 |
| 436:72 | giữ A: LUCIEN đủ | phần lớn đoạn là câu hỏi thầm của Lucien, chỉ mở bằng "Lucien khẽ cau mày." - như 418:32 |
| 426:1 "Tự Nhiên?" | + `NPC*~` | có thể cả phòng hỏi lại (4: "thắc mắc chung của tất cả mọi người") |
| 426:36, 436:77-78 | LEVSKI; ANNONIS | cả hai bên cùng đúng: chủ ngữ của "quay sang/nhìn ... nói", không phải người nghe |
| hdst 090 | không đổi | |

## Vòng 10 (20-09 02:0x): TMA 399, 400, 415, 420 (lô 9, vừa thu) - B gán, A soát

Chọn trong lô 9 để chấm đầu ra THẬT của `qwen3:8b` trên nhiều chương hơn. A đọc lại mọi câu có người nói với nguồn: không
đổi dòng nào. Điểm đáng ghi: 400 - "Andris" bị một thứ khác nhập (xưng "ta", mặt biến dạng) nhưng không chương nào đến 407
nêu danh tính ấy -> ANDRIS đủ (quy tắc 13); 415:39 đuôi câu Fernando bị ngoặc lồng cắt, khoá N -> NARRATOR (quy tắc 10);
399:22, 54, 61 và 400:73, 415:88 là lời dẫn nêu người NGHE - không cho điểm người nghe.
