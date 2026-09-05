# Khi phản biện đạo diễn và bộ phân tích không đồng ý với nhau

## Quyết định của chủ nhân (05/09/2026)

Hỏi trực tiếp, chủ nhân chọn: **lấy cách đọc của model, gắn cảnh báo, để tai người nghe
quyết** — thay vì để cả quyển sách chết. Cùng hình dạng với lựa chọn trước đó về dải nhịp
("lùi về `normal` nhưng ghi cảnh báo").

Tài liệu này ghi lại **vì sao chưa làm được ngay**, và làm đúng thì phải làm thế nào. Đừng
lặp lại cuộc điều tra này từ đầu.

## Bậc thang hiện có

Khi một batch không qua được phản biện, code đã leo qua bốn bậc trước khi bỏ cuộc:

1. **Thử lại** trong `max_retries` lần (mặc định 3).
2. **Chia sớm** nếu model lặp lại y nguyên câu trả lời đã bị bác
   (`repeated_director_candidate`) — `Batch N repeated a critic-rejected candidate
   projection; split early into X + Y segments`.
3. **Chia sau khi hết lượt** — `Batch N vẫn không qua phản biện đạo diễn sau 3 lần; tự
   chia thành X + Y segment`.
4. **Chấp nhận nếu bất đồng không ảnh hưởng âm thanh** —
   `ANALYSIS_INAUDIBLE_DISAGREEMENT_ACCEPTED`, chỉ với
   `INAUDIBLE_DELIVERY_FIELDS = {emotion, intensity}`.

Hết bậc thì `raise RuntimeError`, và cả quyển sách chết.

## Lỗ hổng thật, đo được

Bậc 2 và 3 **cố tình từ chối chia** khi batch là một khối liền mạch có hội thoại:

```python
if not boundaries and contains_dialogue and len(group) <= HIGH_QUALITY_ANALYSIS_BATCH_SEGMENTS:
    return None
```

Lý do đúng: cắt giữa một lượt hội thoại làm việc gán người nói **tệ đi** — mà `speaker`
thường chính là trường đang tranh cãi. Batch chỉ có một segment cũng không chia được.

Bậc 4 thì không cứu, vì `speaker` có ảnh hưởng âm thanh.

Kết quả đã xảy ra thật ngày 05/09/2026: một lần chạy chết ở batch 74, bốn segment, model
lặp lại đúng một `speaker` bị tranh cãi. Mười chương phân tích đã xong mất theo.

> Cùng ngày, alpha.46 gặp ba lần bất đồng tương tự (batch 74, 80, 107) và **sống cả ba**,
> vì các batch ấy chia được. Nên đây là lỗi hiếm — nhưng khi trúng thì mất nhiều giờ.

## Vì sao không vá nhanh được

Đã thử, và test tích hợp chặn lại — ghi ở đây để không ai thử lại cùng cách:

Nhánh chấp nhận ở bậc 4 **chỉ chạy được với bất đồng đến từ host affect**, tức đúng
`emotion`/`intensity`, *sau khi* phản biện đạo diễn đã **chấp nhận**. Lúc ấy vẫn còn một
bản ghi chấp nhận để commit.

Khi **critic từ chối**, không thứ nào trong bốn thứ này được đặt:

- `accepted_director_evidence`
- `accepted_generator_contract`
- `accepted_host_clearance`
- `accepted_analysis_candidate_id`

Và đường commit bền vững đòi đủ cả bốn:

```python
if director_critic_required and accepted_director_evidence is None:
    raise RuntimeError(f"Phản biện đạo diễn bắt buộc thiếu evidence ở batch {group_index}")
```

Cho dữ liệu đi qua chốt này nghĩa là **tự chế ra một bản ghi "đã chấp nhận" cho một
candidate mà critic đã bác** — tức ghi một điều sai vào chính chuỗi bằng chứng QA mà cả dự
án dựa vào để nói phiên bản này đáng tin. Không đáng đổi.

Còn một cạm bẫy nữa: nếu chỉ "không raise" mà không trả lại dữ liệu, vòng commit rơi xuống
`_heuristic`, mà `_heuristic` trả `speaker = "UNKNOWN"` cho mọi dòng hội thoại. Như thế là
**tệ hơn** cách đọc đang tranh cãi, chỉ khác là im lặng hơn.

## Làm đúng thì làm thế nào

Cần một **trạng thái ledger tường minh**, không phải một đường vòng:

1. Thêm `ANALYSIS_CANDIDATE_ACCEPTED_UNDER_PROTEST` vào `database.py`, cạnh
   `ANALYSIS_CANDIDATE_CRITIC_REJECTED`. Trạng thái này nói đúng sự thật: đã publish, và
   critic **không** đồng ý.
2. Sinh evidence từ chính phán quyết của critic (`critic_evidence` vốn đã có sẵn ở nhánh từ
   chối), đánh dấu rõ là bằng chứng *phản đối*, không phải chấp thuận.
3. Nới chốt `director_critic_required` để chấp nhận trạng thái mới, chứ không phải để lọt
   `None`.
4. Vòng commit lấy dữ liệu từ envelope model bị từ chối
   (`candidate_json` → `_analysis_envelope_validated`), **không** từ `_heuristic`.
5. Phát `ANALYSIS_AUDIBLE_DISAGREEMENT_ACCEPTED` kèm `disputed_segments` (dùng
   `AnalysisFeedbackIssue.stable_id`, **không** phải `.id` — trường ấy không tồn tại) và
   `fields`, để trang review chỉ đúng segment cho người nghe.
6. Chỉ dùng ở bậc cuối: đã hết lượt thử **và** `split_result is None`.

Cả `analysis.py` lẫn `database.py` đều nằm trong `QUALITY_IMPLEMENTATION_FILES`, nên việc
này **phải đợi giữa hai lần chạy**.

## Test đã viết sẵn (và đã bắt được lỗi)

Ba test tích hợp dựng đúng tình huống — batch một segment hội thoại, critic luôn tranh cãi
`speaker` — và khẳng định: sách không chết, cảnh báo nêu đúng segment và trường, và
**speaker được publish là câu trả lời của model chứ không phải `UNKNOWN`**. Test thứ hai
mới là test quan trọng: sống sót thôi chưa đủ.

Chính chúng đã lôi ra chốt `thiếu evidence` mà test hàm rời không thể thấy. Khi làm lại,
viết lại chúng trước.
