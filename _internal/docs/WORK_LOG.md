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

### `cast`: người nghe chốt giới tính nhân vật, giống `pronounce` chốt cách đọc tên

alpha.30 phân tích xong cả 948 segment rồi từ chối cast vì model trả lời NOAH nam hai lần,
nữ hai lần. **Từ chối là đúng** - một nhân vật bị lồng sai giới trong cả cuốn sách tệ hơn
một lần chạy dừng lại. Nhưng không ai làm gì được: giới tính nằm trong phần phân tích, phần
phân tích có vân tay, và mọi thay đổi code đủ sức phá thế hoà đều làm hỏng vân tay ấy và
bắt chạy lại cả pha. Một lỗi model mà người nghe trả lời trong một giây lại tốn một tiếng
máy chạy.

```bash
ebook-reader-headless cast <project> --character NOAH --gender male
```

Ghi vào `characters.locked`, cột đã tồn tại sẵn trên bảng mà **chưa đoạn nào tôn trọng** -
chỉ pronunciations mới dùng khoá. Ba chỗ phải cùng tôn trọng nó, và thiếu chỗ nào cũng vô
dụng:

1. `resolve_gender()` — quyết định đã ghim đứng trên cả model lẫn văn bản.
2. Cổng casting — không còn coi đó là xung đột.
3. `upsert_character()` — trước đây ghi đè `gender` **vô điều kiện**, nên một cái khoá mà
   chỉ resolver tôn trọng vẫn bị mất trên đường xuống hàng dữ liệu. Mọi thứ khác của nhân
   vật vẫn là của model.

Hàng được tạo cả khi casting chưa từng chạy, để câu trả lời đưa ra được **trước** lần hỏng
chứ không chỉ sau nó — nếu chỉ trả lời được sau thì vẫn phải trả tiền cho cả tiếng phân
tích ấy hai lần.

Chỉ nhận `male`/`female`. Ghim `unknown` là ghi lại một quyết định không ai đưa ra.

### `accept`: cánh cổng thứ ba, và lý do 2/10 chương

Đo alpha.25 mới thấy vì sao chỉ 2/10 chương xuất bản được:

| chương | trạng thái | segment lỗi | cảnh báo |
|---|---|---|---|
| 1 | xong | 0 | 0 |
| 4 | **xong** | 0 | **2** |
| 8 | **hỏng** | **0** | **8** |
| còn lại | hỏng | 1–4 | 0–5 |

Chương 8 hỏng với **không segment nào lỗi**. Chốt chặn là *mã cảnh báo nào* bị coi là chặn,
và `PERCEPTUAL_NATURALNESS_REVIEW` không nằm trong `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`.

Bốn segment mang cảnh báo đó ở alpha.32 có điểm 2,18–2,59 với `PERCEPTUAL_BASELINE_DROP` —
tụt thật so với bản xem trước của preset, không phải nhiễu. **Chặn là đúng.** Bộ kiểm tra
nói rất thật về ý nghĩa của nó: cần một đôi tai, chứ không phải bằng chứng bản thu hỏng.

Vấn đề là **không có đôi tai nào được phép trả lời**. Vòng sửa chữa thu lại và đôi khi không
khá hơn; cảnh báo còn nguyên; chương vĩnh viễn không xuất bản. Đó là một **bức tường, không
phải một cánh cổng**.

Và đây là lần thứ ba cùng một khoảng trống: `pronounce` tồn tại vì một cách đọc cần con
người, `cast` vì một giới tính cần, và giờ `accept` vì **một bản thu cần**.

```bash
ebook-reader-headless accept <project> --segment c00003_s0000001_571c52609c96 \
    --warning PERCEPTUAL_NATURALNESS_REVIEW --note "đã nghe, chấp nhận"
```

Khoá theo **checksum của bản thu đã nghe**, không theo segment: thu lại là chấp nhận cũ hết
hiệu lực, vì thứ được chấp nhận là *một bản ghi*, không phải *một hàng dữ liệu*. Cùng lý lẽ
đã dùng khi khoá điểm cảm thụ theo checksum.

Lệnh từ chối chấp nhận một cảnh báo mà segment không mang, và từ chối chấp nhận khi segment
chưa có bản thu nào — chấp nhận âm thanh chưa tồn tại là chấp nhận bất cứ thứ gì được tạo
ra sau đó.

### `retry`: để một bản sửa với được tới đúng segment nó viết ra để sửa

`_verify_chapter_audio` có dòng này:

```python
if str(row["status"]) == SegmentStatus.FAILED.value:
    continue
```

Nghĩa là **một segment đã hỏng là hỏng vĩnh viễn trong project ấy**. Resume duyệt lại mọi
chương (`_process_all_chapters` không bỏ qua theo trạng thái), nhưng segment hỏng bị bỏ, nên
chương lại hỏng vì đúng những segment cũ. Cách duy nhất để hưởng bản sửa là chạy sạch — một
tiếng phân tích để thu lại năm segment.

alpha.32 làm điều đó thành cụ thể: chương 6 bị từ chối vì một segment mà **giọng đọc đúng
từng chữ**, bản ghi chỉ khác ở "tháng Mười hai" so với "tháng 12". Bản sửa cho đúng chuyện
đó xuất hiện *trong lúc lần chạy vẫn đang bay*, và không có đường nào áp nó vào segment nó
được viết ra để sửa.

```bash
ebook-reader-headless retry <project> --note "đã sửa gộp số"        # mọi segment hỏng
ebook-reader-headless retry <project> --segment c00006_s0000089_... # một segment
```

Dùng `reset_segment_pending` đã có sẵn: trả segment về `analyzed`, xoá WAV, xoá bằng chứng
ASR, xoá warning, cập nhật lại số đếm chương. **Phân tích và casting giữ nguyên** — chúng
không phải thứ đã sai. Rồi `resume` thu lại và xác minh lại đúng những segment ấy.

Cũng bỏ dấu `failed` trên chương: để nguyên là giữ một lời từ chối đứng trên bản thu không
còn tồn tại.

Segment chưa hỏng thì không bị chạm — thử lại một segment đã đỗ là ném đi bản thu đã đạt.
Và lệnh báo lại đúng những gì nó reset, theo cùng quy tắc `pronounce`/`cast` đã theo: một
lần ghi không xảy ra thì không được báo là thành công.

### Bốn cánh cổng, cùng một hình dạng

| lệnh | người nghe quyết định điều gì | vì máy không quyết được |
|---|---|---|
| `pronounce` | một cái tên đọc thế nào | CMUdict và fallback cùng từ chối |
| `cast` | một nhân vật là nam hay nữ | model trả lời hoà 2-2 |
| `accept` | một bản thu nghe được không | điểm cảm thụ tụt, sửa mãi không khá hơn |
| `retry` | một bản thu đáng thu lại không | segment hỏng bị đóng băng vĩnh viễn |

Ba cái sau đều xuất hiện trong đúng một ngày, và cả ba đều là cùng một khoảng trống: dự án
nghiêm khắc trong việc từ chối mà không có đường cho con người giải quyết lời từ chối.

### Lỗi giết alpha.23 rồi giết alpha.32: planning không phải allocating

```
RuntimeError: naturalness-repair candidate allocation must bind its exact trigger check id
```

alpha.32 chết ở chương 8/10 vì đúng lỗi đã giết alpha.23. Bản sửa hồi đó (cho vòng sửa ASR
đọc plan) đúng nhưng **không phủ hết**.

Chuỗi sự kiện, đọc từ DB thật của segment 633 (`c00008_s0000023`, mang **cả hai** cảnh báo
`ASR_LOCKED_NAME_ANCHOR_REVIEW|PERCEPTUAL_NATURALNESS_REVIEW`):

1. Vòng sửa ASR cấp 5 candidate chuẩn, round 0–4, tạo lúc `t+740s` … `t+1398s`.
2. QA cảm thụ trên **cùng bản thu ấy** sinh trigger naturalness lúc `t+1643s` — **sau cả năm**.
3. Từ đó `segment_candidate_resume_plan` **ném** mỗi lần được gọi cho segment này.
4. Mỗi vòng, pipeline bắt exception, vô hiệu hoá candidate hiện tại **với thông điệp của
   lần cấp phát kế tiếp làm `failure_reason`**, rồi cấp thêm một cái nữa. Năm lần.
5. Hết ngân sách, cú ném lên tới đỉnh, lần chạy chết.

**Nguyên nhân:** `_candidate_perceptual_requirement_conn` xác thực *một hàng candidate đã
tồn tại*, nhưng nó gọi hàm có nhiệm vụ **từ chối cấp phát**. Bất biến ấy thật và cần giữ —
một candidate chuẩn không được **tạo ra** khi bản thu còn nợ một candidate naturalness —
nhưng nó chỉ có nghĩa ở **thời điểm cấp phát**. Lúc đọc lịch sử thì không có gì đang được
tạo ra, và một trigger đến sau thì không candidate nào có thể gắn nó.

Đã bỏ kiểm tra ấy khỏi đường **đọc**, giữ nguyên ở đường **cấp phát** (`allocate_segment_candidate`).
Với đúng dữ liệu ấy, plan giờ trả về **`action: "exhausted"`**: năm vòng đã dùng, không vòng
nào khá hơn, segment ở lại dạng cảnh báo và lần chạy đi tiếp. **Review không bị bỏ quên** —
nó vẫn là `PERCEPTUAL_NATURALNESS_REVIEW`, đúng thứ lệnh `accept` sinh ra để giải quyết.

### Hai lần tôi suýt sửa sai

Lần đầu tôi định làm bất biến ấy "biết thời gian" (bỏ qua trigger mới hơn candidate). Có một
test cũ **không docstring** khẳng định điều ngược lại, nên tôi kiểm tra: sau bản sửa đó, plan
trả về `action=generate` mà **không gắn trigger** — review sẽ bị bỏ quên thật. Bản sửa của
tôi sai và test cũ đúng về mối nguy.

Nhưng test cũ cũng chỉ đúng một nửa: nó biến "hết ngân sách" thành "giết lần chạy". Bản sửa
đúng không phải làm kiểm tra thông minh hơn mà là **đặt nó ở đúng chỗ**. Test cũ giờ có tên
mới và có docstring giải thích lần chạy nào đã chết vì nó.

Bài học: một test không có docstring không phải một quyết định, nó chỉ là một hành vi đã
được đóng băng. Nhưng cũng đừng phá nó trước khi hiểu nó canh cái gì.

### "File an toàn" là sai: có hai loại vân tay, và loại thứ hai tốn cả pha QA âm thanh

Tôi đã ghi trong quy tắc làm việc rằng `asr.py`, `pipeline.py`, `database.py`,
`perceptual_qa.py`, `cli.py`, `scripts/` là **an toàn** khi sửa trong lúc lần chạy đang bay.
Sai một nửa, và alpha.32 vừa cho thấy nửa sai.

Sau khi `retry` 6 segment rồi `resume` với các bản sửa (`database.py`, `asr.py`), số đếm
segment nhảy từ `verified: 596, warning: 34, failed: 6` sang `verified: 8,
signal_passed: 747`. Không phải `retry` làm — nó chỉ reset đúng 6.

Kiểm tra `quality_checks`: policy cũ `e3d2957a…` có **3.415** check, policy mới
`a120f719…` có **33**. Toàn bộ bằng chứng QA âm thanh mang policy hash cũ nên **hết hiệu
lực**, và pipeline phải chạy lại ASR + cảm thụ cho 747 segment.

Vì `QUALITY_IMPLEMENTATION_FILES` chứa: `analysis.py`, `asr.py`, `asr_contract.py`,
`audio_io.py`, `audio_transform_contract.py`, `character_registry.py`, **`config.py`**,
**`database.py`**, `expression.py`, `models.py`, **`pipeline.py`**, **`perceptual_qa.py`**,
`perceptual_contract.py`, `quality_policy.py`, `recovery.py`, `runtime_contract.py`,
**`text_processing.py`**, `tts.py` …

**Hai loại vân tay, hai cái giá khác nhau:**

| nhóm file | hậu quả khi sửa rồi resume |
|---|---|
| `ANALYSIS_CASTING_IMPLEMENTATION_FILES`<br>(`analysis.py`, `character_registry.py`, `models.py`, `voice_catalog.py`) | **Chặn resume.** Mất cả pha phân tích (~1 giờ) và phải tạo project sạch. |
| `QUALITY_IMPLEMENTATION_FILES`<br>(gần như mọi file còn lại, gồm `asr.py`, `pipeline.py`, `database.py`, `config.py`, `text_processing.py`, `perceptual_qa.py`) | Resume chạy được, **nhưng mọi bằng chứng QA âm thanh hết hiệu lực.** WAV còn nguyên (segment về `signal_passed`), phải chạy lại ASR + cảm thụ cho toàn bộ sách (~30–40 phút với 948 segment). |
| Chỉ `cli.py`, `scripts/`, `tests/`, `docs/` | Thật sự không tốn gì. |

Với alpha.32 thì cái giá ấy **đáng trả**: lần chạy lại xác minh bằng cả bản sửa gộp số lẫn
bản sửa planning-not-allocating, tức đúng hai thứ đang chặn nó. Nhưng đó là may, không phải
tính toán — tôi không lường trước.

**Hệ quả cho việc đổi sang faster-whisper:** nó sửa `asr.py` *và* đổi tập phụ thuộc, nên
đằng nào cũng làm hết hiệu lực toàn bộ QA. Làm trên một project sạch, đúng như
`docs/DEPENDENCIES.md` vẫn nói.

### Lần chết thứ ba của alpha.32, cùng một họ: hai vòng sửa chữa dùng chung một sổ

```
RuntimeError: stored candidate repair budget differs from the active repair context
```

Cùng vòng lặp `_repair_chapter_perceptual_candidates`, cùng lời gọi
`segment_candidate_resume_plan`, khác bất biến.

**Gốc:** hai vòng sửa chữa lấy ngân sách từ hai nơi và ghi vào **một sổ candidate**:

| vòng | ngân sách | candidate đã ghi |
|---|---|---|
| ASR (`pipeline.py:4563`) | `asr.repair_rounds` = **5** | 545 candidate `standard_candidate_gate_v1` |
| cảm thụ (`pipeline.py:1745`) | `perceptual_qa.repair_rounds` = **2** | 39 candidate `naturalness_improvement_v1` |

Và bảng có `UNIQUE(segment_id, policy_hash, repair_round)` — nghĩa là **hai đường dùng chung
một không gian số vòng**, nên mỗi segment chỉ thuộc về một đường. Đo trên dữ liệu thật:
**0 trên 122 segment mang cả hai loại candidate.** Thiết kế nhất quán.

Vì thế bất biến "mọi vòng của một segment phải cùng một ngân sách" **đúng**. Cái sai là
**người gọi tự nhận một ngân sách không phải của mình**: vòng cảm thụ áp con số 2 của nó lên
segment mà đường sửa đã thuộc về ASR với ngân sách 5.

**Sửa ở người gọi:** ngân sách chỉ là của vòng này khi segment **chưa có candidate nào**.
Có rồi thì các vòng của chính segment ấy quyết định. Một segment đã tiêu hết vòng cho ASR
thì lập kế hoạch ra **`exhausted`** — câu trả lời thành thật, thay vì một cú ném.

Kiểm trên chính DB của alpha.32: **45/45 segment lập kế hoạch được, 0 ca còn ném.**

### Ba lần chết, một hình dạng

| lần | bất biến ném | gốc |
|---|---|---|
| alpha.23 | `must bind its exact trigger check id` | vòng ASR không đọc plan |
| alpha.32 (1) | `must bind its exact trigger check id` | bất biến cấp phát bị gọi trên **đường đọc** |
| alpha.32 (2) | `stored candidate repair budget differs` | người gọi áp ngân sách **không phải của mình** |

Cả ba: **hai vòng sửa chữa chia nhau một sổ candidate, và một bất biến viết cho sổ đơn loại
bị áp lên tình huống hai loại.** Bất biến đúng cả ba lần; chỗ áp nó thì sai cả ba lần.

Điều đáng ghi cho người sau: khi thấy một bất biến ném trong `segment_candidate_resume_plan`,
câu hỏi đầu tiên không phải "bất biến này có quá nghiêm không" mà **"vòng nào đang hỏi, và
segment này thuộc về vòng nào"**.

### Lần chết thứ tư — tìm ra **trước** khi lần chạy gặp nó

Sau khi sửa lần chết thứ ba, tôi không resume ngay mà đi soi chính hàm ấy tìm các bất biến
cùng họ. Ngay dòng trên chỗ vừa sửa:

```python
if len(repair_bindings) != 1:
    raise RuntimeError("same-policy candidate rounds contain mixed repair trigger bindings")
```

Cùng giả định "một sổ, một loại". Trước đây không segment nào mang cả hai loại — **nhưng
chính vì lần chết trước đã chặn**. Bản sửa ngân sách của tôi vừa mở đường tới đó.

Dựng đúng tình huống: đường ASR chiếm segment, round 0 hỏng, rồi một review naturalness đến.

```
plan  : action=allocate round=1 requirement=naturalness_improvement_v1 trigger=3
cấp phát: NÉM "same-policy candidate rounds cannot mix repair trigger bindings"
```

**Bộ lập kế hoạch và bộ cấp phát mâu thuẫn nhau**: một bên bảo cấp phát naturalness, bên kia
bảo không được trộn.

(Lần dựng đầu tiên tôi truyền ngân sách 5 trong khi hàng đã lưu là 2, và nhận một lỗi
"cannot mix repair budgets" — **hiện vật của cách tôi dựng**, không phải lỗi thật. Dựng lại
cho khớp mới lộ ra lỗi thật.)

**Sửa ở người gọi, lần nữa.** Nhất quán với `UNIQUE(segment_id, policy_hash, repair_round)`:
mỗi segment thuộc **một** đường sửa. Vòng cảm thụ giờ bỏ qua segment mà candidate đang có
thuộc loại khác, ghi log, và để review ở lại dạng `PERCEPTUAL_NATURALNESS_REVIEW` — đúng thứ
lệnh `accept` sinh ra để giải quyết.

**Bốn lần chết, một hình dạng.** Và lần này là lần đầu tiên tìm ra trước khi trả giá: soi
các bất biến hàng xóm ngay sau khi sửa một bất biến cùng họ, thay vì resume rồi chờ.

### Gốc thật của cả bốn lần chết: một trạng thái không thoả mãn được, và một kế hoạch bảo cứ làm

Bản sửa lần thứ tư của tôi né ở người gọi. Viết một test ghim đúng tính chất mà cả bốn lần
chết đều vi phạm — **bộ lập kế hoạch không được đề xuất thứ mà bộ cấp phát từ chối** — thì
test **thất bại**. Né được ở một người gọi không có nghĩa mâu thuẫn biến mất; người gọi sau
sẽ lại vấp.

Hai bất biến ở tầng cấp phát gặp nhau:

- **A:** không được cấp candidate *chuẩn* khi còn trigger naturalness treo.
- **B:** các vòng của một segment không được **trộn** binding.

Một segment đã có vòng chuẩn (đường ASR) **và** đang có trigger naturalness thì **cấp gì
cũng vi phạm một trong hai**. Trạng thái ấy **không thoả mãn được**. Cả hai bất biến đều
đúng; không cái nào nên nới.

Nhưng `_planned_candidate_repair_binding_conn` đọc trigger **trước** và trả về binding
naturalness **vô điều kiện**, kể cả khi segment đã thuộc đường khác. Nên kế hoạch bảo "cấp
naturalness ở round N" còn bộ cấp phát ném — và người gọi không còn nước đi nào ngoài chết.

**Sửa:** khi trigger treo *và* các vòng đã có thuộc đường khác, bộ lập kế hoạch trả về
`exhausted` thay vì một chỉ thị bất khả. Review ở lại dạng `PERCEPTUAL_NATURALNESS_REVIEW` —
đúng thứ `accept` sinh ra để giải quyết.

**Vì sao không đảo thứ tự ưu tiên.** Cho "đường đã có thắng" nghe hợp lý hơn, nhưng nó tái
sinh lần chết thứ nhất: segment ấy sẽ được cấp candidate *chuẩn*, và bất biến A ném
"must bind its exact trigger check id" — đúng lỗi đã giết alpha.23. Trong một trạng thái
không thoả mãn được, mọi lựa chọn "cấp cái gì đó" đều sai; lựa chọn đúng là **không cấp**.

Test `test_the_plan_never_proposes_what_the_allocator_will_refuse` giờ ghim hợp đồng chứ
không ghim câu trả lời hiện tại: kế hoạch có thể **từ chối** thoải mái, nhưng nếu nó bảo cấp
phát thì việc cấp phát ấy phải làm được.

### `accept` với segment `failed`: ranh giới tôi vẽ ban đầu dựa trên một điều sai

Khi dựng `accept` tôi **cố ý** không cho nó chạm segment `failed`, lý do ghi lại là *"một
segment hỏng vì neo tên có nội dung ngoài tên **cũng** sai, nên chấp nhận nó là bắt người
nghe gánh những chữ máy không xác minh được"*.

Chính tôi đã bác bỏ lý do ấy sau đó, khi đọc bản ghi thật: phần tiếng Việt được phiên âm
**hoàn hảo**, chỉ cụm tiếng Anh trong ngoặc ra vô nghĩa. Nhưng ranh giới thì vẫn còn đó.

Bằng chứng đã đủ để dỡ nó:

- Bản đọc **đúng** ở các ca bị chặn (đã kiểm bảng `pronunciations` và bản ghi ASR).
- **faster-whisper nghe y hệt** — engine tốt hơn không cứu được lớp này.
- **Năm vòng sửa** mỗi segment, không vòng nào khá hơn.
- Khiếm khuyết canonical-similarity là thật nhưng **chưa có ràng buộc an toàn** để sửa.
- `chapter_is_publishable` đòi **không segment nào `failed`**, nên bốn chương của alpha.32
  bị chặn bởi đúng **một** segment mỗi chương.

Không ai ngoài người nghe phân xử được, và không có lệnh này thì sách **không bao giờ xuất
bản**.

**Chuyển sang `warning`, không phải `verified`.** Mã cảnh báo ở lại trên hàng và báo cáo vẫn
hiện nó, vì điều đã xảy ra là **một người phủ quyết cái máy**, không phải cái máy đổi ý.

Hẹp hơn vẻ ngoài của nó: chỉ chuyển hàng đang `failed`, chỉ với mã cảnh báo hàng ấy **thật
sự mang**, và chỉ khi checksum khớp bản thu đang có — nên một lần `retry` thu lại là quyết
định cũ hết hiệu lực. Giữa lúc nghe và lúc chấp nhận có thể đã có một lần thu lại; checksum
ở đó đúng để chặn việc bảo lãnh cho một bản ghi không ai nghe.

**Năm cánh cổng, cùng một hình dạng:** `pronounce` (cách đọc), `cast` (giới tính),
`accept` (bản thu nghe được), `retry` (bản thu đáng thu lại), và giờ `accept` cho cả bản thu
mà máy đã bó tay.

## Trang review nói *vì sao* cần nghe, không chỉ nói mã cảnh báo (2026-09-04)

Chủ sách hỏi thẳng: *"trong các file mà tôi cần review thì bạn phải note xem là tại sao đoạn
đó lại cần phải review chứ?"* Đúng. Một mã như `PERCEPTUAL_NATURALNESS_REVIEW` không nói
nghe cái gì, và tệ hơn, nó không nói máy **đã kiểm gì và thấy ổn** - nên người nghe phải xét
lại cả đoạn thay vì đúng một chỗ đang bị nghi.

`scripts/review_evidence.py` gom bằng chứng thật của từng đoạn bị chặn: mọi phép kiểm đã
chạy, phán quyết và con số của nó, mức khớp tốt nhất qua các lần giải mã, và với neo tên thì
cả **các âm tiết mà tên lẽ ra phải được đọc thành**. Chi tiết cuối quan trọng: với
`c00005_s0000013`, máy biết tên phải nghe ra "xa men cai dờ thê ô xờ ban" - đó chính là thứ
cần nghe, mà mã cảnh báo chưa bao giờ nói ra.

Mỗi thẻ giờ có bốn dòng: **máy thấy gì** (kèm số), **đã kiểm ổn** (để khỏi nghe lại),
**nghe cái gì** (cụ thể), **tin máy tới đâu**. Dòng cuối chính là chỗ phép đo thiên vị độ dài
trả công: cờ perceptual trên đoạn 1,5s đến từ một phép kiểm gắn cờ 9,9% đoạn ngắn so với 1,7%
đoạn dài - người nghe xứng đáng biết bằng chứng ấy yếu trước khi bỏ công.

### Tầng kiểm chứng là thứ đáng tiền nhất

Ghi chú do một workflow sinh: 14 agent viết, 14 agent **phản biện** từng ghi chú đối chiếu
với file bằng chứng. **11/14 bị sửa.** Những lỗi nó bắt được đều thuộc loại sẽ khiến người
nghe nghe nhầm chỗ:

- **bịa mốc thời gian** - "chỉ nghe 1 giây cuối" trong khi file không có mốc thời gian nào
- **đếm sai** - "4 lần giải mã" trong khi file ghi 5
- **bảo kiểm thứ máy đã xác nhận đạt** - dò xem có nuốt chữ không, khi ASR đạt 1.0 cả 5 lượt
- **lấy chính tả ASR làm bằng chứng phát âm** - Whisper viết sai dấu tiếng Việt là chuyện
  thường, không chứng minh giọng đọc sai (cùng nguyên tắc với neo tên)
- **trích số đẹp nhất như thể là mức chung** - 0,98 chỉ có ở 2/12 lần, 10 lần còn lại 0,87-0,91

Một ghi chú sai bằng chứng còn tệ hơn không có ghi chú, vì nó điều hướng sự chú ý sai chỗ.
Đó là lý do tầng phản biện tồn tại, và tỉ lệ 11/14 nói nó không thừa.

---

## Đêm 06→07/09/2026: ba bản sửa được chứng minh, và bốn cơ chế tôi đoán sai

### Kết quả

alpha.50 ra **6/10 chương**; alpha.51 ra **8/10, 73 phút audio** — bản tốt nhất tới nay. Hai
chương còn lại (5 và 10) chờ đúng **hai lần nghe**, và audio của chúng giống hệt từng byte
qua bốn phiên bản nên nghe một lần là xong.

Ba bản sửa, mỗi cái có bằng chứng sống chứ không chỉ test:

| bản sửa | bằng chứng |
|---|---|
| cổng thứ sáu | chương 3 và 7 xuất được sau khi chết ở 5 và 3 bản liên tiếp |
| chặn lặng hai đầu | chương 8: 0,68s so với 1,02s (hỏng) ở alpha.48 |
| gieo cách đọc tên | pha tên bỏ qua hoàn toàn; `Theosbane` giữ `theo-bên` của chủ sách |

### Phát hiện lớn nhất: `resume` giữa pha phân tích đổi quyển sách

Thí nghiệm có đối chứng, một biến: cùng code, cùng nguồn, một lần `stop`/`resume` ở 620/948
→ tập nhân vật **23 → 19**, 18 đoạn đổi người nói, **toàn bộ sau mốc bị ngắt**. Tái hiện
đúng dấu vân tay của alpha.50. Đã thành quy tắc trong `AGENTS.md`.

Kèm theo: **nền nhiễu của phân tích hiện là 0%**, không phải 3,1–7,4% như tài liệu kế thừa.
Chính vì tin 0% mà 18 đoạn lệch mới bị truy tới nơi.

### Bốn lần đoán sai cơ chế, và cái chung của chúng

1. **cờ cảm thụ là nhiễu** → sai; máy chấm tất định (10 file, 0 lần đổi phán quyết)
2. **sửa file bị khoá đổi muối seed** → sai; seed chỉ phụ thuộc `stable_id + voice_key + salt`,
   cái đổi là **casting**
3. **resume chia lại batch** → sai; 200 vân tay nhóm giống hệt, có sẵn trong
   `analysis_candidates`
4. **mảnh bị cụt ngữ cảnh** → sai; `original_context` mang láng giềng qua lỗ, có test ghim.
   Mảnh mất **tính chung**, không mất ngữ cảnh

Cả bốn đều đọc ra từ mã nguồn và đều nghe trọn vẹn. Cả bốn đều bị bác bởi thứ đã nằm sẵn
trong kho: một bảng, một test, một phép đo. **Đọc code cho ra giả thuyết, không cho ra kết
luận** — trong repo này gần như luôn có sẵn thứ để hỏi.

### Hai lỗi tôi tự gây ra

- **Trang A/B ghép nhầm audio**: dựng đường dẫn từ `seq` trong khi thư mục đặt tên theo
  `segment_id`. Đã gửi cho chủ sách trước khi kiểm. Giờ mọi cặp đều được xác minh đúng chiều
  trước khi gửi.
- **Watcher tự tắt sau 3 phút**: tôi thay tín hiệu `state.json` bằng heartbeat của lease và
  **khẳng định** rằng lease đập thường xuyên, thay vì kiểm. Nó chập chờn — chạy đúng 5 tiếng
  cho alpha.50, rồi cũ 2.380 giây trên alpha.51. Bắt được 15 phút trước khi cửa sổ chương 3
  đóng; nếu không thì chương ấy lại chết như năm bản trước.

Điểm chung: **cả hai đều hỏng lặng lẽ**. Đó là lý do mọi test mới đêm nay đều khẳng định
*kết quả được nhận*, không phải *lệnh chạy xong*.

## 2026-09-07 — Ba phát hiện, và alpha.51 chốt ở 8/10

**1. Phép kiểm cảm thụ: không có tín hiệu đo được.** Thí nghiệm mù mười cặp, chủ sách chấm.
4 đúng / 3 ngược / 3 không phân biệt được — ngang tung đồng xu (P(≥4/7)=0,50) trên chính
mười lời chê to nhất nó từng đưa ra. Chi tiết và ba lựa chọn: `PERCEPTUAL_QA_COST.md`.

**2. Neo tên khoá đang chấm chính tả, không chấm cách đọc.** Nó loại hai bản thu đọc **đúng**
tên "Samael" và giữ lại bản đọc **sai** ("Sam Min"), vì Whisper viết `Kaiser` còn neo đòi
`cai dờ` — cùng một âm, khác chính tả. Van cứu bằng độ tương đồng tắt đúng ở câu mà tên chiếm
phần lớn số chữ, tức câu tự giới thiệu tên. `raw_similarity` của bản đúng là 0,818 trên ngưỡng
0,78: đủ điều kiện đỗ, không ai hỏi tới. Chi tiết và ba hướng sửa:
`LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md`.

**3. Phán quyết của người nghe không sống qua một `resume`.** Chấp nhận → `warning` → resume
kiểm lại → `failed` → cổng bằng chứng từ chối, vì miễn trừ nằm sau cửa trạng thái. Vòng lặp
khép kín; chương 10 không thể xuất bản nếu không sửa mã. `LISTENER_VERDICTS.md`.

**Chốt alpha.51: 8/10 chương.** Chương 5 và 10 đều bị chặn bởi phát hiện 2 và 3 — cả hai đều
là lỗi mã, **không** phải lỗi bản thu, và không phải chuyện chờ tai người.

**Đáng chú ý về phương pháp.** Cả ba phát hiện đều ra từ bằng chứng máy đã lưu sẵn từ trước —
`segment_candidates`, `locked_name_anchor_metrics`, mốc thời gian trong `quality_checks` — chứ
không cần chạy thêm lượt nào. Sổ ghi đã có câu trả lời từ lâu; chỉ là chưa ai hỏi nó.

Và hai lần trong phiên này tôi chẩn đoán sai rồi bị bằng chứng bẻ lại: đoán "phiên âm thiếu
âm" (chủ sách sửa: phiên âm đúng, giọng đọc sai), rồi đoán "phải sửa từ điển cho cả 18 đoạn"
(Whisper cho thấy 17/18 vốn đã đúng). Bài học lặp lại: **đọc bằng chứng đã lưu trước khi dựng
giả thuyết** — nó nằm sẵn trong database cả rồi.

### Ba fix, nhánh `fix/anchor-and-acceptance` (2026-09-07 chiều)

**1. Tắt phép kiểm cảm thụ trong hồ sơ `high_quality`.** Chủ sách quyết sau khi xem kết quả
A/B. Không xoá bộ máy: một dòng cấu hình bật lại được, và bộ test của nó tự bật lên để vẫn
kiểm được. Đây là thay đổi mã chứ không phải cấu hình, vì `validate_settings` vốn **bắt buộc**
`high_quality` phải bật cảm thụ.

**2. Đưa miễn trừ "chủ sách đã nghe" lên trước cửa kiểm trạng thái** trong
`chapter_segments_have_current_audio_qa`. Test mới: hai test ghim fix (đỏ trên mã cũ, xanh
trên mã mới), ba test canh biên (xanh cả hai bên — chấp nhận vẫn buộc vào checksum bản thu,
`retry` vẫn vô hiệu hoá nó, đoạn chưa ai nghe vẫn bị chặn).

**3. Neo tên khoá: so âm thay vì so chữ.** Việc lớn nhất, và cũng là việc tôi sai nhiều lần
nhất. Ghi lại hai hướng đã đo rồi vứt vì chúng *trông* đúng:

- Nới van tương đồng cả câu: bản đúng 0,818, bản hỏng 0,816. Thả cả hai.
- Tương đồng ký tự theo thành phần: tách được hai bản đó (0,800/0,667) nhưng "Lucian" đối
  "Lucien" được 0,833 — cao hơn bản phải đỗ. **Dựng thử làm đỏ 18 test.**

Hướng dùng: so **âm tiết bằng `_vietnamese_phonemes`**, theo từng thành phần tên. "xa" và
"sa" cùng một âm còn "men" và "min" thì không; "kaizer" và "kaiser" ra âm giống hệt. **Không
ngưỡng nào cả.**

Bốn ràng buộc phát sinh, mỗi cái do một test cũ bắt được, chi tiết trong
`LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md`. Đáng nhớ nhất là cách chữa nghe hợp lý mà sai:
ghim tìm kiếm vào vị trí phép căn chỉnh gán cho neo — khi neo không khớp, phép căn chỉnh đặt
nó ở chỗ **rẻ nhất về chi phí sửa**, với ca Samael là token cuối câu.

**Kết quả trên dữ liệu thật, qua đường thật:** vòng 0 chương 5 (đọc đúng) ĐỖ, bản đang giữ
(đọc sai) TRƯỢT, vòng 4 (hỏng) TRƯỢT, và `c00010_s0000017` — đoạn chủ sách nói "đúng rồi" —
ĐỖ, tức **chương 10 không còn cần tai người nữa**.

**Cách làm đáng giữ:** mọi khẳng định cơ chế trong phiên này đều sai cho tới khi đo. Bốn lần
hôm qua, ba lần hôm nay. Bộ test cũ là thứ bắt được cả ba lần hôm nay — chúng ghim những
ràng buộc mà người viết fix mới không có cách nào tự nghĩ ra. Đừng nới một test cũ để fix mới
xanh; đọc xem nó đang bảo vệ điều gì.

## 2026-09-07 chiều — sáu fix, và bốn trong số đó tìm ra trước khi chúng kịp tốn gì

alpha.52 chốt 5/10, alpha.53 đang chạy với cả sáu. Nhưng điều đáng để lại cho người sau không
phải danh sách fix, mà là **cách chúng được tìm ra**.

### Bốn cái tìm ra bằng cách hỏi

| fix | câu hỏi đã dẫn tới nó |
|---|---|
| cổng thứ tám (`chapter_is_publishable`) | "còn chỗ nào quyết định xuất bản mà chưa bao giờ hỏi bảng chấp nhận?" |
| gạch nối trong chính tả Anh | "fix này phủ được bao nhiêu trong 112 cách đọc thật?" → 107, hụt 5 |
| ràng buộc liền kề | "bản vá của tôi làm gì **dễ dãi hơn**, và chỗ đó có nhìn thấy được không?" |
| resume gửi nguyên nhóm | "cái giá tôi *đoán* lúc đẩy câu hỏi sang chủ sách là bao nhiêu?" → 0,42% |

Bảy cổng đầu tiên của họ phán quyết đều tìm ra bằng cách để một chương chết vào từng cái, mỗi
lần một lượt chạy. Cổng thứ tám tốn một lần `grep` và mười phút. **Với bất kỳ chính sách nào
có nhiều điểm thực thi, liệt kê hết rồi kiểm từng cái rẻ hơn hẳn chờ chúng cắn.**

### Hai cái phải trả giá mới thấy

- **Cổng thứ tám** bị chương 7 đẩy sang: phán quyết đã gieo, khớp checksum, dòng vẫn `failed`.
- **Nửa sau của fix neo** bị chương 5 và 10 phơi ra, và đây là bài học đắt nhất:

  | đoạn | `anchor.passed` | canonical | chương xuất được? |
  |---|---|---|---|
  | `c00005_s0000013` | **True** | 0,00 / 0,75 | **không** |
  | `c00010_s0000017` | **True** | 0,43 / 0,43 | **không** |

  Nhìn `anchor.status` thì cả hai trông như đã sửa xong. **Chỉ khi hỏi "chương có xuất được
  không" mới lộ ra là chưa.** Nghiệm thu một bản vá bằng trường trạng thái nó vừa đổi là
  nghiệm thu chính cái nó vừa làm — phải hỏi tới kết cục cuối cùng.

### Ba lần sai bị bằng chứng bẻ, và một lần suýt

Chẩn đoán "phiên âm thiếu âm" (chủ sách sửa), "phải sửa từ điển cả 18 đoạn" (Whisper cho thấy
17/18 vốn đúng), "hai test bất đồng" (chỉ một). Và suýt ship một lỗ hổng dễ dãi trong chính
bản vá của mình — bắt được không phải nhờ test mà nhờ hỏi ngược lại.

### Cái giá của việc không nhường máy

Ba lượt pytest đầy đủ chạy đè lên pha phân tích alpha.52. Phân tích lệch một lần ở nhóm 45/201
rồi lan ra 57 nhóm; nhãn một nhân vật đổi → giọng 16 thành 14 → giọng mới không đọc được "Mẹ
kiếp" → **mất chương 6, không cứu được trong bản đó**. Chưa chứng minh được nhân quả, nhưng
chờ thì tốn không gì cả. Quy tắc đã ghi vào `AGENTS.md`, phần invariant an toàn.
