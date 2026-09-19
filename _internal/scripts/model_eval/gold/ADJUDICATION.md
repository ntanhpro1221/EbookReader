# Sổ phân xử đáp án chuẩn

Mỗi tranh chấp giữa hai người gán nhãn (A = Claude, B = agent review) và kết luận. Quy tắc: `docs/GOLD_GUIDE.md`.

## Vòng 1 - làm mù (20-09 01:0x): B gán độc lập 378 (cuốn 2) và 248 (cuốn 1)

Độ khớp trước phân xử, trên 94 câu có người nói: người nói ưu tiên trùng 97,9%, tập đủ-điểm giao nhau 100%; loại đoạn
100% (248/248); giới tính 100% (81/81); cảm xúc ưu tiên trùng 89,1%, tập giao nhau 100%.

| câu | A | B | kết luận | lý do |
|---|---|---|---|---|
| 378:1, 48, 87, 91, 93, 95 | chỉ tên | tên + `NPC*~` | theo B | lúc nói, người ấy chỉ được gọi "đại trưởng lão"/ẩn danh; tên ở ngay đoạn kề - quy tắc 5 |
| 378:4, 33, 116, 117 | `NPC*,UNKNOWN` + ... | bỏ `UNKNOWN` | giữ A | câu cả đám: `UNKNOWN` đủ điểm - quy tắc 6 |
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
