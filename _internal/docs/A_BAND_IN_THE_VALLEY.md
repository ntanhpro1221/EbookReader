# Một dải nhịp nằm đúng chỗ trũng, và một công cụ nói ngược

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
