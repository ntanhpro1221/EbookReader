# Retry của pha phân tích: 20% số lượt gọi, và 72% trong đó là làm lại thứ đã đúng

Pha phân tích là chi phí lớn nhất của một run: 948 segment mất ~2,5 giờ ở **6,1 segment/phút**.
Đo trên **1017 lượt gọi LLM** của mọi run:

| lần | số lượt | tỉ lệ |
|---|---|---|
| 1 | 814 | 80,0% |
| 2 | 150 | 14,7% |
| 3 | 53 | 5,2% |

**20% tổng công là làm lại.**

## Cơ chế retry KHÔNG hỏng — đã kiểm trước khi định sửa

Giả thuyết đầu tiên là "hỏi lại y hệt ở temperature 0 thì kết quả buộc phải giống hệt, nên
retry vô nghĩa". **Sai**, và may là tôi đọc code trước khi sửa:

- `retry_temperatures = [0.1, 0.2, 0.3]` — nhiệt độ **tăng dần theo lần**
- seed đổi theo lần (`attempt` nằm trong hàm dẫn xuất seed)
- `validation_feedback` — **phản đối của host được đưa vào prompt lần sau**

Nên retry là một cuộc thương lượng thật, không phải hỏi lại câu cũ.

## Lãng phí thật nằm ở chỗ khác: cả lô bị làm lại vì một segment

Log ghi rõ: *"rejected 1/5 segment"* → *"Đang phân tích batch 1/16: **5 segment**, lần 2/3"*.

Đo trên **394 lần từ chối** có ghi tỉ lệ:

| tỉ lệ từ chối | số lần |
|---|---|
| **1/5** | **218** |
| 1/4 | 55 |
| 2/5 | 54 |
| 3/5 | 19 |
| 1/3 | 19 |

- tổng segment **bị từ chối**: 501
- tổng segment **phải sinh lại**: 1811
- ⇒ **72% công việc trong mỗi lần retry là sinh lại thứ đã được chấp nhận**

Nhân với 20% ⇒ khoảng **14% toàn bộ thời gian phân tích**.

## Ai gây ra phần lớn số retry

`HOST_SOURCE_KIND_MISMATCH fields=kind` chiếm **một nửa** số retry phân tích — nhưng chỉ đến
từ **16 segment khác nhau**, lặp 178 lần. Vài ca điển hình:

| segment | kind | hint | speaker |
|---|---|---|---|
| `'Tỉnh dậy, phải tỉnh dậy!'` | thought | thought | NARRATOR |
| `"Thiêu chết ả phù thủy..."` | dialogue | dialogue | NPC_LOCAL::…::người dân |

Đáng chú ý: `kind` **khớp** `kind_hint`. Host và LLM giằng co đủ ba vòng rồi mới thôi, tức
phản hồi không thuyết phục được model đổi ý ở đúng lớp segment này.

Cũng có retry vì `DIRECTOR_FIELD_MISMATCH fields=emotion,intensity` — bất đồng ở đúng hai
trường đã được xác lập là **không nghe ra được và không được phép chặn**
(`INAUDIBLE_DELIVERY_FIELDS`, `AFFECT_CUE_DISAGREEMENT_BLOCKS = False`). Đây là họ lỗi
"quyết định trên danh sách đầy đủ thay vì tập con chặn được" xuất hiện thêm một lớp nữa.

## Hai việc nên làm, theo thứ tự giá trị

1. **Chỉ sinh lại segment bị từ chối, không sinh lại cả lô.** Lợi ích đo được: ~14% thời
   gian phân tích. Rủi ro: hợp đồng phân tích băm theo `group_fingerprint`, nên đổi thành
   phần lô giữa các lần retry là chạm vào đúng thứ codebase này canh gác chặt nhất. Ngữ cảnh
   câu trước/sau đã được truyền riêng qua `original_context` nên không mất khi tách lô.
2. **Không retry khi bất đồng chỉ nằm ở trường không nghe được.** Nhỏ hơn nhưng sạch, và
   cùng gốc với bốn lỗi đã sửa trong `_validate_analysis_rejection_evidence`.

Chưa làm cái nào vì cả hai đều sửa `analysis.py`, mà lúc đo thì một run đang chạy — sửa file
đó giữa chừng chính là thứ đã buộc phải bỏ cả một project ở alpha.17.
