# Một dải nhịp nằm đúng chỗ trũng — và lượt vá kế tiếp bác bỏ tôi

> **Đọc mục cuối trước.** Tên tài liệu này là kết luận đầu tiên của tôi, và nó **sai**. Lượt vá
> của bước 3 chạy xong 06:54 ngày 2026-09-12: đoạn ấy **qua ngay lần thử đầu**, 1,68 giây,
> 21,28 kt/s. Công cụ của dự án nói "trong tầm với" và nó đúng; tôi nói "không tới được" và tôi
> sai. Phần đo vẫn giữ nguyên giá trị, phần suy luận thì không — giữ cả hai ở đây vì cái sai này
> dạy được nhiều hơn cái đúng.

Chương 140 của lô 5 hỏng lúc 05:51 ngày 2026-09-12 vì **một** đoạn trong 196 đoạn — 195 đoạn kia
`verified`. Đoạn ấy chưa từng tới cổng ASR: nó chết ở cổng **nhịp**, trong vòng thử lại TTS.

    "Ngậm miệng lại và tập trung đi,"     SAMAEL, dialogue, pace=normal, 24 ký tự đọc được

Mười lần thử, và tốc độ đọc **lặp lại đúng bốn giá trị**:

    lần  1  24.79 kt/s        lần  6  29.70
    lần  2  29.70             lần  7  27.03
    lần  3  24.79             lần  8  29.70
    lần  4  27.03             lần  9  24.79
    lần  5  12.45             lần 10  29.70

Đổi sang thời lượng thì thấy ngay hình dạng của nó:

    12.45 kt/s  ->  1.9277 s
    24.79 kt/s  ->  0.9681 s
    27.03 kt/s  ->  0.8879 s
    29.70 kt/s  ->  0.8081 s

    dải [12,5 .. 24,5] kt/s  đòi thời lượng trong [0.9796 .. 1.9200] s

Bốn giá trị ấy nằm **hai bên** cái cửa sổ ấy, không có giá trị nào bên trong. Ba giá trị nhanh
cách nhau đúng **80 ms** (0,0798 và 0,0802), rồi nhảy một bước **0,96 s** tới giá trị chậm. Tức
phân bố thời lượng của giọng cho câu này là **hai cực**: hoặc buông rất nhanh (0,81–0,97 s), hoặc
đọc chậm hẳn (1,93 s). Dải nhịp rơi đúng vào chỗ trũng giữa hai cực, và hai lần thử gần nhất
trượt lần lượt **1,2%** (24,79 so với trần 24,5) và **0,4%** (12,45 so với sàn 12,5).

## Công cụ của dự án nói "trong tầm với", và nó nói ngược

`scripts/pace_retry_reachability.py` tồn tại đúng để phân biệt *xui* với *không thể*. Chạy nó:

    c00022_s0000036   24.79 29.70 24.79 27.03 12.45 29.70 27.03 29.70 24.79 29.70
                      normal  nhanh  p/lần 38.9%   4:86%  6:95%  8:98%  10:99%

Nó bảo mỗi lần thử có **38,9%** cơ hội, và mười lần thì **99%**. Thực tế: **0 trên 10**. Nếu
38,9% đúng thì trượt cả mười lần có xác suất 0,7% — không phải chuyện thường gặp.

Sai ở đâu: bộ ước lượng khớp một **phân bố liên tục, một đỉnh** vào các giá trị quan sát được,
nên một phần khối lượng xác suất của nó rơi vào trong dải. Nhưng dữ liệu là **bốn giá trị lặp
lại, hai cực**, và không giá trị nào trong dải. Đúng lỗi mà chính tài liệu của công cụ ấy cảnh
báo ở ca khác ("một dải tính trên văn xuôi định giá sai một thang bậc"), chỉ ở chiều khác: nó
định giá sai **hình dạng** của phân bố.

Sửa đề xuất (ghi ở `OPTIMISATION_QUEUE.md`): báo thêm **số giá trị PHÂN BIỆT** và khoảng trống
lớn nhất giữa chúng. "10 lần thử, 4 giá trị phân biệt, khoảng trống 0,96 s chứa cả dải" nói thật
hơn mọi con số phần trăm, và nó không cần một giả định nào về phân bố.

## Thứ chắc chắn chữa được ca này đã có trong dự án

`POSTPROCESS_PROFILE_TEMPO` = `ffmpeg_atempo_0_94_pcm_s16le_v1` — làm chậm 6%, không đổi cao độ.
Áp lên từng lần thử:

    24.79 kt/s  ->  23.30 kt/s   QUA
    27.03 kt/s  ->  25.41 kt/s   vẫn trượt
    29.70 kt/s  ->  27.92 kt/s   vẫn trượt
    12.45 kt/s  ->  11.70 kt/s   vẫn trượt (chậm thêm thì càng chậm)

Đúng một lần thử — lần gần trần nhất — được tempo cứu, và nó đã có mặt **bốn lần** trong mười
lượt. Vậy ca này không phải "giọng không đọc nổi", mà là **đường cứu có sẵn không với tới chỗ
cần**: ứng viên tempo chỉ nằm trong thang sửa của **ASR** (vòng cuối, `repair_round == max`), còn
đoạn này chết ở vòng thử lại **TTS** và không bao giờ đi tới đó.

## Vì sao không sửa ngay đêm nay

Cả hai bản sửa (bộ ước lượng, và đường tempo cho pace) đều là thay đổi thật ở tầng quyết định
xuất bản, và ranh giới lô 5 → 6 đang chờ chạy một mình với **ba** bản vá đã chứng minh. Thêm bản
vá thứ tư chưa chạy thật vào một đêm không ai ngồi cạnh là đổi một chương lấy nguy cơ cho hai
mươi sáu chương.

Bước 3 của ranh giới sẽ **vá lại chương 140**, và tài liệu này ghi trước dự đoán: nếu phân bố
thời lượng của câu ấy vẫn hai cực như mười lần vừa rồi thì lượt vá ấy **trượt tiếp**, tốn chừng
25 phút GPU. Sáng ra kiểm đúng chỗ này: `runtime/boundary_05.log` bước 3, và
`pace_retry_reachability.py` trên project `lo05v_140`. Nếu nó trượt, đây là ca thật để áp bản vá
tempo ở ranh giới 6 → 7 — và lúc ấy đã có một ca đo được thay vì một giả thuyết.

## Kết luận đầu tiên của tôi sai, và đây là vì sao

Bước 3 của ranh giới vá chương 140 thành project `lo05v_140_8c58fd5165`, xong lúc 06:54 — **26
phút** kể từ lúc khởi động. Chương `completed`. Đoạn từng hỏng:

    trước:  10 lần thử, 24.79 / 27.03 / 29.70 / 12.45 kt/s, không lần nào trong dải -> failed
    sau :   qua ngay lần thử ĐẦU, 1.68 s, 21.28 kt/s, 6.21 âm tiết/giây -> verified

Thứ đổi không phải hạt giống, mà là **phiếu diễn**: lượt vá **phân tích lại** chương, và đạo diễn
cho `intensity = 0` thay vì `1` (emotion `neutral` và pace `normal` giữ nguyên). Cùng một câu,
cùng một giọng, cường độ thấp hơn một bậc, và bản thu dài gấp **2,1 lần** bản nhanh nhất của lượt
trước.

Sai của tôi nằm ở một giả định tôi không nói ra: rằng "cùng văn bản, cùng giọng" thì phân bố thời
lượng là cố định, nên mười mẫu của một lượt nói được về mọi lượt. Không phải: **một lượt vá thay
cả phiếu diễn**, và phiếu diễn là một tham số của phân bố ấy. Mười mẫu của tôi mô tả đúng một
lượt, không mô tả câu ấy.

Và `pace_retry_reachability.py` — cái công cụ tôi vừa chê là "nói ngược" — nói **38,9% mỗi lần
thử**. Lượt sau đạt ngay lần đầu. Lời chê vẫn còn đúng một nửa (bộ ước lượng thật sự khớp một
phân bố liên tục vào dữ liệu rời rạc), nhưng **ca tôi dùng để chứng minh nó sai thì nó lại đúng**.
Một bộ ước lượng lạc quan mà đúng thì tốt hơn một lý thuyết bi quan mà sai.

## Cái gì còn lại sau khi trừ đi phần sai

- **Đo được và vẫn đúng:** trong MỘT lượt, mười lần thử cho đúng bốn giá trị lặp lại, ba giá trị
  nhanh cách nhau 80 ms. Phương sai trong một lượt nhỏ và rời rạc; đừng chờ nó tự bò vào dải.
- **Đường cứu thật của ca này không phải tempo, mà là phân tích lại.** Nó đã có sẵn trong bước 3
  của ranh giới, và nó chữa xong trong 26 phút mà không ai chạm vào.
- **Bản vá tempo: hạ xuống "theo dõi", không phải "có ca rồi".** Tôi chưa có ca nào chứng minh
  retry không tới được; ca duy nhất tôi tưởng là nó thì đã tự khỏi. Muốn áp tempo thì phải có một
  đoạn trượt nhịp **qua ít nhất hai lượt vá** (tức hai phiếu diễn khác nhau). Chưa có.
- **Bản sửa bộ ước lượng vẫn đáng làm**, nhưng vì lý do khác lý do tôi viết lúc đầu: nó nên nói
  **"phương sai trong một lượt"** khác **"cơ hội qua sau khi phân tích lại"**, vì hai con số ấy
  trả lời hai câu và chỉ con số thứ hai mới quyết định có nên vá lại chương hay không.

Bài học chung, đắt hơn cả ba gạch đầu dòng trên: **tôi đặt tên tài liệu theo kết luận trước khi
lượt chạy kế tiếp kịp nói.** `TWO_CHARACTERS_ONE_VOICE.md` từng làm đúng việc phải làm trong ca
tương tự — giữ lại kết luận sai kèm lý do — nên tài liệu này giữ nguyên cái tên sai ấy, có cảnh
báo ở đầu.

## Ca thứ hai, chương 175 (2026-09-13 01:5x): lượt vá đổi cả NGƯỜI NÓI

Lô 7, chương 175, câu "Nghiên cứu… nghiên cứu kiểu gì cơ?": 10 lần thử, 4 giá trị, 25,7–33,7 kt/s,
tất cả trên trần — cùng lớp với 140. Bước 3 vá lại: **qua ngay lần thử đầu**, 2,16 s, 19,5 kt/s,
với **cùng phiếu diễn** (normal/neutral/1). Lần này không phải đạo diễn đổi ý. Thứ đổi là người nói:

    lô 7     speaker='BẢN LINH'                       canonical=BẢN LINH (male)  giọng=thanh_binh_f100_p-04
    vá 175   speaker='JULIANA'                        canonical=JULIANA (female)  giọng=ngoc_linh_f100_p+00

Phân tích lại gán câu ấy cho một người khác, người ấy có giọng khác, và giọng khác đọc với nhịp
khác. Vậy phân bố thời lượng thuộc về **(văn bản, người nói → giọng, phiếu diễn)**, và một lượt vá
đổi được cả ba. Kết luận của mục trước đứng vững và mạnh hơn: "trong tầm với" là câu hỏi của một
lượt; hai lượt là hai phân bố. Tempo vẫn ở mức "theo dõi" — hai ca, hai lần lượt vá tự chữa.

Câu gán cho ai mới đúng thì tài liệu này không phán: cả hai lượt đều là LLM đọc cùng một đoạn.
