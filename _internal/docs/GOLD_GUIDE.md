# Quy tắc gán nhãn đáp án chuẩn (gold) cho khâu phân tích

Chủ sách, 20-09: *"đáp án rất quan trọng để chấm điểm và chọn model... cả 2 phải thật khắt khe"*. File này là quy
ước CHUNG cho mọi người gán nhãn (Claude và agent review). Đáp án nằm ở `scripts/model_eval/gold/<truyện>/<file>.txt`;
tranh chấp và kết luận ghi ở `scripts/model_eval/gold/ADJUDICATION.md`. Quy ước này bám theo luật của chính dự án
(SYSTEM_PROMPT trong `ebook_reader/analysis.py`) - đáp án chấm model theo đúng cái dự án đòi, không theo sở thích riêng.

## Cú pháp một dòng

    seq kind speaker emotion intensity pace volume gender

- `kind`: N (lời kể), D (thoại), T (nội tâm); tập như `T,N` khi chấp nhận cả hai, cái đầu là ưu tiên. `H` = tiêu đề
  chương (không chấm) - chỉ đoạn 0; nguồn lặp lại tiêu đề ở đoạn 1 thì đoạn 1 là `1 N` như lời kể thường (vòng 6).
  Dòng chỉ `seq N` = NARRATOR neutral 0-1 normal normal u.
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
   trong lời dẫn thì nửa điểm (vòng 1-2). Lời dẫn nêu HAI người cho MỘT câu mà chỉ một người nói ("Công tước James và
   pháp sư Barek... nhỏ giọng thở dài", "Tamaki và Shirawakamaru vội vàng đỡ"): cả hai đủ điểm, người có bằng chứng hơn
   (lối xưng hô, mạch đối đáp) đứng trước (vòng 6). Nhưng HAI câu liên tiếp sau lời kể nêu hai người ("Hayase và Narumi
   gọi Fuyutsuki." rồi hai câu chúc) là mỗi câu một người: người có bằng chứng đủ điểm, cách đọc đảo nửa điểm; câu kể tả
   hai người ở đoạn văn khác ("Narumi và Hayase đứng vẫy tay") không phải lời dẫn (vòng 7).
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
   thì NARRATOR; khoá T mà thực chất là lời kể thì NARRATOR, người nghĩ `~`). Ghi chú ở đầu file. Lời lẩm bẩm không
   ngoặc nằm trong đoạn kể bị khoá N ("Mọi kế hoạch tan tành. Iruka lẩm bẩm") cũng chỉ NARRATOR (Yamiyo 155:43).
11. **Tên gọi khác của cùng một người** (Cẩn Huyên / Diệp Cẩn Huyên, Ray / Ray Warner, Douglas / Derrick Douglas): liệt kê
   các dạng, đều đủ điểm. KHÔNG tính dạng có tiền tố vai vế/xưng hô ("CHÚ LƯU ĐẠT", "NGÀI X", "GIÁO SƯ GLAST") hay
   danh hiệu trơn khi đã biết tên ("THÁNH NỮ" cho Magali) - prompt dự án cấm chúng, và nhãn danh hiệu thành giọng thứ
   hai của cùng người (vòng 4). Tên viết nhầm trong chính bản dịch ("Eris" cho Eria) được nửa điểm ở câu nó dẫn. Nhân vật
   không có tên riêng mà cả truyện gọi bằng họ + kính xưng ("Trịnh lão") thì dạng ấy là tên, đủ điểm (vòng 7).
12. **Không** cho điểm tên nổi tiếng chỉ vì họ có trong danh sách đã biết - đây là lỗi model hay mắc nhất.
13. **Nhập xác, cải trang, danh tính ẩn**: tên mà CHƯƠNG NÀY gọi người nói đủ điểm; danh tính thật chỉ lộ ở chương sau
   nửa điểm (Beyer / Rudolf II ở 407). Nếu chính chương đã lộ danh tính thật trước câu nói thì danh tính thật đủ điểm.
   Giọng của người bị nhập xác (xác hay hồn) là câu hỏi mở cho chủ sách (vòng 5). Cải trang mà lời kể vẫn gọi tên thật
   trước câu nói (Lucien đội lốt "Beaulac"): tên thật đủ điểm, tên giả nửa điểm trên câu NÓI, không điểm trên câu nghĩ.
   Cả khi chính lời dẫn dùng tên giả ("Aska ngạo nghễ nói" sau khi Aska thật đã bất tỉnh): danh tính đã lộ trước câu thì
   tên thật đủ, tên giả nửa điểm - giọng người thật nói, không phải giọng cái lốt (vòng 8).

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

## Khi thí sinh trả lời ĐÚNG HƠN đáp án

Chuyện này xảy ra được, và đã xảy ra bốn lần với người soát (`ADJUDICATION.md`: 347:20, nise ×8, hdst 151, TMA
407 - A đọc sót chương trước, B đúng). Đáp án là công trình của người đọc chương một lượt; một thí sinh đọc lại
chỗ ấy kỹ hơn thì nó đúng hơn. **Đáp án sai thì SỬA ĐÁP ÁN** - giấu đi để giữ thể diện thước đo là tự làm hỏng
thước đo. Nhưng sửa theo bài làm là đường ngắn nhất tới một đáp án chỉ còn đo được chính thí sinh đã dạy nó, nên
đi đúng sáu bước sau:

1. **Mọi chỗ lệch đều phải PHÂN XỬ, không chỉ trừ điểm.** `score_models.py --dispute-out <file>.tsv` in phiếu:
   mỗi chỗ lệch một dòng, có nguyên văn đoạn, có cột `phán xử` và `bằng chứng` để điền.
2. **Phân xử làm MÙ.** Phiếu giấu tên model thành `TS1..TSn` (băm tên, thứ tự không liên quan điểm); khoá ở
   `<file>.tsv.key`, **chỉ mở SAU khi điền xong cột `phán xử`**. Không phân xử giữa lượt so hai model với nhau:
   nhận cách đọc của một bên lúc ấy là lặng lẽ cho bên ấy điểm.
3. **Ba ô, không hai:** `TS_SAI` (văn bản đã quyết định, thí sinh sai - cứ để sai), `ĐÁP_ÁN_SAI` (sửa gold),
   `NHẬP_NHẰNG` (văn bản thật sự cho hai cách đọc - thêm vào tập chấp nhận, thường `~`). Ô thứ ba là ô dễ bị
   lạm dụng nhất: một đáp án chấp nhận mọi thứ cho mọi thí sinh 100 điểm và không đo gì cả.
4. **Bằng chứng phải là câu trong truyện**, dán vào cột `bằng chứng` - chương ấy hoặc chương trước. "Model tự tin",
   "ba model cùng nói thế", "nghe hợp lý hơn" KHÔNG phải bằng chứng; nhiều thí sinh cùng sai một kiểu là chuyện
   thường (cả nhà cùng gán người được gọi tên làm người nói). Phép thử: lời giải thích phải thuyết phục được người
   chưa hề xem bài làm nào.
5. **Sửa đáp án là HUỶ mọi điểm cũ của chương ấy.** Chấm lại tất cả thí sinh đã đo trên chương đó và ghi cả số cũ
   lẫn số mới vào `docs/LLM_EVAL.md` - nếu không, điểm tăng không còn phân biệt được "model khá hơn" với "đáp án
   dễ đi".
6. **Ghi vào `ADJUDICATION.md`** một dòng: chương:seq, đáp án cũ, đáp án mới, bằng chứng, và nguồn phát hiện (thí
   sinh nào, sau khi đã mở khoá). Đếm được số lần đáp án phải sửa chính là cách biết đáp án đang khắt khe tới đâu.
