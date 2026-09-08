# Kế hoạch chạy cả cuốn: 478 chương, 16 lô

Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động toàn bộ cho
ra sản phẩm"*, và về phân lô: *"phân lô thế nào cũng được, đừng để phân tích bị sai do phân lô
có vấn đề là được"*.

Câu thứ hai đã được đo và trả lời: **phân lô không làm hỏng phân tích** — xem
[VERSIONS.md](VERSIONS.md), mục *"Phân lô có làm hỏng phân tích không?"*. Tài liệu này là câu
trả lời cho câu thứ nhất: chạy hết 478 chương thì tốn bao nhiêu và đi theo đường nào.

## Toàn cảnh

```
478 chương · 1.125.675 từ · 58.258 segment
16 lô, mỗi lô ~8 giờ máy (~3.700 segment)
tổng ~128 giờ máy  ≈  5,3 ngày chạy liên tục
```

Sinh bằng `scripts/plan_batches.py "D:/Novels/Tools/Text" --hours 8`. Cân theo **giờ máy**,
không theo chương và cũng không theo từ: máy tính tiền theo **segment**, và cùng một số từ thì
số segment chênh tới 40% giữa chương nhiều đối thoại và chương tự sự. Chia theo 73.000 từ cho
ra những lô lệch nhau tới 2,7 giờ; chia theo giờ máy cho ra 15 lô trong khoảng 7,9–8,2 giờ và
một lô cuối 5,9 giờ.

| lô | chương | số chương | segment | giờ máy |
|---|---|---|---|---|
| 1 | 000..029 | 30 | 3.727 | 8,1 |
| 2 | 030..059 | 30 | 3.762 | 8,1 |
| 3 | 060..091 | 32 | 3.675 | 7,9 |
| 4 | 092..118 | 27 | 3.795 | 8,2 |
| 5 | 119..144 | 26 | 3.720 | 8,0 |
| 6 | 145..166 | 22 | 3.636 | 7,9 |
| 7 | 167..192 | 26 | 3.692 | 8,0 |
| 8 | 193..221 | 29 | 3.713 | 8,0 |
| 9 | 222..252 | 31 | 3.735 | 8,1 |
| 10 | 253..278 | 26 | 3.693 | 8,0 |
| 11 | 279..305 | 27 | 3.678 | 7,9 |
| 12 | 306..342 | 37 | 3.701 | 8,0 |
| 13 | 343..375 | 33 | 3.670 | 7,9 |
| 14 | 376..406 | 31 | 3.634 | 7,9 |
| 15 | 407..447 | 41 | 3.706 | 8,0 |
| 16 | 448..477 | 30 | 2.721 | 5,9 |

## Chương 000–027 đã có audio rồi — vẫn phải làm lại

Ba lô đầu tiên của lịch sử (`000..009`, `010..018`, `019..027`) đã chạy xong, nhưng bằng **mã
cũ**, và mã ấy có bốn lỗi đã sửa từ đó:

| lỗi | ảnh hưởng lên audio đã có |
|---|---|
| nhịp đọc đếm chữ số thay vì chữ đọc | tiêu đề chương bị chấm sai, có chương trượt oan |
| ngoặc kép không đóng làm dừng cả sách | 8 chương nguồn không segment được |
| bản thu chạm trần khung không được thu lại | đoạn lảm nhảm lọt vào sách |
| `k`/`c` trong kiểm phát âm tên | tên đúng bị chấm sai |

Audio cũ **không sai ở chỗ nghe được** trong đa số trường hợp, nhưng nó được duyệt bởi những
phép kiểm đo nhầm thứ — nên "đã qua" ở bản cũ không nói lên điều gì về bản hiện tại. Lô 1 của
kế hoạch này (`000..029`) chạy đè lên chúng, và đó là lý do bảng trên bắt đầu từ 000 chứ không
từ 028.

## Đường đi mỗi lô, không được đổi thứ tự

Nguyên văn ở [VERSIONS.md](VERSIONS.md); tóm tắt để khỏi phải mở hai file:

```
create  →  port_pronunciations  →  port_casting  →  seed_listener_acceptances  →  run
```

**Gieo từ lô liền trước**, tạo thành một dây. Đứt một mắt là mất một thứ cụ thể, và cái mất
lớn nhất là `port_pronunciations`: cách đọc một cái tên đổi thì audio đổi, mà phán quyết của
người nghe khoá theo checksum audio — nên mất cách đọc là mất luôn mọi lần nghe đã bỏ ra.

Kiểm rẻ nhất ngay sau `create`: tên thư mục project phải chứa hash của **dải ấy**. Hash phụ
thuộc dải chứ không chỉ nguồn, nên chỉ so được giữa hai lượt cùng dải.

## Còn cái gì có thể dừng cả dây

Sau [cơ chế xuất bản khi không có ai để hỏi](SHIPPING_WITHOUT_A_LISTENER.md), không còn chỗ nào
trong đường ống **dừng lại đợi người**. Chương hỏng thì hỏng riêng chương ấy và lô vẫn đi tiếp.

Hai thứ còn lại có thể làm hỏng một chương, cả hai đã ghi:

1. `"Tiếp theo."` — bản đương nhiệm chạm trần khung, ứng viên tốt hơn bị vứt vì luật giữ
   bản-đương-nhiệm. Đo được **2 ca trên 38.520 đoạn**, ngoại suy ra **khoảng bốn chương** trên
   cả cuốn. Xem [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md).
2. QA tầng chương (`_evaluate_chapter_quality`) — chỗ nối, im lặng, độ to. Máy không được phép
   tự cho qua cổng này, vì nó đo trên chính file âm thanh chứ không đo qua ASR.

## Sau mỗi lô

```bash
scripts/compare_runs.py <lô trước> <lô này>       # chương nào hỏng, gỡ được nhờ đâu
scripts/machine_acceptances.py <lô này> --markdown # đoạn nào chưa ai nghe, ở giây thứ mấy
scripts/audit_audiobook.py <lô này>                # kiểm tổng thể
```

Cột đáng nhìn nhất ở `compare_runs.py` là chỗ nó **tách riêng** chương gỡ được nhờ bản thu khá
lên thật với chương gỡ được nhờ máy tự cho qua. Gộp hai loại lại là cách dễ nhất để tự khen
nhầm, và tôi viết nó ra vì đã suýt làm thế.
