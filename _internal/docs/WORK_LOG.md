# Nhật ký làm việc — kiểm chứng được, không cần tin lời

Mỗi dòng ở đây đều đối chiếu được với `git log`. Xem dấu thời gian thật bằng:

```bash
git log --format="%ad  %s" --date=format:"%m-%d %H:%M" -30
```

## Cơ chế: vì sao có lúc tôi đứng im, và cách chặn điều đó

Tôi chỉ hành động **trong một lượt**. Khi lượt kết thúc mà không còn việc nền nào đang
chạy, tôi đứng im cho tới khi có người nói. Đó không phải lười — đó là cách môi trường
hoạt động, và nó giải thích khoảng trống **07:40 → 10:35** ngày 2026-09-01.

Cách chặn: **luôn để một việc nền đang chạy**. Khi nó kết thúc, hệ thống tự đánh thức và
lượt mới bắt đầu. Một run nhiều chương vừa là công việc thật vừa là đồng hồ đánh thức.

Bố cục hai thư mục làm việc này khả thi:

| thư mục | dùng để |
|---|---|
| `D:\Novels\Ebook Reader` | chạy run thật (không sửa mã khi đang chạy) |
| `D:\Novels\Ebook Reader_dev` | worktree git, sửa mã và chạy test song song |

## 2026-09-01

| giờ | việc | bằng chứng |
|---|---|---|
| 03:20 | Hạ Thái Sơn + Thục Đoan xuống đáy bảng chọn giọng | `f42d780` |
| 04:00 | Hạ Thanh Bình xuống đồng hạng đáy sau khi mọi cách chữa tiếng "tóp" đều thất bại | `25e8ba` |
| 04:23 | Xếp hạng giọng trẻ em theo tai người nghe, đặt trên mọi phép đo tính toán | `3bd8fdc` |
| 04:27 | Phạm Tuyên số 1 cho bé trai theo phán quyết người nghe | `a4c1da8` |
| 04:40 | Cài `--stage tts` vào benchmark; đo 3 worker = 2,16× | `f733bbd` |
| 04:48 | `SynthesisPool` + `ReadOnlyVoiceDB`; 9/9 segment byte giống hệt | `3357488` |
| 04:58 | Nối pool vào pipeline, nạp trước theo lô | `57054f2` |
| 05:34 | Sửa anchor phát âm lệch — 17/79 segment chết tất định | `a0380b2` |
| 06:24 | Sửa phép đo tốc độ đọc: trừ chỗ nghỉ ra trước | `93ffd4f` |
| 06:43 | ASR không được chặn trên câu trả lời không ai lấy được | `2c8155c` |
| 07:03 | Segment ngắn: verified kèm cảnh báo thay vì failed | `25951f8` |
| 07:32 | Vá nốt nhánh thứ hai; thu hẹp lại sau khi test bắt lỗi | `63b2d93` |
| 07:39 | **Run đầu tiên đi trọn vẹn tới cùng** — 2/2 chương, exit 0 | `5322437` |
| 10:35 | Ngưỡng lô tối thiểu = 3, đo ấm và lặp lại | `42edce1` |
| 10:47 | Khởi động run 10 chương làm vừa công việc thật vừa đồng hồ đánh thức | — |

### Chuỗi lỗi trong `_validate_analysis_rejection_evidence` (run 10 chương)

Run 10 chương chạm vào những nhánh mà run 2 chương chưa từng chạm. Bốn lỗi liên tiếp, tất
cả cùng một gốc: **quyết định chấp nhận được tính từ danh sách trường đầy đủ thay vì tập
con nghe ra được**.

| lỗi | mệnh đề hỏng | commit |
|---|---|---|
| `Rejected critic evidence is not exactly candidate-bound` | `accept_flag` | `7c36caa` |
| `Rejected source-kind critic override is not source-bound` | `effective_accept` | `75f4cbe` |
| `Rejected critic outcome does not match unresolved evidence` | đang chờ khai | — |

**Cách rút ngắn chuỗi:** mỗi thông báo lỗi gộp 4–11 mệnh đề vào một câu mù, và bằng chứng
nằm trong bộ nhớ chứ không trên đĩa — nên muốn biết mệnh đề nào hỏng phải chạy lại cả pha
phân tích. Thêm phần khai tên mệnh đề biến mỗi lỗi từ *nhiều vòng đoán* thành *một vòng
đọc*. Đây là thứ đáng làm trước tiên cho bất kỳ phép kiểm gộp nào còn lại.

**Hai lần tôi đoán sai và bị test chặn**, ghi lại để không lặp:

1. Bóp `unresolved_fields` về tập con chặn được → **4 test hỏng**. Đó là *sổ ghi bằng
   chứng*, phải giữ đủ mọi trường; bóp nó là phá sổ ghi để chữa phán quyết.
2. Suy `effective_accept` từ tập con chặn được → **test thứ 5 hỏng**, một dòng cố ý từ chối
   chỉ vì `emotion`.

Kết luận đúng chỉ lộ ra sau hai lần sai: cờ chấp nhận **không suy ra được theo chiều nào**;
nó phải được *kiểm tính nhất quán* với hai hình dạng hợp lệ. Giờ `accept_flag_is_coherent`
phục vụ cả hai cờ.

## Đã đóng bằng kết quả âm — đừng làm lại

| việc | kết luận |
|---|---|
| Thiên lệch dư phép đo tốc độ | **5 mô hình đều thất bại**; mô hình 3 lớp thử cả trên dấu lẫn trên nhóm, cả hai lần R² cao hơn mà lệch tệ hơn. Chi phí cố định mỗi phát ngôn khớp ra hệ số **âm**. Phần dư +0,12 không phải số hạng nghỉ còn thiếu. `PACE_METRIC.md` |
| Song song hoá Ollama phía client | **1,00×**. Server tuần tự hoá; `OLLAMA_NUM_PARALLEL` là biến môi trường của server, không sửa trong mã được. `THROUGHPUT.md` |
| Bộ dò tiếng "tóp" đầu câu | Bị tai người nghe bác bỏ; UTMOSv2 xếp hạng ngược. `ONSET_CLICK.md` |
| Gộp hai lần tái tổng hợp giọng trẻ em | Người nghe chọn cách hiện tại. `CHILD_VOICE_TRANSFORM.md` |

## Việc còn tồn

1. **Chuỗi lỗi validator** ở trên — đang chạy, mỗi vòng một lỗi.
2. **Whisper song song**: đo được 0,70× nhưng **phép đo không dùng được** vì GPU đang bị run
   chiếm 6,2/8,15 GB. Dấu hiệu mạnh là Whisper ở 1 worker đã đẩy GPU lên 100% (TTS chỉ 23%),
   tức không còn chỗ rảnh để thu lại. Đo lại khi GPU trống.
3. **Chồng lấn giai đoạn**: đã có `scripts/phase_timings.py`, nhưng cần một run **mới tinh**
   để có số liệu thật (`--require-fresh` sẽ từ chối run resume).
4. **`OLLAMA_NUM_PARALLEL` phía server**: phải khởi động lại Ollama, chờ lúc không có run.
5. **HiFi-Glot** — tồn đọng lâu, chưa khởi động.

---

# Phiên 2026-09-02: cách đọc tên tiếng Anh, và một run chết vì kế hoạch không nói gì

## Việc bắt đầu từ đâu

Truy 9 segment fail của alpha.22 để hỏi người nghe xem cổng ASR có quá nghiêm không. Câu
trả lời hoá ra **ngược lại**: cả bốn tên bị chặn đều chứa cụm phụ âm **không tồn tại trong
tiếng Việt** (`xba`, `bla`, `lđ`, `xc`). Cổng bắt đúng; cách đọc mới là thứ sai.

Đo ra: **35/189 cách đọc đã khoá (18,5%) vi phạm chính bộ luật âm tiết của project**, và
chúng `locked=1` nên tồn tại xuyên mọi run.

## Gốc rễ, và bốn lỗi cùng lộ ra

`_cmu_pronunciations()` tra **cả cụm** trong CMUdict. Từ điển khoá theo **từ**, nên mọi tên
nhiều từ đều trượt và rơi xuống đường đọc theo **mặt chữ** — đường không biết 'e' câm và
không tách cụm phụ âm. Xem `ENGLISH_TO_VIETNAMESE.md` cho toàn bộ.

Bốn lỗi độc lập cùng lộ ra khi kiểm định toàn corpus:

1. `VIETNAMESE_SYLLABLE_ONSETS` có "d" nhưng **không có "đ"** — bộ kiểm tra chuẩn hoá đ→d
   trước khi so, bộ tách cụm thì không, nên bộ tách **bỏ cuộc** đúng chỗ bộ kiểm tra từ chối.
2. R trước phụ âm bị coi là âm đầu → đẻ ra âm tiết từ gốc không có (`A-rơ-thơ`).
3. Luật "r + d cuối lùi về -c" **viết trong comment, không có code nào thực hiện**.
4. Luật /l/ tự thành âm tiết không phân biệt trọng âm → nuốt phụ âm cuối của cả một lớp từ.

## Ba nguồn đối chiếu, mỗi nguồn bắt được thứ hai nguồn kia bỏ sót

| nguồn | quy mô | bắt được gì |
|---|---|---|
| 138 cách đọc người nghe viết ra | 138 từ | phần lớn các luật nguyên âm và thanh |
| Corpus sách (2 cuốn) | 1.495 + 1.692 từ | R làm âm đầu, /l/ theo trọng âm |
| Nguồn ngoài (10k từ + 27k tên) | 24.061 từ | không có ca không hợp lệ nào lọt |
| **Từ mượn tiếng Việt có sẵn** | 41 từ | `style`→"Xờ-t**aiu**", vần không tồn tại |

Nguồn thứ tư là do người nghe chỉ ra: *"bạn thực sự biết cách người việt đọc các từ tiếng
anh? sao bạn không tự áp dụng mục tiêu đó cho thuật toán mà cứ phải hỏi tôi?"* Đúng. Nó nằm
ở `tests/data_vietnamese_loanwords.py`, và **phần khó là lọc**: rất nhiều "từ tiếng Anh"
trong tiếng Việt vào qua **tiếng Pháp** (`ga-ra`, `cà phê`, `vắc-xin`, `sa-lát`) và sẽ kéo
bộ luật Anh→Việt đi sai hướng.

## Điều lặp đi lặp lại trong phiên này

**Bộ kiểm tra hợp lệ chỉ xét âm đầu và ký tự cuối, không bao giờ xét vần.** Nó cho qua
`Xă-mon` ("ă" không đứng lẻ được) và `Xờ-taiu` ("aiu" không phải vần). Cả hai chỉ lộ ra khi
**in kết quả ra cho người đọc** hoặc khi có **bộ đối chiếu độc lập** — không lần nào do suy
luận về luật. Đã vá hai ca cụ thể; **danh sách vần hợp lệ vẫn là lỗ hổng chưa lấp**.

**Luật phải phát biểu theo cái bị bỏ, không theo cái được giữ.** Viết "giữ phụ âm cuối nếu
là âm tắc" làm hỏng `name`, `game`, `james` — vì /m/ là âm **mũi**. Viết "bỏ nếu là âm xát"
thì đúng hết.

**Mỗi lần mở rộng một luật quá tay đều bị chính dữ liệu bắt lại**: "R + phụ âm kêu → -c" làm
`george` thành "Giọc"; tách từ ghép hoàn hảo trên 7 từ ghép thật nhưng hỏng 35 tên bịa.

## alpha.23 chết, và vì sao

`naturalness-repair candidate allocation must bind its exact trigger check id` ở chương 2.

Hai chỗ cấp phát candidate; **kế hoạch không nói cho chỗ nào biết phải cấp loại gì**. Lần đầu
nó im lặng, các lần sau nó **sao chép candidate trước**. Nên mỗi bên tự đoán mặc định khác
nhau — và một lần đoán sai thì sai mãi, 5 vòng rồi chết.

Đúng họ lỗi **"một sự thật viết ở hai nơi"** đã ghi trong log này từ phiên trước, lần thứ
sáu trong lịch sử project. Sửa: chính trigger là nơi duy nhất biết, nên kế hoạch đọc từ đó,
và đoạn quét trigger dùng chung giữa bên *từ chối* và bên *lập kế hoạch*.

Đáng ghi: **ràng buộc database đã làm đúng việc** — nó biến một lỗi đọc thành một run dừng
lại thay vì một cuốn sách nói hỏng. Cái thiếu là chưa ai test rằng bên gọi **có thể** lấy
đúng câu trả lời, và hoá ra không thể.

## Việc còn tồn (cập nhật)

1. **Danh sách vần hợp lệ cho bộ kiểm tra** — hai ca đã lọt trong phiên này.
2. **Retry phân tích**: 34% ca `DIRECTOR_FIELD_MISMATCH` chỉ bất đồng ở trường không nghe
   được. Cơ chế chấp nhận đã có nhưng chỉ chạy như phương án cuối. Cách sửa ít rủi ro nhất
   đã ghi trong `ANALYSIS_RETRY_COST.md`.
3. Whisper song song / chồng lấn giai đoạn / `OLLAMA_NUM_PARALLEL` / HiFi-Glot — như cũ.

## 2026-09-03 — hiệu năng: đo trước, sửa sau

Phiên này chuyển trọng tâm từ chuyển tự tiếng Anh sang hiệu năng toàn dự án. Ba phát hiện
đo được, một khoản lấy không đã làm, và một lần chạy bị giết.

### 1. ASR đắt hơn TTS (`docs/WHERE_A_RUN_SPENDS_ITS_TIME.md`)

Whisper 3.870s, TTS 2.055s, cảm thụ 2.538s trên alpha.25. Cả dự án vẫn ngầm coi TTS là
phần đắt nhất; không phải, và không gần. 2,14 lượt giải mã mỗi segment **không** phải lãng
phí - đã kiểm tra: lượt xác nhận chỉ chạy khi lượt đầu MISMATCH/INCONCLUSIVE.

### 2. Chấm cảm thụ giờ chạy cạnh ASR (commit `b96e2ce`)

Chấm điểm là đọc thuần trên CPU; Whisper giữ GPU; file WAV đã có trước khi Whisper bắt đầu.
Chín trên mười chương có ASR dài hơn chấm điểm, nên gần như toàn bộ 2.538s lọt vào trong.
Không verdict nào đổi. Hai điều làm cho việc chạy sớm là an toàn:

- **Điểm khoá theo checksum của âm thanh, không theo đường dẫn.** Vòng sửa ASR thu lại
  segment và ghi bản mới vào *đúng đường dẫn cũ*; khoá theo đường dẫn thì bản mới thừa
  hưởng điểm của bản đã vứt. Khoá theo checksum thì tra cứu đơn giản là trượt.
- **Khởi động là một lần đọc không chặn**, không phải cái gate. Gate lặp tới khi máy sẵn
  sàng, mà lặp ở đây thì chặn đúng cái ASR nó định nấp sau.

Khởi động sau khi Whisper đã nạp, không phải trước: số worker tính từ snapshot RAM, và
snapshot lấy lúc model chưa nạp thì hứa cho pool phần bộ nhớ model sắp đòi.

### 3. Ba lượt UTMOSv2 là cần (`docs/PERCEPTUAL_QA_COST.md`)

Đo: một lượt lệch tối đa 0,208 so với ba lượt, trên ngưỡng quyết định 0,8. Giữ nguyên 3.
Kết quả âm được ghi lại.

### 4. Máy hết VRAM và RAM (`docs/VRAM_AND_CONTEXT.md`)

GPU 8.151 MiB, còn trống 308 MiB; qwen3:8b chạy 22% trên CPU vì không lọt. `num_ctx` 16384
giữ ~2,42 GB KV cache mà prompt đo được chỉ dùng ≥1.351 token (8,2%) - nhưng đó là **cận
dưới**, và prompt vượt num_ctx thì Ollama cắt trong im lặng, nên chưa đổi. Commit `18295d5`
ghi lại các bộ đếm Ollama vẫn luôn gửi; lần chạy mới đầu tiên sẽ cho con số thật.

### 5. alpha.26 bị RAM giết ở 357/948 - và điều đó đã được sửa

Ba Unity Editor + Rider giữ ~5,5 GB; máy còn 1,1 GB; pipeline dừng khẩn cấp. Lần chạy
**không** phải thủ phạm: nó đã tự nhả model và số đo vẫn 1,4 → 1,1 GB.

Thiếu RAM do chương trình khác giờ là **chờ có giới hạn** (30 phút) thay vì giết lần chạy.
Chờ được là vì tới lúc đó mọi thứ tiến trình này giữ đã nhả hết - máy thuộc về ai cần nó.
Mỗi vòng thăm dò vẫn hỏi stop/pause, thiếu đĩa hay quá nhiệt thì không chờ, và hết giờ thì
dừng đúng như cũ.

### Bài học: đo hằng số mà thay đổi của mình dựa vào, trước khi ship thay đổi ấy

Phần chồng lấn "chấm cảm thụ cạnh ASR" dựa hoàn toàn vào `PERCEPTUAL_WORKER_RAM_GB` để
quyết định cấp mấy worker. Tôi ship nó mà không đo hằng số đó. Hằng số ghi 1,0 GB; thật ra
một worker tốn 1,76 GB (biên) và đỉnh RSS 2,18 GB.

Chuỗi hậu quả:

1. alpha.28 khởi động với phần chồng lấn và hằng số sai.
2. Đo ra hằng số sai ở nhịp sau. Với 7,3 GB trống, pool cấp 5 worker ≈ 8,8 GB. Ở pha ASR,
   Whisper chiếm ~2,5 GB, còn ~4,5 GB, pool cấp 2 worker ≈ 3,5 GB, để lại ~1,0 GB - **ngay
   dưới ngưỡng tới hạn 1,5 GB**. Đúng cách alpha.26 chết.
3. Phải khởi động lại alpha.28 để lấy bản sửa. Tiến trình Python đang chạy không đọc lại
   mã nguồn đã đổi.
4. `_validate_resume_stage_fingerprints` **chặn resume**: `analysis.py` và `models.py` đều
   nằm trong `ANALYSIS_CASTING_IMPLEMENTATION_FILES`, mà tôi đã sửa cả hai. Chặn đúng - trộn
   kết quả phân tích của hai phiên bản code là đúng thứ bất biến ấy tồn tại để cấm.
5. Mất 886/948 segment đã phân tích.

**Bài học thật không phải "đừng sửa code khi đang chạy"** - điều đó đã có trong quy tắc và
tôi vẫn giữ (chỉ sửa cây dev). Bài học là: **một thay đổi phụ thuộc vào hằng số nào thì
phải đo hằng số ấy trước khi ship.** Đo mất bốn phút; không đo mất một tiếng phân tích và
suýt mất cả lần chạy.

Ghi chú phụ: `models.py` chứa cả model dữ liệu phân tích lẫn `ResourceSnapshot`, nên một
thay đổi thuần về giám sát tài nguyên cũng làm hỏng vân tay resume của phân tích. Ghép cặp
này hơi rộng, nhưng tách `models.py` là một cuộc tái cấu trúc có rủi ro riêng; ghi lại là đủ.
