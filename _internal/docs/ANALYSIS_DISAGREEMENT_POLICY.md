# Khi phản biện đạo diễn và bộ phân tích không đồng ý với nhau

## Quyết định của chủ nhân (05/09/2026)

Hỏi trực tiếp, chủ nhân chọn: **lấy cách đọc của model, gắn cảnh báo, để tai người nghe
quyết** — thay vì để cả quyển sách chết. Cùng hình dạng với lựa chọn trước đó về dải nhịp
("lùi về `normal` nhưng ghi cảnh báo").

Đã cài đặt xong trên `dev/alpha13` (`f7dcb43`), **chưa merge** vì `analysis.py` nằm trong
`QUALITY_IMPLEMENTATION_FILES` và alpha.46 đang chạy.

Tài liệu này ghi lại cách làm, và quan trọng hơn là **hai cách làm sai mà tôi đã thử
trước** — cả hai đều trông hợp lý. Đừng lặp lại chúng.

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

## Cách sai thứ nhất: chỉ gỡ chốt cho dữ liệu đi qua

Test tích hợp chặn lại. Ghi ở đây để không ai thử lại cùng cách:

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

## Cách sai thứ hai: thêm một trạng thái ledger mới

Bản ghi đầu của tài liệu này kết luận phải thêm `ACCEPTED_UNDER_PROTEST` kèm migration
bảng, vì `analysis_candidates.state` có `CHECK (state IN (...))`. Nghe có vẻ đúng đắn —
nhưng nó **đắt mà không cần thiết**, và một migration schema chỉ để lách một chốt là dấu
hiệu chốt ấy đang bị hiểu sai.

## Cách đã làm

Không đụng schema, không thêm trạng thái.

Mấu chốt: **không cần nói dối chỗ nào cả.**

- **Hàng ledger giữ nguyên `critic_rejected`.** Vì đó là sự thật. Critic đã bác.
- **Candidate cố ý *không* được gắn vào commit** (`analysis_candidate_id=None`).
  `database.py` có chốt cứng: commit kèm candidate id thì candidate **bắt buộc** phải
  `critic_accepted`. Chốt ấy đúng, nên đừng nới nó — chỉ cần đừng khai đây là một commit
  được chấp nhận, vì nó không phải.
- **Ba dữ kiện commit cần đều là sự thật độc lập với phán quyết của critic**: generator
  contract (generator đã sinh ra gì), host affect clearance (host đã thông qua gì), và
  chính phán quyết phản đối của critic. Cả ba đọc lại được từ candidate row bền vững.
- **Sự kiện commit là `ANALYSIS_DIRECTOR_CRITIC_PROTESTED`**, mức `warning`, chứ không phải
  `..._ACCEPTED`. Sự kiện commit mới là thứ một lần audit về sau đọc; ghi "accepted" ở đây
  là giấu đúng cái duy nhất đáng biết về những segment này.
- **Dữ liệu publish lấy từ envelope model bị từ chối**, không phải `_heuristic`.

### Cạm bẫy thứ hai, suýt làm hỏng đúng ý người ra quyết định

Nếu chỉ "không raise" mà không nạp lại `validated`, vòng commit rơi xuống `_heuristic` — hàm
ấy dò cảm xúc bằng từ khoá và trả `speaker = "UNKNOWN"` cho **mọi** dòng hội thoại. Tức là
chọn "giữ cách đọc của model" nhưng nhận về "không có người nói". Tệ hơn cách đọc đang tranh
cãi, chỉ khác là im lặng hơn. Vòng commit còn index thẳng `validated[stable_id]`, nên nhánh
mới **bắt buộc** phải tự nạp lại `validated`.

### Ranh giới: chỉ bất đồng, không phải critic hỏng

Nhánh mới **chỉ chạy khi mọi issue là `DIRECTOR_FIELD_MISMATCH`** — tức critic đã đọc phần
delivery và nêu đích danh trường nó không đồng ý. Đó là tình huống chủ nhân phán quyết.

Một critic trả về câu trả lời không dùng được (`DIRECTOR_INVALID_RESPONSE`, hash mismatch)
thì **không phải đang bất đồng — nó đang hỏng**, và publish đè lên một cái hỏng là một quyết
định khác mà chưa ai đưa ra. Những trường hợp ấy vẫn kết thúc batch y như cũ.

> Bằng chứng ranh giới vạch đúng chỗ: ba test có sẵn quanh "invalid reason" và "exhausted
> budget" **xanh trở lại mà không phải sửa một dòng nào** sau khi thu hẹp. Trước khi thu
> hẹp, cả ba đều đỏ.

### Một cái bẫy trong chính test

Sửa `speaker` trong phán quyết của critic làm **câu trả lời của critic** trượt kiểm tra
provenance, và hệ thống ghi nhận là `DIRECTOR_INVALID_RESPONSE speaker_provenance` — tức
test dựng nhầm sang nhánh "critic hỏng". Dùng `pace`: cũng ảnh hưởng âm thanh, không bị
kiểm provenance, và cho ra đúng `DIRECTOR_FIELD_MISMATCH` như lần chạy thật.

### Bậc thang sau thay đổi

`test_persistent_director_rejection_splits_then_publishes_the_singleton` ghi lại: một batch
4 segment đi qua `[4, 4, 2, 2, 1, 1, 1, 1, 2, 2, 1, 1, 1, 1]`. Kỳ vọng cũ dừng ở
`[4,4,2,2,1,1]` vì singleton đầu tiên giết cả quyển sách; giờ nó xử hết cả bốn segment.

## Đo rồi bỏ: Ollama giữ VRAM sau pha phân tích

Trong alpha.46, pool TTS có lúc phải tổng hợp tuần tự vì VRAM chỉ còn ~3.990 MiB, và giả
thuyết là Ollama vẫn ôm 6 GB sau khi phân tích xong. **Không phải.** Ollama tự nhả model
theo `keep_alive` mặc định; kiểm tra lúc đó `/api/ps` trả `{"models":[]}` và GPU còn 6.159
MiB. Cửa sổ bị siết chỉ kéo dài 20:34 → 20:36, tức khoảng 2,3 phút ở mức lợi 1,12× của
pool — **mất chừng 15 giây**. Không đáng thêm một lời gọi unload vào ranh giới pha.
