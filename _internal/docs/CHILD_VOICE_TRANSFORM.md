# Giọng trẻ em: phép biến đổi mất gần 1,0 MOS

## Phát hiện

Người nghe đã báo **rè** ở gần như *mọi* giọng trẻ em — Ngọc Linh, Thái Sơn, Thanh Bình,
Đoan Trang, Thục Đoan — trong khi **không giọng người lớn nào** bị. Suốt một thời gian dài
điều đó bị hiểu nhầm là khuyết tật của từng preset hoặc xổ số lúc sinh. Đo đạc cho thấy
không phải: **chính phép biến đổi đang phá chất lượng**.

Đo bằng UTMOSv2, cùng một waveform, tách từng bước:

| giọng | fm | st | thô | chỉ formant | chỉ pitch | cả hai | tổng mất |
|---|---|---|---|---|---|---|---|
| Phạm Tuyên | 1,20 | +15 | 2,81 | 2,26 | 1,95 | 1,69 | **−1,12** |
| Đoan Trang | 1,15 | +2 | 2,79 | 2,34 | 1,96 | 2,10 | **−0,69** |
| Thanh Bình | 1,20 | +7 | 2,95 | 2,37 | 2,05 | 1,96 | **−0,99** |
| Thái Sơn | 1,20 | +11 | 2,85 | 2,37 | 1,86 | 1,61 | **−1,24** |

Hai điều quan trọng:

1. **Bước dịch cao độ đắt hơn bước dịch formant** — khoảng −0,85 so với −0,50 MOS.
2. Giọng người nghe khen nhất (Đoan Trang) đúng là giọng **dịch ít nhất** (+2 nửa cung) và
   **mất ít nhất**. Độ dịch càng lớn, thiệt hại càng lớn.

## Nguyên nhân cấu trúc: đang tái tổng hợp HAI lần

Đường hiện tại chạy hai lần resynthesis riêng biệt trên cùng một tín hiệu:

1. `apply_voice_variant()` — Praat, đổi formant
2. `shape_segment()` — Praat PSOLA, đổi cao độ (register + tuổi)

Mỗi lần đều trả giá. Praat có lệnh **"Change gender"** làm cả hai **trong một lần**.

## So sánh ba cách (UTMOSv2, chênh so với thô)

| giọng | A: 2 lần (hiện tại) | B: Change gender 1 lần | C: Praat + WORLD |
|---|---|---|---|
| Phạm Tuyên | −1,03 | −1,24 | −1,49 |
| Đoan Trang | −0,82 | **−0,44** | −1,06 |
| Thanh Bình | −1,00 | **−0,87** | −0,93 |
| Thái Sơn | −1,33 | −1,08 | **−0,89** |

B thắng 3/4, kể cả trên Thanh Bình là giọng đang có lỗi nặng nhất; thua ở Phạm Tuyên là ca
dịch nhiều nhất (+15).

## ĐÃ CHỐT: giữ cách hiện tại (A, hai lần)

Người nghe đã phán trên ba cách: **A tốt nhất**, nhưng *"nó chả giải quyết được vấn đề"*.
Nghĩa là gộp hai lần tái tổng hợp thành một **không** phải cải thiện — B và C đều nghe tệ
hơn A dù UTMOSv2 chấm B cao hơn ở 3/4 giọng. Đây là **lần thứ hai** UTMOSv2 đi ngược tai
người trong cùng một vấn đề; xem `ONSET_CLICK.md`.

Không đổi đường xử lý. Thanh Bình và Thái Sơn được đưa xuống **đồng hạng đáy** bảng ưu
tiên thay vì tiếp tục sửa: khuyết tật còn đó, nhưng việc chọn giọng thôi không với tới
chúng nữa. Bé trai giờ do Phạm Tuyên dẫn.

Bảng đo MOS ở trên vẫn đúng và vẫn có giá trị — nó giải thích vì sao mọi giọng trẻ em đều
rè — nhưng **không được dùng nó để tự quyết** thay cho tai người.

## Hướng chưa thử

- **Lấy mẫu lại thuần tuý** (resampling) dịch formant và F0 cùng lúc, đúng như một cơ thể
  nhỏ hơn, và **không có nhiễu thuật toán nào** vì chỉ là nội suy. Vướng: nó đổi thời lượng
  (+7 nửa cung ⇒ ngắn đi 33%), mà kéo dài lại thì phải time-stretch — chính thứ đã bị loại
  vì không tất định. Chỉ khả thi nếu model đọc chậm lại được theo tỉ lệ tương ứng, mà `pace`
  của VieNeu đã được chứng minh là **không có tác dụng thật**.
- **Giảm độ dịch** và bù bằng cách chọn preset gần đích hơn. Dữ liệu ủng hộ: mất ít nhất ở
  giọng dịch ít nhất.
