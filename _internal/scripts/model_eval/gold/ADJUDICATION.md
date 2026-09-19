# Sổ phân xử đáp án chuẩn

Mỗi tranh chấp giữa hai người gán nhãn (A = Claude, B = agent review) và kết luận. Quy tắc: `docs/GOLD_GUIDE.md`.

## Vòng 1 - làm mù (20-09 01:0x): B gán độc lập 378 (cuốn 2) và 248 (cuốn 1)

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

## Vòng 2 - soát đối kháng (20-09 01:3x): B đọc đáp án của A cho 351, 363, 381 và tìm lỗi

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
