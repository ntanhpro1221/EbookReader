# Quy tắc gán nhãn đáp án chuẩn (gold) cho khâu phân tích

Chủ sách, 20-09: *"đáp án rất quan trọng để chấm điểm và chọn model... cả 2 phải thật khắt khe"*. File này là quy
ước CHUNG cho mọi người gán nhãn (Claude và agent review). Đáp án nằm ở `scripts/model_eval/gold/<truyện>/<file>.txt`;
tranh chấp và kết luận ghi ở `scripts/model_eval/gold/ADJUDICATION.md`. Quy ước này bám theo luật của chính dự án
(SYSTEM_PROMPT trong `ebook_reader/analysis.py`) - đáp án chấm model theo đúng cái dự án đòi, không theo sở thích riêng.

## Cú pháp một dòng

    seq kind speaker emotion intensity pace volume gender

- `kind`: N (lời kể), D (thoại), T (nội tâm); tập như `T,N` khi chấp nhận cả hai, cái đầu là ưu tiên. `H` = tiêu đề
  chương (không chấm). Dòng chỉ `seq N` = NARRATOR neutral 0-1 normal normal u.
- `speaker`: các lựa chọn cách nhau dấu phẩy, đều đủ điểm; hậu tố `~` = nửa điểm (chấp nhận nhưng kém hơn);
  `NPC*` = bất kỳ NPC_LOCAL nào. Tên VIẾT HOA, tên có dấu cách được (`THẦN HƠI NƯỚC`).
- `emotion`, `pace`, `volume`: TẬP chấp nhận được, cái đầu là ưu tiên (dùng làm đáp án khi dạy model).
- `intensity`: khoảng `a-b`.
- `gender`: m / f cho người nói có giới rõ; u cho lời kể hoặc không rõ.

## Người nói - phần chấm khắt khe nhất

1. **Lời kể luôn là NARRATOR**, kể cả truyện ngôi thứ nhất: "tôi ..." trong lời kể vẫn là người kể; chỉ câu "tôi" NÓI
   thành tiếng mới là nhân vật ấy (vd SAMAEL).
2. **Thoại**: người nói là người phát ra câu, không phải người được gọi tên trong câu ("Harold, ..." thường là người
   nghe). Tìm lời dẫn trước/sau câu ("X nói", "X cười khẩy", "Nghe X nói thế", "X thầm nghĩ"), rồi mạch đối đáp.
3. **Nội tâm (T)**: người nói là CHÍNH người đang nghĩ (quyết định chủ sách 20-09: nội tâm ai thì giọng người ấy đọc).
   Chỉ khi thật không biết ai nghĩ mới là NARRATOR.
4. **Lời kể có câu tự nhủ trực tiếp** ("Ả khốn này!", "Không ổn!", "...V-Vãi.", "Chẳng lẽ...?" ở ngôi của nhân vật):
   chấp nhận `N,T` với `NARRATOR,<người nghĩ>` - đều đủ điểm (dự án cho phép đổi narration thành thought khi là tiếng
   nói nội tâm trực tiếp; không bắt buộc). Truyện ngôi thứ nhất (kể ở hiện tại hay quá khứ): phản ứng TỨC THỜI của
   người kể trong cảnh (câu hỏi tu từ, "Thôi chết.", "Hmph", nói thầm với người trước mặt) là tiếng lòng -> `N,T`; câu
   giải thích bối cảnh hay nói với người đọc ("mọi người hiểu mà đúng không?") vẫn chỉ `N` (vòng 4-5). Truyện ngôi ba:
   đoạn phần lớn là lời kể VỀ nhân vật ("Nghe vậy, Sophia... Cô ngã xuống...") chỉ có một câu tự nhủ ở đầu/cuối -> `N,T`
   nhưng người nghĩ chỉ `~` (đọc cả đoạn bằng giọng nhân vật là sai giọng cho phần kể về chính họ; vòng 5).
5. **Nhân vật không tên nhưng phân biệt được** (người hầu, lính gác, "một người lùn", giọng máy): `NPC*`.
   **`UNKNOWN` đủ điểm CHỈ khi không có manh mối gì** (đúng lời prompt của dự án: "Chỉ dùng UNKNOWN khi hoàn toàn
   không có dấu hiệu phân biệt người nói"); có manh mối thì `UNKNOWN~` (vòng 2, 20-09). Người CHƯA được xác định lúc nói mà cùng chương sau đó gọi tên (dù là
   nhân vật cũ hay mới - "một pháp sư có ria mép" rồi mới "Lauren", "một giọng nói rất to" qua điện thoại rồi mới "Diệp
   Cẩn Huyên"): tên đủ điểm, `NPC*~` nửa điểm (lượt hoà giải NPC nối được về tên trong cùng chương). Nhãn NPC chỉ sống
   trong MỘT chương, nên nhân vật xuất hiện ở nhiều chương (vd "Thần Hơi Nước", thật ra là Lucien, nói lại ở chương 460)
   dùng `NPC*` chỉ được nửa điểm - không thì mỗi chương một giọng (vòng 3).
6. **Câu cả đám cùng nói/niệm**: `NPC*` đủ điểm (`UNKNOWN~`). Người được NÊU TÊN trong lời dẫn của câu ấy ("Harold và
   những người lùn khác cầu nguyện", "dẫn dắt Myrna... đáp lại") đủ điểm; người có mặt trong cảnh nhưng không được nêu
   trong lời dẫn thì nửa điểm (vòng 1-2).
7. **Văn bản viết** (thư, ghi chú, nhận xét đang viết, câu trích luận án, tựa sách, lời bài hát, khế ước): `NARRATOR`
   đủ điểm. Hai trường hợp (vòng 3):
   - văn bản chỉ được NHÌN THẤY / trích ra: NARRATOR và TÁC GIẢ đủ điểm (khế ước của "thần" -> giọng thần), người đang
     đọc/nhìn thấy nửa điểm;
   - văn bản được một nhân vật ĐỌC TO bằng giọng của mình ("khàn khàn giọng đọc lên", giọng máy đọc tiêu đề kèm dấu
     "?", đang viết nhận xét): người đọc và NARRATOR đủ điểm, tác giả nửa điểm.
   Người ký/nhận văn bản không được điểm. Người viết không tên: `NPC*~`. Tác giả chỉ được gọi tên ở chương khác hoặc qua
   một câu trích thoáng qua ("ghi chép của Vua Mặt Trời Thanos"): tên đủ điểm, `NPC*~` (vòng 5). Thư gửi CHO X thì X không phải người nói.
8. **Ngoặc kép nhấn mạnh / tiếng tượng thanh trong ngoặc** ("mỉm cười", "quan sát", "Rầm!", "Bùm!"): parser khoá là
   thoại nhưng thực chất là chữ của người kể → `NARRATOR` đủ điểm. Từ/cụm nằm GIỮA câu kể mà gốc là lời của ai
   ("quan sát" của Fernando, câu đáp của Lucien) thì người ấy chỉ nửa điểm (đổi giọng giữa câu kể là sai). Từ trong
   ngoặc là MÔ TẢ chứ không phải lời ("ông liền 'mỉm cười' nói") thì không nhân vật nào được điểm. Tiếng động:
   `UNKNOWN~`. Tiếng thét/kêu của người vẫn là của người ấy (NARRATOR~).
9. **Quy tắc 4 thắng quy tắc 10** khi parser cắt vụn (vd đuôi của một câu nghĩ bị khoá N: "này của mình!'"): cho `N,T`.
   Chỉ khi host thật sự khoá ngữ nghĩa (gold_replay báo LỆCH LUẬT) mới giữ N.
   **Thứ tự loại**: loại THẬT đứng trước (`N,T` cho lời kể bị parser khoá thành thought), kể cả khi parser khoá loại kia.
   Câu NGHĨ bị khoá thoại (có lời dẫn "Trong đầu tôi chỉ nghĩ:" mà nằm trong “”): `T,D`, người nghĩ đủ điểm (vòng 5).
10. **Parser khoá sai loại** (nguồn hỏng dấu nháy làm cả đoạn lời kể thành T; thoại nằm giữa dòng lời kể nên bị khoá N):
   giữ loại bị khoá là đủ điểm (model không được phép đổi), người nói = người đọc hợp lý nhất theo loại bị khoá (khoá N
   thì NARRATOR; khoá T mà thực chất là lời kể thì NARRATOR, người nghĩ `~`). Ghi chú ở đầu file.
11. **Tên gọi khác của cùng một người** (Cẩn Huyên / Diệp Cẩn Huyên, Ray / Ray Warner, Douglas / Derrick Douglas): liệt kê
   các dạng, đều đủ điểm. KHÔNG tính dạng có tiền tố vai vế/xưng hô ("CHÚ LƯU ĐẠT", "NGÀI X", "GIÁO SƯ GLAST") hay
   danh hiệu trơn khi đã biết tên ("THÁNH NỮ" cho Magali) - prompt dự án cấm chúng, và nhãn danh hiệu thành giọng thứ
   hai của cùng người (vòng 4). Tên viết nhầm trong chính bản dịch ("Eris" cho Eria) được nửa điểm ở câu nó dẫn.
12. **Không** cho điểm tên nổi tiếng chỉ vì họ có trong danh sách đã biết - đây là lỗi model hay mắc nhất.
13. **Nhập xác, cải trang, danh tính ẩn**: tên mà CHƯƠNG NÀY gọi người nói đủ điểm; danh tính thật chỉ lộ ở chương sau
   nửa điểm (Beyer / Rudolf II ở 407). Nếu chính chương đã lộ danh tính thật trước câu nói thì danh tính thật đủ điểm.
   Giọng của người bị nhập xác (xác hay hồn) là câu hỏi mở cho chủ sách (vòng 5).

## Cảm xúc, cường độ, nhịp, âm lượng

- Tập chấp nhận phải chứa mọi cách đọc HỢP LÝ, và loại những cách đọc SAI RÕ (vd happy cho câu đe doạ). Không được
  hẹp đến mức chỉ còn sở thích riêng, cũng không được rộng đến mức chấm gì cũng đúng.
- Lời kể trung tính: neutral 0-1 normal normal. Lời kể trong cảnh căng: thêm cảm xúc của cảnh vào tập (afraid, sad...)
  nhưng luôn giữ neutral.
- intensity 3 chỉ cho cao trào rõ (gào thét, khóc nấc, quát tháo tột độ). Lẩm bẩm/thì thầm: volume soft, thường có
  `whispering` trong tập. Quát: loud.
- Không có nhãn "đau": tiếng kêu đau ("Á hự!") chấp nhận sad/angry/afraid/surprised.
- Luật của host: đoạn có từ gợi cảm xúc mạnh thì host CẤM neutral (`allowed_emotions`). Nếu đáp án chỉ có neutral cho
  đoạn như vậy, gold_replay sẽ báo "LỆCH LUẬT" - khi đó xét lại: hoặc thêm cảm xúc hợp lý vào tập, hoặc ghi vào sổ
  phân xử là luật host sai.

## Giới tính

Ghi cho mọi câu có người nói rõ giới. Dòng mà lựa chọn ĐẦU là một nhân vật (kể cả văn bản viết `CHLOE,NARRATOR`) ghi
giới của nhân vật ấy; lựa chọn đầu là NARRATOR thì `u`. Nhân vật mới: suy từ đại từ (anh/cô/ông/bà/gã/ả/y/hắn), xưng hô, tên. Sổ nhân vật
của sản xuất có thể SAI (vd CHLOE ghi female nhưng chương 344 gọi "anh", "ngài Chloe") - tin văn bản, không tin sổ.

## Quy trình

1. Người gán nhãn A đọc TRỌN chương trước khi gán; gán mọi đoạn.
2. Người B làm mù (không xem A) hoặc soát đối kháng (xem A, tìm lỗi) - mỗi chương ít nhất một trong hai.
3. So bằng script; mọi câu lệch người nói/loại đoạn phải tranh luận với bằng chứng văn bản; cảm xúc chỉ tranh luận
   khi tập của một bên loại mất cách đọc rõ ràng đúng.
4. Kết luận ghi vào `ADJUDICATION.md` và sửa file gold. Câu không phân xử được: nới tập chấp nhận, hoặc hỏi chủ sách.
5. Sau khi sửa, chạy `gold_replay.py` (không được có LỆCH LUẬT chưa giải thích) và test `test_model_eval_scoring.py`.
