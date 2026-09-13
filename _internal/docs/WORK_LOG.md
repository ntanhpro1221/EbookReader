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

## Đêm 2026-09-07 → 08: bốn chỉ thị, và ba phép kiểm bắt nhầm thứ

Chủ sách ra bốn lệnh: **(1)** dấu ngoặc thiếu không được làm hỏng chương trình, **(2)** không
phải tự nghe, project phải tự ra sản phẩm, **(3)** chia lô theo số từ chứ không theo chương,
**(4)** cần cài gì cứ cài.

### Kết quả

| | trạng thái |
|---|---|
| (4) cài `praat-parselmouth` + `librosa` | **xong** — 6 test mù bấy lâu giờ chạy, 49/49 xanh |
| (3) chia lô | **xong** — `plan_batches.py`, cân theo giờ máy |
| (1) ngoặc treo | **xong, đã kiểm, chờ áp** — 478/478 chương chia được **không sửa nguồn** |
| (2) không cần tai người | **quá nửa** — 3/6 đoạn chặn được giải phóng |

### Ba phép kiểm cùng một hình dạng lỗi

Không phải "ngưỡng đặt sai". Cả ba là **một lớp ca chưa ai nghĩ tới**:

| phép kiểm | định bắt | thực tế bắt |
|---|---|---|
| neo tên (`asr_only_failure`) | tên bị đọc sai | mọi đoạn **chỉ gồm** một tên ngắn |
| `is_vocalization_only` | tiếng cười | tiếng cười — trừ khi viết là `Ahaha` |
| trần khung (`generation_frame_cap`) | mô hình lảm nhảm vô tận | câu không hạ giọng |

Cả ba lộ ra bằng cùng một cách: **nhìn vào những ca bị chặn rồi hỏi chúng có điểm gì chung.**

### Chỗ tôi sai, và thứ cứu tôi

Tôi công bố rằng `generation_endpoint_active` bắt nhầm ngữ điệu, kèm một tương quan tuyệt đối
(0/899 trên dấu chấm, 14/57 trên dấu phẩy và hỏi), viết bản vá, viết tài liệu, báo chủ sách.
**Mũi tên nhân quả ngược.** Câu không hạ giọng → mô hình không dừng → chạm trần → **cắt thật**.
Cả năm bản thu của `"Rồi, rồi,"` dài đúng 0,96 giây, bằng trần khung.

Thứ bắt được: một test tên `..._remain_blocking` đỏ lên — người trước đã ghim đúng hành vi tôi
vừa bỏ. **Quy tắc rút ra:** test đỏ đúng chỗ vừa đổi, tên mô tả chính hành vi vừa bỏ, thì mặc
định là *mình sai* cho tới khi đọc xong và chứng minh ngược lại.

Chi tiết: [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md).

### Hai lần đo sai vì chọn nhầm cửa sổ

1. **"6% nhân vật lặp lại giữa các lô"** — đo trên chương 000–018, khúc mở đầu, nơi sách thay
   nhân vật nhanh nhất. Cả cuốn: **80%**, đến lô 9 là 95%. Sai số 13 lần, và nó là khác biệt
   giữa "chia lô vô hại" và "chia lô làm hỏng phân tích".
2. **"563 lượt thu vòng 2–4 cứu được 4 segment"** — mẫu số bị chính những ca vô vọng nhồi lên.
   Đếm theo *segment*: **106/641 = 16,5%** lấy bản thắng từ vòng 2 trở đi.

Cùng một bài học: khi một con số dẫn tới kết luận "bỏ cơ chế này đi", kiểm xem mẫu số có bị
chính thất bại nhồi lên không, và cửa sổ đo có đại diện không.

### Một dự đoán ghi trước, và nó đúng

Trước khi chạy alpha.56 tôi ghi: *chương 011 phải xuất **vì đọc đúng**, không phải vì phán
quyết — tôi cố ý không chấp nhận đoạn danh sách kỹ năng.* Kết quả: bản ghi sạch cụm "giá trị
tuyệt đối", similarity 0,57 → 0,83, chương 115/116 → **116/116**, và **3,68 giây lời đọc thừa**
biến mất. Ghi trước cái gì sẽ khiến mình nghi ngờ là cách duy nhất để một kết quả tốt có giá trị.

## 03:00 — alpha.57 chết vì một từ: `Cred`

```
RuntimeError: High-quality pronunciation QA could not resolve: Cred
```

Cùng một hình dạng với dấu ngoặc kép: **một từ trong nguồn làm dừng cả cuốn sách.**

`Cred` là đơn vị tiền trong truyện, có mặt ở **24/478 chương**. Trong cùng lô có 12 tên trượt
kiểm tra qua 3 lần thử; 11 cái được cứu bằng từ điển CMU hoặc dự phòng cục bộ. Riêng nó có cụm
phụ âm đầu `cr` không nằm trong `LATIN_NAME_ONSET_READINGS`, nên
`_short_name_local_fallback_is_safe` từ chối đoán — **đúng**, đoán sai một cái tên suốt cả cuốn
thì tệ hơn nhiều.

Nhưng rồi nó ném lỗi. Một lượt chạy **1.357 segment đã phân tích xong** dừng ở bước ngay sau
phân tích, và thứ duy nhất đưa nó đi tiếp được là một người gõ tay cách đọc vào.

### Mã tự mâu thuẫn với chính nó

```
self.log("Bỏ qua cách đọc tự động cho tên ngắn chưa đủ chắc chắn: ['Cred']. TTS sẽ đọc nguyên văn.")
...
raise RuntimeError("High-quality pronunciation QA could not resolve: Cred")
```

Ba dòng nói "TTS sẽ đọc nguyên văn", dòng sau giết cả lượt chạy. Hai câu ấy không thể cùng đúng.

Và lập luận biện hộ, trong docstring của `_command_pronounce`, thật ra **ủng hộ đọc nguyên
văn** chứ không ủng hộ dừng: *"đọc sai một cái tên suốt cả cuốn còn tệ hơn để người đọc đánh
vần chữ Latin"*. Kết luận của câu ấy là đánh vần, không phải dừng. Dừng chỉ đúng khi có người
đứng sẵn để hỏi.

### Đã làm

1. **Gỡ tắc ngay:** thêm `Cred` → `Cờ-rết`, khớp đúng số nhiều của chính nó (`Creds` →
   `Cờ-rết`) đã có sẵn trong bảng, cùng họ với `Credit` → `Cờ-re-đít`.

   Ghi với nguồn `english_name_transliteration`, **không phải** `listener_choice`. Đây là
   phỏng đoán của máy theo đúng quy ước máy đã dùng cho 176 tên khác; gán nó thành quyết định
   của chủ sách sẽ nhân bản vĩnh viễn qua `port_pronunciations`, thứ giữ nguyên `source`.

2. **`resume`, không tạo lại.** 1,5 giờ phân tích được giữ nguyên.

3. **Vá gốc, đang chờ máy rảnh:** bỏ `raise`, giữ nguyên việc từ chối đoán, ghi sự kiện
   `NAME_PRONUNCIATION_UNCERTAIN_SKIPPED` rồi đi tiếp.

   Có một test ghim hành vi dừng — `test_high_quality_blocks_unresolved_short_name_pronunciation`
   — và tối nay tôi đã trả giá một lần cho việc đè lên loại quyết định như thế. Khác biệt lần
   này: **chủ sách đã ra lệnh thẳng vào đúng lớp lỗi này** ("nhỡ sách khác cũng gặp chuyện thế
   này thì project phải tự xử lý được chứ?"), chứ không phải phân tích của tôi thắng. Test được
   viết lại kèm nguyên do, không xoá đi.

### Bức tường ấy rộng bao nhiêu

Đo bằng chính đường ống, trên 9 chương mới của alpha.57:

| | |
|---|---|
| cách đọc mới sinh ra | **55** |
| tên trượt kiểm tra (3 vòng thử lại) | 12 → 9 → 3 |
| tên **không cứu được** | **1** (`Cred`) |

Tức **một lần dừng cứng trên mỗi chín chương mới**.

Tôi **không** nhân con số ấy lên 478 chương, vì đó đúng là cái sai đã mắc với "6% nhân vật lặp
lại": tên mới xuất hiện dày nhất ở đầu sách rồi thưa dần khi dàn nhân vật đã đủ. Con số thật
nằm giữa "một nhúm" và "~50" — và điều đáng nói không phải độ lớn, mà là **mỗi cái trong số đó
hôm nay là một lần dừng cứng cần người gõ tay mới đi tiếp được**.


---

## 2026-09-08 — Cơ chế xuất bản khi không có ai để hỏi

Nửa còn lại của lệnh *"tôi không muốn phải tự nghe, project phải hoạt động toàn bộ cho ra sản
phẩm"*. Thiết kế và số liệu đầy đủ ở
[SHIPPING_WITHOUT_A_LISTENER.md](SHIPPING_WITHOUT_A_LISTENER.md); đây chỉ ghi ba lần bằng chứng
lật ngược thứ tôi định làm, vì đó là phần một người sau tôi cần.

**1. Định làm cơ chế không đụng tới trạng thái đoạn — nó sẽ vô dụng hoàn toàn.**
Tôi cho rằng đoạn chặn mang trạng thái `warning` và chỉ vướng ở *mã cảnh báo*, nên cơ chế chỉ
cần dập mã là đủ, "sạch" hơn. Truy vấn alpha.60: **cả tám đoạn chặn đều `failed`**. Cổng chặn
chương đọc trạng thái, nên cơ chế ấy sẽ chạy đúng, test xanh, và không gỡ được **một chương
nào**. Đo trước khi viết cứu đúng một ngày công.

**2. Định thêm ngưỡng nhịp đọc làm nhân chứng thứ hai — phân bố chồng khít nhau.**
`"Tiếp theo."` dài 1,92 giây là 4,7 ký tự/giây, quá chậm, chắc chạy loạn. Đo 205 đoạn ngắn
`verified` của chính bản ấy: `"Tiếp theo!"` **sạch** nằm ở 4,76; p5 của cả nhóm là 4,76; thấp
nhất `"À!"` ở 1,56. Bất kỳ ngưỡng nào ở đây cũng chỉ là con số tôi bịa. Thay bằng lời tự khai
của bộ sinh (`generation_ceiling_hit`), và nó chia tám đoạn thành đúng 6 cho qua / 2 từ chối.

**3. Chạy thử trên dữ liệu thật lộ ra một khiếm khuyết không test nào của tôi bắt được.**
Cơ chế cấp 13 lượt, nhưng 7 trong đó là đoạn `warning` mang mã vốn **không chặn gì**. Chương
007 và 009 đang xuất bản bình thường sẽ bỗng mang nhãn "3 đoạn chưa ai nghe". Cơ chế vẫn đúng;
cái hỏng là **báo cáo**, và một con số kêu ở chỗ không có gì sai thì lần sau không ai đọc nó
nữa. Thêm điều kiện "chỉ cấp cho đoạn thật sự đang chặn": còn 6 lượt.

### Kết quả đo, không phải dự phóng

Trên tám đoạn chặn của alpha.60: **cho qua 6, từ chối 2**. Hai đoạn bị từ chối (`"Tiếp theo."`
chương 003, `"Gì cơ?"` chương 008) đúng là hai đoạn có `generation_ceiling_hit`, tức đúng hai
đoạn bản vá trần khung vừa cho phép thu lại — cơ chế và bản vá khớp nhau. Số chương còn đoạn
`failed`: **5 → 2**.

Con số 5 → 2 là đo trên bảng dữ liệu cũ. Nó chưa tính bản vá trần khung sẽ làm gì với chương
008 ở lượt chạy mới, nên vẫn phải chạy lại chín chương ấy mới biết kết quả thật.

## 2026-09-09 — Lô vá đòi lại cả bốn chương, và bốn lần tôi tự bác bỏ

**Lô vá xong 4/4.** Chương 000, 003, 007, 016 đều `completed` và `publishable`, nên chương
000..029 đủ 30/30. Ba chứng cứ trên audio thật:

```
patch_edge_fade                  ch003  0,219 → 0,0215     ch016  0,216 → 0,0019
patch_loudness_review_ships      ch000  vẫn lệch 0,62 LU, vẫn ghi cờ, vẫn xuất bản
xuất-bản-không-người-nghe        ch016  'Tôi nhếch mép.' → Whisper nghe 'Tôi nhét mép.'
```

Ca cuối là ca khó nhất cho thiết kế hai bảng, và nó đứng: máy cho qua **có ghi sổ**, còn báo cáo
chương liệt kê đúng đoạn ấy trong `unheard_segments` thay vì nhận là đã có người nghe.

**`patch_pace_relaxed_is_a_decision` thì KHÔNG được chứng minh**, và điều đó phải nói ra: lần
thu mới đọc 14,07 ký tự/giây, vừa qua sàn `fast` 14,0, nên đường nới lỏng không mở lần nào. Một
chương xanh không phải bằng chứng cho một bản vá chưa chạy.

### Nửa giờ tôi suýt đọc thành "treo"

Chương 007 đứng im hơn nửa tiếng với nhịp tim 5 giây. Không phải treo: RAM trống 2,85 GB dưới
sàn 3,5 GB nên bộ điều tiết tắt cả cấp việc GPU lẫn CPU, GPU đo 0% và 4,6 W. Thủ phạm không chỉ
là Unity/Rider của chủ máy — **pool TTS tự giữ 7,63 GB**, và nó định cỡ **chỉ theo VRAM**.
Worker thứ ba là thứ làm cho không worker nào chạy được; hai worker để lại 5,39 GB.

Cách sửa nằm cách hai file: `perceptual_qa.usable_for` đã trừ đúng cái sàn ấy từ lâu, và chú
thích của nó viết đúng câu tôi tự nghĩ ra — *"the pool would size itself into the state that
forbids the work it was built for"*. Hằng số 2,65 GB cũng không phải số mới: theo dõi đỉnh RSS
25 phút bắt được 14 worker TTS ở 2,68 cực đại / 2,57 trung vị, gần trùng phân bố worker cảm thụ.

Ba chương của lô vá còn cho một phép đo thông lượng chỉ dùng số tổng, nên không dính cái nhiễu
đã làm hỏng phép gán theo chế độ:

```
ch016  186 segment / 23,5 phút = 7,91/phút    34% thời gian yield_heavy
ch003  121 segment / 27,0 phút = 4,48/phút    58%
ch007  151 segment / 41,8 phút = 3,61/phút    65%
```

Đơn điệu, biên độ 2,2 lần, và nội suy về 0% cho ~11–12/phút — khớp với 13,13/phút đo trực tiếp
ở chế độ `maximum`.

### Bốn lần phép đo bác bỏ tôi

| tôi định làm | phép đo nói | kết cục |
|---|---|---|
| tài liệu *"Kho giọng nam đã đầy 14/14"* | tô màu đồ thị đồng hiện chỉ cần **7** giọng | đổi tên file, viết lại từ đầu |
| trả giọng miền Trung cho NPC để nới kho | miền Trung sai thanh điệu trên **từ thường** | bỏ đề xuất trước khi viết vá |
| vô hiệu `time.sleep` cho bộ test nhanh hơn | cùng một test: 5,09s → **89,65s** | conftest viết lại thành chỉ **đếm** |
| script chia lô bằng `(n−1)×30` | kế hoạch chia **theo số từ**: lô 3 là 32 chương | đọc dải từ chính bảng kế hoạch |

Cái thứ ba đáng nói nhất vì hàng đợi tối ưu đã đề xuất nó từ hôm trước với lý lẽ rất thuyết
phục. Nó sai vì có **hai loại `time.sleep` trộn lẫn**: ngủ để *nhường lượt* (bỏ được) và ngủ để
*đợi đồng hồ* (bỏ đi thì thành quay tít). Nhìn từ ngoài hai loại giống hệt nhau. Số thật trên cả
bộ: 2.521 test / 519 giây, trong đó 246 giây là ngồi chờ.

Cái thứ tư nguy hiểm nhất vì nó im lặng: nếu không đối chiếu bảng, lô 3 sẽ chạy `060..089`, bỏ
sót hai chương và làm lệch mọi lô còn lại.

### Luật va chạm giọng: hai lần xếp hạng sai trước khi đúng

`port_casting` cũ bỏ pin của **cả hai** người khi họ trùng giọng — đổi hai giọng để chữa một va
chạm, và ở ranh giới lô 1 → lô 2 nó làm sáu nhân vật mất giọng, CHA và NOAH đều là chính.

Lần đầu tôi so số câu trong lô: THEOSBANE im lặng lô ấy nên 0 câu, thua SAMAEL 1 câu — đúng lỗ
hổng một bài test khác đang canh. Lần hai tôi xếp "có pin" lên trên: `SỐ BA` (phụ, 2 câu) thắng
`CHA` (chính, 4 câu), vì không có cột nào phân biệt pin của **người** với pin của **script**
(`locked=1` đánh dấu giới tính, không phải giọng). Thứ đúng là `mention_count` — cộng dồn qua
các lô, nên nó xấp xỉ được người nghe đã quen giọng ấy tới mức nào. Kết quả: **ba** người bị đúc
lại thay vì sáu, và cả ba là người ít lời hơn trong cặp.

### Việc đã làm và đang chạy

Hai bản vá tài nguyên vào cây ở ranh giới (`bda3283`), tag `v0.2.0-lo02`, và **lô 2 (030..059,
3.762 segment) đang chạy**. Bốn script mới: `voice_pool_pressure.py`, `throttle_report.py`,
`assemble_book.py`, `launch_batch.sh`.

Chương 000..029 đã ghép thành `D:/Novels/Audiobooks/_book` kèm `manifest.json` ghi gốc gác từng
chương — và chính `assemble_book.py` bắt được một lỗi im lặng lúc lô vá chưa xong: chương 016
khi ấy rơi về `alpha.56`, chín phiên bản trước, với dàn giọng khác.


## 2026-09-10 (tối) — Bản vá thứ ba, một tuyên bố sai về thứ tự, và một ranh giới không cần người

**Lô 3** đang chạy: 14/32 chương xong lúc 18:48, 1.405 segment có audio lúc 18:29, nhịp tim
sống. Không có gì để nghe, nên tối nay là chuẩn bị cho ranh giới.

**`patch_stray_surname_is_the_same_name`** xếp thứ ba vào hàng chờ (6b5c976). ALICE 25 câu còn
có ALICE DRACEN (0) và ALICE VIC. DRAKEN (1); SELNE 32 còn có SELNE VALKRYN (3). Gộp khi bản dài
≤ 3 câu **và** bản ngắn ≥ 10×; JAKE 300 / JAKE SMITH 30 là bài giữ. Docstring đầu tiên nói "áp
thứ tự nào cũng được" — sai: áp nó trước là bản rơi dấu trượt neo. Thu hẹp neo, đo lại hai thứ
tự trên hai bản sao: cùng một `character_registry.py` byte-một, 52 bài xanh cả hai. Tuyên bố
độc lập không phải phép đo.

**Ranh giới lô 3 → 4 tự chạy.** `scripts/boundary.sh 3 --recast 062 066 071 084 086` được thả
tối nay, đợi lô xong rồi làm năm việc tới khi lô 4 chạy. Để nó chạy không người, ba thứ phải
đổi — ghi ở [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md): `apply_all` tự rút hàng chờ trước
bộ test; project đúc lại nối đuôi và lô sau gieo từ cái cuối (`seed_chain.py`, sổ đi theo
chuỗi, mỗi chương đếm một lần); và "mới nhất" theo `book.created_at` vì `ls -dt` xếp lô 2 trước
ba project vá của nó. Bộ test đầy đủ xanh sau tất cả.

Dự đoán cho sáng mai, ghi trước để không tự thuyết phục mình sau:

- (a) 062, 084, 086 hết va chạm **không nhờ đúc lại** mà nhờ gộp tên — THU LÃNH về THỦ LÃNH,
  SELNE VALKRYN về SELNE — nên chúng **không** chứng minh bản vá quay vòng;
- (b) chỉ 066/071 (KANG + SAMAEL, hai người thật) cần một giọng mới, và đó là chỗ duy nhất
  `patch_wrap_prefers_a_stranger` được thử;
- (c) lô 4 sẽ thấy KANG mang đúng giọng ấy, không phải giọng thứ ba — nếu chuỗi gieo làm việc.

**Thêm lúc 19:55 — chương 075 và thước nhịp lệch lần thứ hai.** Chương hỏng đầu tiên của lô 3
mất một câu dẫn 38 ký tự 10/10 lần ở 10,6–11,8 chars/s; không chia được, dải đã `normal`. Đếm
lại: câu có 2,25 chữ/từ (kho 3,33), và theo âm tiết nó đọc 4,48/giây, gần trung vị kho 4,67 —
cùng họ với lỗi chữ số, thước đếm sai cái nó nhận là đếm. 22 segment của lô 3 chạm sàn, ~38
lần sinh thừa, quá nửa phía chậm là câu từ ngắn. `patch_pace_counts_syllables_too` (thứ tư
trong hàng chờ): chỉ chậm khi chậm theo **cả** chữ lẫn âm tiết, sàn âm tiết 3,75 = p2 của 8.301
bản thu đã qua. Ranh giới tự chạy sẽ áp nó trước lô vá, và chương 075 chạy lại là phép thử —
phải qua lần đầu. Diễn tập ranh giới trên bản sao đủ bố cục: ba bản vá áp, hàng chờ tự rút,
bộ test xanh, mã 0. `plan_repair_batch` giờ ghi "SEGMENT_FAILED — speech pace N chars/s" thay
vì chỉ `SEGMENT_FAILED`, để log ranh giới đọc được nguyên nhân mà không phải mở SQLite.

**Thêm lúc 21:30 — 170 cờ neo tên mỗi lô, và chỉ một là lỗi thật.** Lô 3 gắn cờ 147
`ASR_LOCKED_NAME_ANCHOR_REVIEW` + 23 `_MISMATCH`, cả hai không chặn chương, nên chúng đi qua mà
không ai nhìn. Đo hết 3.923 phép kiểm neo (`scripts/name_is_read_the_same_way.py`) và tách hai
câu hỏi vốn bị trộn: *"có thoả cổng"* khác *"có được đọc giống nhau mỗi lần"*. Phần lớn là cổng
đếm chính tả của Whisper — `Awakened` đọc **giống nhau 66/66 lần** mà trượt 68 lần. Nhưng
`Jake → Giếch` là lỗi thật: **1.827 neo qua cả ba lô, 0% khớp ở cả ba, 89 dạng đọc**, và cùng
một câu ra `Giật` rồi `Dịch`. Giá sửa hẳn: đọc lại 182 đoạn trên 18 chương. Ghi ở
[A_NAME_READ_MANY_WAYS.md](A_NAME_READ_MANY_WAYS.md).

Một giả thuyết của tôi bị bác trong lúc đo: dạng đọc chèm âm `ờ` trượt cổng 2,4% so với 27,4%
nhưng **đọc ổn định ngang** (đỉnh 50,0% so với 51,9%) — chúng chỉ không bao giờ thoả cổng, và ca
xấu nhất (`Giếch`) không chèm âm nào. Bài học cũ, hình dạng cũ: tôi gán cho giọng đọc một lỗi
thuộc về phép đo.

## 2026-09-11 (khuya) — Ranh giới tự chạy xong, và câu ngược chưa ai hỏi

**Ranh giới lô 3 → 4 chạy hết chuỗi không ai ngồi cạnh** (21:12 → 23:24): áp bốn bản vá, commit,
tag, lô vá 075, đúc lại năm chương, đo va chạm, khởi động lô 4, ghép sách. Chương 075 xuất bản
được nên lô 3 thành **32/32**. Cuốn sách từ 60 lên **92 chương, 1,4 GB**.

**Bản vá nhịp được chứng minh trên audio thật**: đoạn từng chết 11 lần giờ qua ở lần thử **đầu
tiên**, tại 10,64 kt/s — con số *thấp nhất* trong cả mười lần trước, nên sàn cũ chắc chắn sẽ bắn.
Cùng một con số, quyết định khác.

**Bản vá quay vòng chạy đúng một nửa.** KANG dùng chung bậc của VIKTOR — người không có trong
chương 071 — đúng việc nó được viết ra để làm. Rồi `holders` chỉ nhớ người giữ **đầu tiên** nên
NPC kế tiếp đọc bậc ấy thành "người lạ" và xếp vào đúng chỗ KANG vừa chiếm.

**Ba lỗi của chính tôi, tìm ra bằng cách chạy thứ mình vừa viết:**

1. Bộ đếm âm tiết (thêm lúc 21:19) tách theo khoảng trắng, nên `I-xờ-hờ-ta-ra` đếm 1 thay vì 5 —
   **chương 084 mất vì nó, bốn tiếng sau**. Docstring của tôi gọi việc đếm thiếu là "chiều sai an
   toàn"; an toàn trước việc *tha nhầm*, không an toàn trước việc *chặn nhầm*, và chặn nhầm thì
   mất cả chương.
2. `prove_a_patch` gọi một chương còn `verifying` là "VẪN CHẶN" — trộn *chưa xong* với *hỏng*.
3. `boundary.sh` gọi `assemble_book` **không có `--apply`**, nên nó ghi "đã ghép sách" cho một
   lượt thử và cuốn sách đứng ở 60 chương suốt.

Và một phép đo sai: tôi tra thang formant bằng slug `preset_thanh_binh` trong khi tên catalog là
`Thanh Bình`; slug rơi vào đường mặc định không kẹp nên tôi kết luận "còn một bậc trống" và suýt
báo rằng bản vá không được thử. Tra một bảng bằng một cái khoá bịa ra thì nó vẫn trả lời.

**Việc lớn nhất tìm được trong đêm** là câu chưa ai hỏi: `voice_pool_pressure` hỏi *hai người một
giọng*, còn *một người hai giọng* thì không công cụ nào hỏi. Đo trên sách: **21 chương, 202 câu
thoại**, một người nói hai giọng ngay trong cùng chương — chương 060 có THỦ LÃNH nói 7 câu giọng
này, 5 câu giọng kia. Mọi cổng xanh vì `verify_casting` thấy **hai** người. Lớp tách danh tính do
rơi dấu không chỉ ăn chỗ trong kho giọng; nó đã đi vào audio, và hôm qua tôi chỉ đo nửa đầu.

## 2026-09-11 (sáng) — Ranh giới chết theo phiên, và bản vá đổi hình dạng lỗi

Lô 4 xong **25/27** (097, 106 hỏng — cùng nhãn `speech pace`, hai ca khác nhau). Ranh giới tự
chạy áp ba bản vá, vá 097 (**qua ngay lần đầu** ở 10,74 kt/s — dự đoán đúng), không cứu 106
(dự đoán đúng), đúc lại 104 (0 va chạm), rồi **chết lúc 08:45 vì phiên Claude Code thoát** — giữa
lúc đúc lại chương 007. Lô 007 tự nó vẫn chạy tiếp (supervisor riêng), đủ 151/151.

Sáu tiếng heartbeat không nổ (01:01 → 07:03), rồi phiên thoát. Chủ sách hỏi hai lần. Từ giờ
nhịp 30 phút và luôn có một waiter nền song song với wakeup.

Làm trong buổi sáng: `boundary.sh` chạy lại được (bỏ qua việc đã xong, đợi GPU, nối `SEED` qua
mọi bước, `launch_batch.sh --seed-from`); phát hiện `NGUOI_TRA_LOI` — bản vá gộp rơi dấu làm
Ollama đổi sang gạch dưới, 45 câu trong 4 project, một người hai giọng ngay trong chương 104
vừa đúc lại; bản vá `identity_key` xếp hàng chờ, 78 bài xanh trên bản sao. Dừng 007 đang dở (nó
mang lỗi ấy) để ranh giới chạy lại đúc nó dưới bản vá.

## 2026-09-11 (chiều) — Chuỗi tám tiếng rưỡi không người, và câu ngược về 0

Ranh giới lô 4 → 5 chạy lại xong lúc 17:40: 24 chương đúc lại, tất cả một giọng một người; lô 5
khởi động gieo từ cuối chuỗi; sách 118 chương. **`one_person_one_voice` trên sách: 0** — hôm qua
21 chương, 202 câu. Ba bản vá được chứng minh trên audio thật trong ngày: âm tiết nối gạch (097
qua lần đầu), gạch dưới (097 vá lại 37 câu một giọng; 104b), và đúc lại giọng (060 về giọng đa
số).

Lỗi tự tìm ra bằng cách chạy thứ mình viết: tên project là địa chỉ nội dung nên lần thứ hai mở
lại project cũ và `run` từ chối trong im lặng (sửa: hậu tố `b`, in lỗi); `!` ép cả bước 3 (sửa:
chỉ bước đúc lại); công cụ đếm giọng đọc cả bản bị bỏ cùng thư mục (sửa: đọc đúng project trong
manifest); sổ cộng dồn ghi vào phần tử cuối chuỗi thay vì project gieo (sửa: gieo luôn đứng
cuối). Một kết luận sai được rút lại cùng buổi: giết `launch_repair.sh` **không** giết lượt chạy.

Phát hiện lớn nhất: **48% đoạn được sửa trong sách đọc tên theo chữ viết** thay vì cách đọc
ghim, cả 348 bản đọc-ghim thua chỉ vì bài chính tả neo tên, WAV còn. Đặc tả bản vá đã ghi, áp ở
ranh giới lô 5 → 6; viết và thử trên bản sao trong lúc lô 5 chạy.

## 2026-09-11, 17:50–18:45 — giữ cách đọc ghim: viết, thử trên bản sao, xếp hàng

Bản vá `patch_keep_the_locked_reading` xong và thử trên bản sao của `lo03r_084b` (bài thử chép
project thật vào thư mục tạm — đồ thị ứng viên với đủ provenance không dựng tay được). Ba lần
bài thử ấy bắt lỗi thiết kế: CAS cuối của `promote_segment_candidate` so với đương nhiệm cũ
(sửa: so với đương nhiệm hiện tại, tự hạ anh em đọc-theo-chữ-viết trong cùng giao dịch, ràng
buộc CHECK đòi `promoted_at IS NULL`); CAS trạng thái ứng viên so với hằng số `dual_passed` —
và nhờ thế thấy đường "bản hoàn chỉnh thắng bản bị cắt" có sẵn chưa từng chạy thật, 0 dòng sổ
trên 47 project (sửa: so với trạng thái đã đọc); `_validated_promoted_candidate_conn` ném cho
bản vừa giữ cách đọc ghim (sửa: đọc lý do từ dòng check cuối). Rồi `test_no_new_blind_compound_
check_is_added` bắt thêm một `if` ba mệnh đề — đổi sang `require_all`.

Lượt đề cử lại cho 348 đoạn đã lên sách: `scripts/keep_the_locked_reading.py`. Thử đầu gọi
`_process_chapter` và nó nạp Whisper: chương 084 mang `Selene Valkryn.` `failed` được máy cấp
phép, bước tổng hợp đặt lại thành `signal_passed`. Tách đuôi của `_process_chapter` thành
`_publish_verified_chapter` (cắt đúng văn bản, hai người gọi). Bài học thứ hai: chính sách chất
lượng mang `implementation_hash`, nên phải ghép lại chương dưới chính sách *của project*, không
phải của cây mã. Kết quả: 10/10 đoạn, 38 giây, `cli validate` qua. Bộ test đầy đủ xanh trên cây
đã vá (trừ `test_doctor…` chỉ hỏng vì cây tạm không có `runtime/models`). Xếp vào `ORDER`, bước
6b của ranh giới. Lô 5 đang phân tích: 816/3.720 lúc 18:34, ~15 đoạn/phút.

Lượt thử chỉ-đọc trên cả sách (18:50) đếm 1.127 đoạn, không phải 348, và ép script thêm hai
luật: chỉ chương manifest ghi (33 chương đã bị bản đúc lại thay — ghép lại chúng là để chương
cũ đoạt lại chỗ trong sách, vì `assemble_book` chọn `completed_at` mới nhất) và chỉ đoạn đang
phát bản đọc-theo-chữ-viết (411 đoạn vẫn phát bản gốc: không có bằng chứng xếp hạng). Còn lại
**452 đoạn trong 102 chương**, ~70 phút ở bước 6b.

## 2026-09-11, 18:55–19:05 — chương 106 chết vì "123456" đếm là một âm tiết

Sau khi lượt đề cử lại xếp hàng xong, nhìn lại chương 106 (lô 4, chưa có bản nào trong sách):
đúng **một** đoạn hỏng, 10/10 lần ở 12,35 kt/s — sàn 12,5, thiếu 0,15 — và thước âm tiết cũng
gọi nó chậm (~3,0 at/s). Câu chứa "password", "123456", "qwerty1234": `123456` đếm sáu ký tự và
một âm tiết vì `vietnamese_number_words` dừng ở 999 và bộ đếm âm tiết không nở số. Viết
`patch_a_number_is_read_in_full`: đọc trọn vẹn tới dưới 10^12 theo ngữ pháp số đếm; thước nhịp
lấy cận dưới của hai cách đọc cho dãy từ 1000; `spoken_syllables` đếm trên văn bản đã nở số.
Đoạn ấy đo lại 88 ký tự / 26 âm tiết — giữa dải. ASR không đổi. Xếp hàng sau bản vá giữ cách
đọc ghim; ranh giới 5 → 6 thả bằng `--recast auto 4:106` thay vì `--skip 106`.

Bộ test đầy đủ trên cây tạm có cả hai bản vá bắt thêm một bẫy không thuộc bản vá nào:
`retire_queue` (apply_all) tìm dấu `)` đứng riêng một dòng để kết thúc `ORDER`, nên với hàng chờ
MỘT tên viết gọn `("patch_x.py",)` nó nhảy tới dấu đóng của `APPLIED` và ghi ra một file không
import được — đúng dạng cây thật mang lúc 18:35, và ranh giới tự chạy không có ai sửa tay. Đổi
sang tìm phép gán bằng `ast`; thêm bài thử tuple một dòng. Hai bài cũ ghim "số > 999 để nguyên"
đổi theo bản vá số.

## 2026-09-11, 23:12 (giờ thật) — đồng hồ máy chạy chậm 4 giờ 17 phút cả ngày, vừa được chỉnh

Nhật ký hệ thống (Kernel-General, Id 1): 23:12:55 đồng hồ nhảy từ 11:56:06Z lên 16:12:55Z —
**+4 h 16 m 49 s**, lý do 2 (đồng bộ giờ). Header `Date` của một request HTTPS khớp giờ MỚI. Nghĩa
là mọi mốc giờ ghi hôm nay trước lúc ấy — `completed_at`, `created_at`, sổ chất lượng, giờ
commit git (45d0f1e "18:39", e8a7c0a "18:44"), và mọi con số giờ trong các ghi chú ở trên — đều
**sớm hơn giờ thật 4 h 17 m**, nhưng nhất quán với nhau. Nhảy TIẾN nên thứ tự không đảo:
`assemble_book` chọn bản `completed_at` mới nhất và `seed_chain` xếp theo `book.created_at` vẫn
đúng; nhịp tim lease chỉ trông "chết" trong đúng một khoảng ghi. Lô 5 đi tiếp không gián đoạn
(1.143 đoạn phân tích lúc 23:14, 1.214 lúc 23:19 — cùng nhịp ~15 đoạn/phút như trước). Nếu có
lúc nào đồng hồ bị chỉnh LÙI thì mới nguy: "mới nhất" và "còn sống" đều so bằng giờ tường.
Dấu vết duy nhất của cú nhảy trong lô: 23:14:18 `ANALYSIS_CRITIC_TRANSPORT_FAULT` — một request
Ollama "Read timed out" ngay khi hạn chót tính theo giờ tường nhảy qua; thử lại sau 2 giây và
được chấp nhận. Đúng kiểu lỗi mà đường thử lại có sẵn để nuốt.

Cùng nhật ký ấy còn cho thấy lý do lô 5 chậm lại vài phút quanh "18:49–18:51": governor báo
`yield_heavy — foreground CPU 102%` — bộ test và ffmpeg của tôi chạy dưới cửa sổ đang có focus,
nên bị coi là việc tiền cảnh và lô nhường máy cho chúng (`THE_MACHINE_IS_SHARED.md`).

## 2026-09-11, 23:27 (giờ thật) — thả ranh giới lô 5 → 6

Bộ test đầy đủ xanh trên cây tạm mang cả hai bản vá; commit 3288b1e; cây sạch. Thả
`bash scripts/boundary.sh 5 --recast auto 4:106` — chờ bước 0 cho lô 5 xong (1.237/3.720 đoạn phân
tích lúc 23:22, ~15 đoạn/phút → phân tích xong ~02:10, rồi tổng hợp và phiên nhiều giờ). Bước 1 áp
hai bản vá và chạy bộ test trên cây thật; 4b đúc lại 106 dưới mã mới; 6b đề cử lại 452 đoạn của
102 chương đã lên sách; 7 ghép sách. Đếm tiến trình: một ranh giới là HAI bash (lớp bọc của harness
+ script) — nhịp tim đếm dòng lệnh `bash.exe" scripts/boundary.sh`, không đếm lớp bọc.

## 2026-09-11, 23:33 (giờ thật) — thả lại ranh giới với chín chương di sản của lớp rơi dấu

Trong lúc chờ lô 5, đọc phần "qua các chương" của `one_person_one_voice.py`: **12 người mang hơn
một giọng qua cả sách**. Hai cái tên đứng đầu là hai vai nói nhiều nhất cuốn sách:

    NGƯỜI TRẢ LỜI   90 chương doan_trang_f100 · 6 chương ngoc_linh_f108 (031 043 053 055 081 089) · 1 chương f115 (056)
    THỦ LÃNH        83 chương thanh_binh_f100_p-07 · 7 chương thanh_binh_f090_p-04 (031 043 053 055 072 080 081)

Truy từng chương: giọng thứ hai luôn nằm ở dòng `characters` viết **rơi dấu** — `NGUOI TRA LOI`,
`THU LÃNH` — trong những project đúc trước `patch_dropped_marks_are_the_same_name` (ranh giới
3 → 4): lô 2, các lần vá lô 2 (`lo02v_031`, `lo02r_056`), lô 3. Cùng lớp lỗi đã đo 21 chương
"một người hai giọng trong cùng chương"; đây là mặt còn lại của nó — trong mỗi chương ấy chỉ có
một giọng, nhưng là giọng khác 83–90 chương kia. Người nghe mất hai nhân vật xuyên suốt ở chín
chương. Mã hiện tại gộp tên nên đúc lại là hết: cast lại ports `NGƯỜI TRẢ LỜI` → doan_trang_f100.

Ranh giới đang chờ ở bước 0, chưa làm gì, nên dừng nó (taskkill ba tiến trình bash) và thả lại
với `--recast auto 2:031 2:043 2:053 2:055 2:056! 3:072 3:080 3:081 3:089 4:106` (056 cần `!` vì
`lo02r_056` đã hoàn thành). Giá: ~10 chương × 25 phút GPU ở bước 4b, trước khi lô 6 khởi động.
Thứ đổi lấy là hai vai chính của cả cuốn sách chỉ còn một giọng mỗi vai.

Chưa động tới: KANG (8 chương f100, 5 chương f093 — hai bản đúc lại `lo03r_090/091` mang f093 và
lô 5 gieo từ `lo03r_091`, nên lô 5 có thể thêm f093; quyết sau khi lô 5 xong, phía ít hơn sẽ
đúc lại), và mười cái tên 1–3 chương. Sổ `character_exposure` trong lô 5 là bản cũ 21 tên
(NGƯỞI TRẢ LỞI 320 thay vì 955, KANG không có) — KANG đụng giọng trong lô 5 sẽ là người nhường.
Không sửa DB của lô đang bay; ghi để kiểm sau. Việc dài hơi ghi ở OPTIMISATION_QUEUE.

Viết luôn chế độ `one_person_one_voice.py --across [--min-chapters 5]` (23:40): in `B:NNN` cho những
chương mang giọng thiểu số của người có đủ chương, lô tra từ manifest. Trên sách thật nó đề nghị 16
chương: chín chương trên, cộng 051 và 054 (THALIA ba giọng trong sáu chương, WILLEM một chương lệch)
và năm chương f093 của KANG. Nhận 051 + 054 (thêm ~50 phút GPU), **hoãn KANG**: lô 5 gieo từ phía
f093 nên "đa số" của KANG có thể đổi chiều sau lô 5 — đúc lại bây giờ là đúc lại có thể sai chiều.
Dừng và thả lại ranh giới lần ba (vẫn ở bước 0):
`--recast auto 2:031 2:043 2:051 2:053 2:054! 2:055 2:056! 3:072 3:080 3:081 3:089 4:106` — 054 và
056 cần `!` vì `lo02r_054/056` đã hoàn thành. Nối `--across` vào `boundary.sh --recast auto` để ở
điểm yên tĩnh kế (không sửa script đang chạy).

Một bẫy nữa của bước 6b, thấy khi nhìn thứ tự các bước: 4b đúc lại 031 043 … xong rồi 6b mới
chạy, mà `--book` đọc manifest của lần ghép TRƯỚC — vẫn trỏ về `lo02v_031` cũ. Ghép lại chương cũ
ấy là đóng cho nó `completed_at` mới hơn bản đúc lại vừa xong, và bước 7 lấy nhầm chương cũ.
`shipped_projects()` giờ hỏi thẳng câu bước 7 hỏi (`assemble_book._candidates`: bản `completed` có
MP3, mới nhất thắng) thay vì đọc manifest; hai bài thử ở `tests/test_keep_the_locked_reading_
targets.py`. Ranh giới đang chờ không cần thả lại: script được đọc lúc bước 6b gọi.

## 2026-09-12, 00:20–00:50 — bước 6b có thể gỡ một chương khỏi sách; sửa trước khi nó chạy

Chủ sách chuyển sang Opus 5 và nạp tài liệu workflow. Lệnh vĩnh viễn "cấm chia subagent" vẫn
đứng cho tới khi có câu cho phép rõ ràng, nên vẫn tự làm trong vòng lặp chính (và lúc này fan-out
còn làm governor nhường máy, làm chậm lô 5 — đo 18:49–18:51 hôm qua).

Đọc lại thứ tự các bước của ranh giới và tìm ra một lỗ: `reassemble` của bước 6b đặt chương sang
`verifying` rồi ghép; mọi đường lỗi để nó ở `verifying`/`failed`, mà `assemble_book` chỉ nhận
`completed` — nên một chương **đang trong sách** sẽ rơi ra, im lặng, và một ngoại lệ không phải
`AudioQualityError` còn giết cả vòng `--book`. Sửa: chụp ảnh trạng thái đã lên sách (chương +
artifact) rồi mới đánh dấu hết hiệu lực, bắt mọi ngoại lệ, thất bại thì đặt lại đúng ảnh ấy và nói
ra; `main()` bọc từng project. Bài thử bắt được lỗi của bản sửa đầu (ảnh chụp sau khi đã đánh dấu
→ "khôi phục" về `verified=0`). Chứng minh trên hai bản sao `lo03r_084b`, một bản bị trỏ nguồn sang
file không tồn tại: chương giữ `completed` + mốc cũ + artifact cũ + MP3 cũ, 9 đoạn đề cử lại vẫn
giữ, `assemble_book` vẫn thấy nó. Chi tiết và bảng đo ở `KEEP_THE_LOCKED_READING.md`.

Lô 5: 2.152/3.720 đoạn phân tích lúc 00:19, nhịp ~16 đoạn/phút, lease sống, không lần nhường máy
nào trong 30 phút. Ranh giới vẫn chờ ở bước 0 với đúng một tiến trình script.

## 2026-09-12, 01:00–01:20 — bản vá thứ ba: một đoạn một bản được đề cử, và một cách thất bại

Việc sửa CAS trạng thái ứng viên (bản vá thứ nhất) làm đường `over_a_cut_off_incumbent` chạy được
lần đầu kể từ khi nó được viết — 0 dòng `machine_take_substitutions` trên 47 project lô là bằng
chứng nó chưa từng đi qua. Một đường vừa được mở thì phải đọc nó như đọc mã mới, và nó mang hai
chỗ hở:

- **Hai bản `promoted` cho một đoạn.** Việc hạ bản `promoted` cũ chỉ chạy khi giữ cách đọc ghim.
  Đường cut-off không hạ gì, nên nếu đương nhiệm của đoạn lại là một ứng viên đã được đề cử vòng
  trước thì sau khi thay sẽ có hai dòng `promoted`, và `segment_candidate_resume_plan` ném ở lần
  ĐỌC sau — lúc resume hoặc lúc lắp ráp chương, xa chỗ gây ra lỗi. Bốn điều kiện của
  `_require_candidate_beats_a_cut_off_incumbent` không nói gì về việc đương nhiệm là ai.
  Sửa: hạ vô điều kiện, nên bất biến phát biểu được thành một câu — *một đoạn, nhiều nhất một
  ứng viên `promoted`* — và nó đúng cho cả ba đường thăng hạng. Đường thường khớp 0 dòng.
- **Một ngoại lệ giết cả chương**, đúng hình dạng đã sửa cho `_keep_the_locked_reading` ba mươi
  phút trước: `_segment_candidate_item` ném thật khi checksum văn bản đọc trôi.

Bài thử kiểm bất biến trên cả project thật sau khi đề cử lại (mọi đoạn: đúng một bản `promoted`,
và `segment_candidate_resume_plan` dựng được cho từng đoạn), và kiểm lớp bọc bằng cách cho hàm tìm
ném thật. Ba bản vá áp theo thứ tự trên một cây sạch: ok, 8 bài của hai file mới xanh.

Rồi tự hỏi bản vá số có mở ra cách trượt nào mới không: nở chữ số làm ký tự TĂNG, mà cận trên của
thước nhịp không xét âm tiết — một câu dày chữ số đọc nhanh có thể vượt trần 24,5 kt/s. Đo trên
321 đoạn có chữ số của các project lô, bằng chính `chars_per_second` đã lưu và dải nhịp trong
settings của từng project: 217 đoạn đổi số đếm, **0 bị gắn cờ mới, 0 được tha thêm**, biên lùi xa
trần nhỏ nhất là 2,1 kt/s. Không hồi quy, nhưng biên mỏng — ghi vào hàng chờ kèm cách chữa nếu
ngày nào nó bật: cho cận trên xét cả âm tiết, đừng nới trần.

## 2026-09-12, 00:55–01:25 — một câu chưa ai hỏi: giọng ấy có ĐÚNG không

Hai công cụ đang có đều hỏi về tính nhất quán (`voice_pool_pressure`: hai người chung một giọng;
`one_person_one_voice --across`: một người hai giọng). Không ai hỏi *giọng ấy có đúng không* — và
một cuốn sách hoàn toàn nhất quán vẫn có thể đọc một người đàn ông bằng giọng con gái ở mọi chương.
Viết `scripts/voice_matches_the_person.py` (+ 8 bài thử) để hỏi hai câu: lệch phái, và đổi tuổi
giữa các lô.

Lần đo thô báo 11 dòng / 5 tên, và **cái bẫy nằm ngay đó**: luật giọng trẻ con là có thật và có
chủ ý — preset nam dừng cách ống âm một đứa trẻ 0,8 cm, nên trẻ trai được đọc bằng preset nữ kéo
cao formant/pitch, có đo và có xếp hạng của người nghe trong `voice_catalog`. Trừ luật ấy ra, con
số thật là **1 dòng**: IVAN, `age=unknown`, 17 câu ở chương 062 bằng giọng trẻ con nữ, vì lô 3 gọi
anh ta là `child` một lần và `port_casting` mang `locked_voice_key` ấy sang mọi lô sau. Không có
lệnh nào ghim được tuổi (`cast` chỉ ghim phái), nên đúc lại bây giờ chỉ tốn GPU — đặc tả bản vá
cho ranh giới 6 → 7 đã ghi, kèm điều 3 là điều khó: *một thuộc tính đã ghim phải thắng giọng
ported*, tức chỗ duy nhất "nhất quán" phải nhường "đúng".

Cùng buổi, diễn tập bước 6b ở quy mô thật trên bản sao `lo01b`: 25 chương ghép lại, 0 thất bại,
17 phút 16 giây, project thật không đổi một byte. Diễn tập ấy lại phát hiện lượt này **đưa ba
chương từ `failed` sang `completed`** (003, 007, 016) — `_publish_verified_chapter` xuất bản mọi
chương qua được ba cổng chặn. Nguy vì `completed_at` mới nhất thắng ở bước 7: một chương hỏng cũ
sẽ đoạt chỗ của bản đúc lại vừa xong. Giờ lượt này bỏ qua và nói ra mọi chương không `completed`.
Ước lượng lại cho ranh giới: ~41 giây/chương, tức 1,5–2 giờ cho 102 chương, không phải 70 phút.

## 2026-09-12, 01:30–01:45 — viết bản vá ghim tuổi, và cố ý KHÔNG xếp hàng đêm nay

`patch_a_pinned_person_outranks_a_ported_voice`: cột `locked_age` riêng (+ migration), `cast --age`,
`port_casting` mang thuộc tính đã ghim theo chuỗi gieo, và `_drop_pins_that_contradict_a_person`
bỏ giọng ported khi nó trái thứ người đã ghim. Một luật duy nhất, và là luật duy nhất dữ liệu
chứng minh được: *preset phải đúng phái, trừ trẻ con*. Không bịa luật "giọng trẻ con cho người
lớn": nhìn `voice_key` không phân biệt được preset nữ dành cho một đứa trẻ với preset nữ dành cho
một phụ nữ trưởng thành, và đoán chính là thứ đã tạo ra cả lớp lỗi này.

Không vào `ORDER` đêm nay. Ba bản vá kia đã chứng minh trên dữ liệu thật; đây là tầng casting, nơi
một lỗi hỏng dàn giọng cả lô chứ không hỏng một đoạn. Đợi lô 6 chạy xong rồi xếp ở ranh giới 6 → 7.

Hai lần tự đâm vào bẫy của chính mình trong nửa giờ này, ghi lại vì cả hai đều đã nằm trong bộ
nhớ: (1) dùng `strip().upper()` thay `_character_key` — chính docstring của nó nói hai phép ấy
đồng ý cho "Noah" và khác nhau cho "Lê  Văn  A", tức người nghe ghim được rồi lượt chạy bỏ qua
trong im lặng; (2) viết `
` trong heredoc bash của tool và bị ăn dấu gạch chéo, đúng dòng đã ghi
trong memory. Cách chữa cho (2) vẫn là: script sửa file thì viết bằng Write tool.

## 2026-09-12, 01:50 — KANG: một giả thuyết đẹp, và dữ liệu bác nó

Lô 5 không mang pin nào cho KANG (`locked_voice_key` rỗng), nên casting sắp cấp cho anh ta một
giọng MỚI — giọng thứ ba trên cả sách. Truy ra: ở project gieo `lo03r_091`, KANG dùng
`thanh_binh_f093_p-04` **chung với SAMAEL**, và luật va chạm của `port_casting` bỏ pin của người
ít lời hơn. Giả thuyết đầu của tôi: lỗi là do sổ cộng dồn của lô 5 bị cũ (21 tên, không có KANG),
nên KANG vào cuộc với 0 câu và thua SAMAEL 10-0 — tức chính cái sổ sinh ra để chặn loại lỗi này
lại gây ra nó.

Dựng lại sổ đúng trên 46 project của chuỗi (chỉ đọc, không ghi vào lô đang bay): **62 nhân vật,
117 chương**, và con số quyết định là SAMAEL **152** câu so với KANG **41**. SAMAEL thắng, và
thắng đúng. Giả thuyết sai; sổ cũ không đổi kết quả này. Ghi lại vì một giả thuyết đẹp bị dữ liệu
bác vẫn là kết quả, và vì lần sau tôi sẽ lại nghĩ ra đúng giả thuyết ấy.

Điều còn lại đúng: `f093_p-04` là giọng của SAMAEL, nên 5 chương KANG mang f093 (066, 067, 087,
090, 091) là dấu vết của lớp va chạm cũ (tám người trên một bậc, đã vá), và giọng đúng của KANG là
`f100_p-04` (8 chương). Quyết định sau khi lô 5 khoá dàn giọng: đúc lại 5 chương ấy về f100, trừ
khi lô 5 cấp cho KANG một giọng thứ ba và số chương của nó lớn hơn 8. Sổ của lô 6 sẽ đủ 62 tên
(launcher chạy backfill với luật gieo-đứng-cuối đã sửa).

## 2026-09-12, 01:30–01:40 — cuốn sách đã ghép không tự biết nó là một cuốn

Hỏi một câu về **sản phẩm**, không về đường ống: máy nghe nhạc thấy gì khi mở thư mục `_book`?
Đọc thẻ ID3 của 118 file: `album` **38 giá trị khác nhau**, mỗi giá trị là slug project, và
`track` là số thứ tự trong project nên **36 file cùng mang `track=1`**. Player nào sắp theo thẻ
thì thấy 38 đĩa và trộn thứ tự chương. Không cổng nào bắt được, vì ở tầng một lô thì thẻ ấy đúng
(`book.title` của project chính là slug lô) - chỉ cuốn sách mới là chỗ biết mình là một cuốn.

Sửa trong `assemble_book.py`: ghi lại thẻ bằng `ffmpeg -c copy` (bài thử giải mã trước/sau và so
từng byte PCM), `album` một giá trị, `track` = số chương thật kèm tổng của nguồn. 118 chương trong
11,7 giây. Kiểm sau khi chạy: 1 album, 0 track trùng, 118/118 track khớp số chương, thứ tự tăng
dần. Tên đĩa thật là thứ duy nhất chỉ chủ sách biết (không có ở đâu trong dữ liệu), nên mặc định
là chỗ giữ chỗ và có `--album`.

Bước này ép sửa thêm một luật: "chép khi khác kích thước file đích" không dùng được nữa (ghi thẻ
đổi kích thước → chép lại 2 GB mỗi lần ghép). Giờ hỏi theo gốc gác trong manifest.

Hai câu hỏi phụ, cùng lượt đo, cùng trả lời "không có gì sai": chương 000 chỉ 7,9 giây **không**
bị cắt (nguồn của nó là một mẩu 183 byte về ảnh fan art), và trên 117 chương có nguồn ≥200 ký tự,
tỉ lệ ký-tự-nguồn trên giây audio nằm trong dải **11,4–13,3** quanh trung vị 12,4 - không chương
nào bị cắt hay phình. Giọng người kể cũng một giọng duy nhất (Phạm Tuyên, cùng seed) trên cả 118
chương.

## 2026-09-12, 02:04 — lô 5 khoá dàn giọng: bốn dự đoán, bốn lần đúng, một lần tôi nói chưa chính xác

Lô 5 phân tích xong 3.720 đoạn lúc 02:03 và khoá dàn giọng lúc 02:04 (26 chương, 25 nhân vật đối
thoại). Đây là phép thử của `patch_a_step_remembers_every_holder` ở quy mô thật — lô 4 từng có
**tám** người trên một bậc formant trước bản vá ấy.

| Dự đoán | Kết quả |
|---|---|
| không bậc nào quá 2–3 người | **4 giọng bị dùng chung, nhiều nhất 3 người**, trong đó có NPC |
| không va chạm trong cùng chương | **0/4** va chạm nằm trong cùng một chương |
| một người một giọng trong chương | **0 chương** có một người hai giọng |
| giọng đúng phái/tuổi | **0 dòng** lệch (97 dòng chương × nhân vật × giọng) |
| KANG không có giọng thứ ba | được cấp `thanh_binh_f100_p-04` — **đúng giọng đa số** của anh ta |

Chỗ tôi nói chưa chính xác: dự đoán ghi là "không có dòng `CẢNH BÁO: nhiều nhân vật dùng chung một
giọng` trong runtime_events". Dòng ấy **có** — lúc 02:03:49, liệt kê đúng bốn giọng trên. Nó
không sai: cảnh báo ấy đếm người dùng chung một `voice_profile_id`, không hỏi họ có gặp nhau trong
chương nào không. Câu hỏi có ý nghĩa là câu `voice_pool_pressure` hỏi tiếp — **cùng chương hay
không** — và câu ấy trả về 0. Dự đoán đúng phải là "cảnh báo có thể vẫn in ra, nhưng số va chạm
cùng chương phải là 0", và lần sau tôi viết dự đoán theo con số chứ không theo sự có mặt của một
dòng log.

KANG được cấp đúng giọng đa số nên quyết định đúc lại thành sạch: 5 chương mang giọng của SAMAEL
(066, 067, 087, 090, 091) là thiểu số, đúc lại về `f100_p-04`. Và nó **đáng tin** chứ không phải
xổ số: KANG nói 2 câu trong lô 5 với f100, nên `port_casting` của bước 4b (gieo từ lô 5) sẽ ghim
f100 cho anh ta trước khi chương được đúc lại — SAMAEL đang ở f093 nên không va chạm.

Thả lại ranh giới lần thứ tư (vẫn ở bước 0, lô 5 vừa bắt đầu tổng hợp chương đầu) với danh sách
cuối cùng: **16 chương giọng-thiểu-số + chương 106**, và `EBOOK_COAUTHOR` đặt về Claude Opus 5 để
commit tự động đêm nay ghi đúng người. Danh sách khớp chính xác đầu ra của
`one_person_one_voice.py --across --min-chapters 5`.

## 2026-09-12, 02:25 — hai chương đầu của lô 5, và một phân biệt quan trọng

Lô 5 tổng hợp ~9,5 phút một chương (119 và 120 xong, 121 đang chạy → 26 chương xong khoảng 06:10).
Chương 119 `completed` **với 3 đoạn `failed`**, và cả ba đều là loại máy tự cho qua: hai
`ASR_LOCKED_NAME_ANCHOR_MISMATCH` (Bowden, Aurieth) và một `ASR_MISMATCH_UNRESOLVED`
(`"Wheee! Whooohooo! Booyaaa!"` — ASR không phiên được tiếng reo).

Phân biệt đáng ghi, vì nó đổi cả kỳ vọng cho bước 6b: hai đoạn neo tên ấy **vẫn đang phát bản
gốc**, tức chính cách đọc ghim. Năm ứng viên của mỗi đoạn đều `dual_failed`, không bản nào được
đề cử, nên đương nhiệm chưa bao giờ đổi. Người nghe nghe đúng cách đọc; chỉ ASR là không xác nhận
được. 6b để yên chúng, và đúng như thế.

Lớp **thật sự** hỏng thì đã thấy ngay trong hai chương đầu: **4 ứng viên `source_spelling_v1`
được đề cử** (so với 4 `locked_spoken_v1`). Tức lô 5 vẫn sinh ra tỉ lệ ~50/50 của phát hiện
348/716, vì bản vá chỉ vào cây ở ranh giới **sau** lô 5. Ngoại suy: ~50 đoạn cho 26 chương, và
bước 6b sẽ chữa chúng (nó đọc người thắng theo `completed_at`, nên chương của lô 5 cũng nằm
trong đó) — thêm khoảng 18 phút ffmpeg cho ~26 chương của lô 5.

Lô 6 mới là phép thử thật của bản vá giữ cách đọc ghim: ở đó móc chạy **trong** vòng sửa và con
số `source_spelling_v1` được đề cử phải về gần 0.

## 2026-09-12, 02:40–02:56 — câu hỏi thứ năm về giọng, và một phép đo tôi phải làm lại

`voice_pool_pressure` hỏi va chạm **trong một chương của một lô**. Câu chưa ai hỏi: trên **cả
cuốn sách**, có hai người nào dùng chung một giọng không, và họ có bao giờ cùng nói trong một
chương không? Đo trên 118 chương (451 dòng chương × nhân vật × giọng, 61 tên):

    92  cặp hai người dùng chung một giọng
     1  cặp CÙNG CHƯƠNG: `thai_son_f093_p+00` — SỐ BỐN và SỐ NĂM, chương 023
     2  cặp mà cả hai đều ≥5 chương với giọng ấy (không bao giờ cùng chương):
        SAMAEL (29ch) + KANG (5ch) trên f093 · KANG (8ch) + BOWDEN (6ch) trên f100

**Phép đo đầu của tôi sai và tôi phải làm lại.** Bản đầu giao hai tập "chương mà người ấy có
mặt", nên nó báo NGƯỜI TRẢ LỜI và THALIA "cùng chương" ở sáu chương — trong khi hai người chỉ
dùng chung giọng `f115` ở **hai chương khác nhau** (056 và 054) và ở sáu chương kia mỗi người
mang giọng riêng. Câu đúng là giao hai tập "chương mà người ấy dùng **chính giọng ấy**". Sau khi
sửa: 6 cặp giả biến mất, còn đúng một cặp thật. Ghi lại vì con số sai ấy suýt vào báo cáo, và vì
nó là cùng một lớp lỗi với `one_person_one_voice` trước khi gộp tên — **giao đúng hai tập mới là
câu hỏi**.

Cặp cùng chương duy nhất ấy **chính công cụ của dự án đã báo từ lô 1**: `voice_pool_pressure` trên
`lo01b` in "CÙNG CHƯƠNG 023 — người nghe lẫn". Nó chưa từng được đúc lại, vì ranh giới lô 1 → 2
chưa có `--recast auto`. Giờ thêm `1:023` vào ranh giới: 25 phút GPU để cuốn sách không còn va
chạm cùng chương nào mà ta biết mà vẫn để đó.

Hai cặp còn lại là **tái dùng bình thường của một pool hữu hạn** (14 preset × 7 bậc formant cho 61
cái tên) và không bao giờ gặp nhau trong một chương. Nhưng đáng ghi một điều về kế hoạch KANG: đúc
lại 5 chương f093 của anh ta về f100 **không giảm** việc dùng chung qua sách, nó **chuyển** —
KANG(13) + BOWDEN(6) trên f100 thay vì SAMAEL(29) + KANG(5) trên f093. Vẫn nên làm, vì mục tiêu là
KANG có MỘT giọng (người nghe không mất nhân vật), không phải giảm tổng số cặp.

Danh sách đúc lại cuối cùng của ranh giới: **18 chương** (1:023 · 2:031 043 051 053 054! 055 056! ·
3:066 067 072 080 081 087 089 090 091 · 4:106), khoảng 7,5 giờ GPU ở bước 4b.

## 2026-09-12, 03:25–03:45 — đi tìm gốc rễ, và tìm thấy tài liệu của chính dự án đã ở đó

Nối tiếp câu hỏi thứ năm: nếu 92 cặp dùng chung giọng là do **pool hết chỗ**, thì đúc lại vô
nghĩa và câu đúng là mở rộng pool. Đo ba bước:

1. **26 trong 61 người đã nói trong sách KHÔNG có pin giọng** trong lô 5 — KANG dẫn đầu (13
   chương, 41 câu). Mỗi lô sau là một lần rút thăm lại giọng của họ. Viết
   `scripts/pin_the_book_cast.py` để ghim theo **giọng đa số trên cả sách** (nguồn: cuốn sách đã
   ghép, chứ không phải một project gieo), chỉ thêm cho người chưa có pin, và giải quyết va chạm
   bằng luật "nhiều chương hơn thì giữ".
2. Lượt thử của nó lộ ra thứ khác: **5 người được ghim mà im lặng trong lô 5 đã bị người khác
   lấy slot** (BOWDEN → KANG, JAKE → VINCE + REINER, ALVARA → REVISIA, TIS → LIA, VALE → LEON +
   AARAV). Tưởng là lỗ trong `reserve_pinned_voices`, nhưng đọc mã thì nó giữ chỗ đúng cho cả
   người im lặng; thật ra **ladder của preset ấy đã cạn** nên `_first_free_variant` buộc phải
   chia, và nó chia cho người ít chương chung nhất — đúng luật của nó.
3. Vậy pool có hết chỗ không? Kho dùng được cho nhân vật: **nam đúng 2 preset × 7 bậc = 14 slot**
   (cả hai preset đều bị đánh dấu "giáng cấp", mà chẳng còn gì ở trên), nữ 4 preset = 27 slot.
   39 nhân vật nam trên 14 slot.

**Và đây là chỗ tài liệu của dự án đã đứng sẵn.** `TWO_CHARACTERS_ONE_VOICE.md` đi đúng con đường
này ở lô 1, đặt tên file là "Kho giọng nam đã đầy", rồi **tự bác kết luận ấy**: ràng buộc thật là
số người nam nói trong **chương đông nhất**, vì người nghe nghe từng chương một. Đo lại ở quy mô
sách: chương đông nhất có **7** người nam (kho 14) và **5** người nữ (kho 27). Vẫn còn chỗ gấp đôi.

Nên tôi **không** mở rộng pool, và ghi rõ lý do vào hàng chờ để người sau không mở lại vụ này:
hai trong ba cửa mở ra dẫn tới lỗi phát âm thật — giọng miền Trung đọc sai thanh điệu trên từ
thường ("khốn kiếp" → "khôn kiêp", thanh điệu mang nghĩa), giọng tin tức sai văn phong — còn cửa
thứ ba (Xuân Vĩnh) đã bị một người nghe Việt phán.

`pin_the_book_cast.py` vẫn giữ: nó chữa đúng thứ nó chữa (26 người không pin), độc lập với câu
hỏi pool. Nhưng lượt thử cho thấy nó chỉ ghim thêm được **4 người** (KANG, LYLE, SỐ SÁU, SỐ MỘT),
vì luật va chạm nhường slot cho người nhiều chương hơn *đã được ghim*. Thứ tự đúng phải là: tôn
trọng pin đã có trước, rồi mới xét va chạm giữa các đề nghị mới — sửa trước khi dùng thật.

## 2026-09-12, 03:50 — bỏ 5 chương KANG khỏi ranh giới: đúc lại chúng KHÔNG đạt mục tiêu

Trước khi để ranh giới tiêu 2 giờ GPU, tôi truy xem việc đúc lại 5 chương f093 của KANG sẽ cho
anh ta giọng nào. Chuỗi lý luận, đọc từ dữ liệu chứ không từ ý định:

1. Project đúc lại gieo từ lô 5. Ở lô 5, KANG **nói** 2 câu bằng `thanh_binh_f100_p-04`, còn
   BOWDEN **giữ pin** đúng giọng ấy (im lặng cả lô).
2. `port_casting` lấy cả hai (một từ `SPOKE_HERE`, một từ `PINNED`) → **va chạm cùng một
   `voice_key`** → luật "người nhiều lời hơn giữ giọng" xử.
3. Hạng đầu tiên là **sổ cộng dồn**, và launcher chạy `backfill_exposure` trước mỗi lần đúc lại
   nên sổ sẽ đủ 62 tên. Trong sổ đúng: **BOWDEN 68 câu, KANG 41 câu**. BOWDEN giữ f100 — và giữ
   **đúng**.
4. Nên KANG bị bỏ pin, allocator cấp cho anh ta một bậc còn trống → 5 chương ấy nhận **giọng
   thứ ba**, không phải giọng đa số.

Kết quả nếu cứ chạy: KANG vẫn hai giọng (8 chương f100 + 5 chương giọng mới), chỉ khác là 5
chương kia thôi trùng giọng với SAMAEL. Mà theo học thuyết của chính dự án (`TWO_CHARACTERS_ONE_
VOICE.md`) việc trùng giọng **khác chương** không phải lỗi — KANG và SAMAEL không bao giờ nói
cùng một chương trên giọng ấy. Vậy 2 giờ GPU mua một thứ không phải lỗi, và không mua thứ là lỗi
(người nghe mất nhân vật vì KANG đổi giọng giữa sách).

**Bỏ 5 chương ấy.** Danh sách ranh giới còn **13 chương**: `1:023 2:031 2:043 2:051 2:053 2:054!
2:055 2:056! 3:072 3:080 3:081 3:089 4:106`. Mười ba chương này thì đúc lại **có** đạt mục tiêu,
và tôi kiểm bằng pin trong lô 5 trước khi để yên: THỦ LÃNH `thanh_binh_f100_p-07`, NGƯỜI TRẢ LỜI
`doan_trang_f100_p+00`, THALIA `doan_trang_f104_p+00`, WILLEM `thai_son_f104_p+00` — cả bốn pin
đều **chính giọng đa số**, nên port mang pin ấy sang và chương đúc lại sẽ về đúng giọng.

Việc của KANG cần một dụng cụ khác, ghi vào hàng chờ: **ghim anh ta vào một bậc còn trống rồi đúc
lại cả 13 chương** (~5,5 giờ GPU) — cách duy nhất cho anh ta MỘT giọng — hoặc chấp nhận hai giọng
cho một nhân vật 13 chương / 41 câu. Đây là quyết định đánh đổi, không phải bug, nên nó thuộc chủ
sách.

Một bài học về công cụ, không về giọng: lần thả lại này tôi dùng `bash ... &` trong một lệnh
compound và tiến trình chết theo shell cha — ranh giới biến mất, không ai thấy. Phải thả bằng
`run_in_background` của tool, và **luôn đếm lại tiến trình sau khi thả**. Đếm mới là thứ cứu, chứ
không phải cách thả.

## 2026-09-12, 04:55–05:03 — chạy trước bộ test mà ranh giới sẽ chạy, và đo cái giá của việc ấy

Bước 1 của ranh giới chạy `apply_all --apply`, và bên trong nó là bộ test đầy đủ **trên cây
thật**. Cả đêm tôi chỉ chứng minh bộ test xanh trên các cây tạm, nơi hai bài phụ thuộc môi trường
(`test_doctor…`, `test_one_click_startup_contract`) luôn đỏ vì thư mục tạm không có
`runtime/models`. Nên tôi chạy đúng lượt ấy trên cây thật: **0 lỗi, exit 0, 8 phút**. Giờ biết
chắc bước 1 sẽ đi qua, thay vì suy ra.

`before_a_batch.py` khuyên đừng chạy test giữa lô ("chạy test bây giờ là cướp CPU của nó"), nên
tôi đo luôn cái giá: **0 lần nhường máy** trong suốt tám phút ấy (`Resource mode: yield%` trong
`runtime_events`). Lần nhường duy nhất của ba mươi phút trước đó xảy ra lúc 04:39:20 vì "system
CPU 100%" và hồi lại sau 29 giây — trước khi bộ test bắt đầu. Thời gian mỗi chương của lô 5 dao
động **5,3 đến 19,8 phút** theo độ dài chương, nên một mẫu đơn không đủ để nói việc đo đạc ở nền
có làm chậm lô hay không; điều đo được là governor **không** coi việc ở nền là tải tiền cảnh.

Một mẫu, không phải một định luật: lời khuyên của cổng vẫn là mặc định đúng, và tôi phá nó một
lần có chủ đích để đổi lấy sự chắc chắn về bước chạy một mình.

## 2026-09-12, 07:25 — hai chương đúc lại đầu tiên chứng minh cả kế hoạch

Bước 4b đang chạy. Hai chương xong, và chúng là hai phép thử tôi thả ranh giới để làm.

**Chương 023 — va chạm cùng chương duy nhất còn lại của cuốn sách.** `voice_pool_pressure` trên
`lo01r_023_c45ff27cc2`: *"Không có giọng nào bị hai nhân vật dùng chung."* Tám người nam cần tám
giọng trong kho mười bốn, và báo cáo ghi **"tối ưu (chạm cận dưới)"**. SỐ BỐN và SỐ NĂM giờ là hai
giọng khác nhau — cặp mà `voice_pool_pressure` đã chỉ ra từ lô 1 và không ai đúc lại suốt mười một
tuần chương.

**Chương 031 — hai vai nói nhiều nhất cuốn sách về giọng đa số.** So trước/sau:

    trước (lo02v_031)   NGUOI TRA LOI   ngoc_linh_f108_p+00     THU LÃNH    thanh_binh_f090_p-04
    sau   (lo02r_031)   NGƯỜI TRẢ LỜI   doan_trang_f100_p+00    THỦ LÃNH    thanh_binh_f100_p-07

Hai việc xảy ra cùng lúc, và cả hai đều do bản vá: **cách viết tên** hết rơi dấu (bản vá gộp tên
của ranh giới 3 → 4 nay áp cho chương cũ), và **giọng** về đúng bản 90 chương / 83 chương mà port
mang sang. Người nghe chương 031 giờ nghe đúng hai nhân vật ấy như ở 89 chương kia.

Còn mười một chương nữa cùng loại (043 051 053 054 055 056 072 080 081 089) và chương 106. Nhịp
~10 phút/chương ở bước 4b.

## 2026-09-12, 08:20–08:45 — "cửa sổ terminal nháy liên tục": đo, tìm, sửa

Chủ sách báo lúc 08:2x: *"cứ chạy một lúc là lại có vài cái cửa sổ terminal pop ra rồi biến
mất liên tục"*, rồi *"đấy vừa mới nháy 3 4 phát lên"*. Không đoán: viết một bộ lấy mẫu
(`scratchpad/win_sampler.py`) ghi mọi cửa sổ top-level và mọi tiến trình mới mỗi 100 ms trong
5 phút. Ba cửa sổ hiện lúc **08:27:24, :25, :26**, sống 0,4–0,6 s, đúng lúc ba con của
`ollama.exe (36944)` ra đời. Heartbeat của tôi (gọi PowerShell từ Bash) thử ngay lúc 08:28:14:
**không** sinh cửa sổ — vô can.

Ollama 36944 khởi động **23:14:23 ngày 11-09** bởi watchdog (log của nó nói rõ), 90 giây sau
khi đồng hồ được chỉnh nhảy 4h17m. Cờ khởi động `CREATE_NO_WINDOW | DETACHED_PROCESS`; đo bốn
tổ hợp trên máy này, chỉ tổ hợp ấy làm cháu bật cửa sổ. Kể từ đó mỗi lần nạp model (mỗi chương
đúc lại, vì model bị dỡ sau phân tích để nhường VRAM cho TTS) là ba phát nháy.

Đang sửa thì bộ test đỏ một bài, và bài đỏ ấy dẫn tới gốc rễ thật: bài test cũ mock
`can_generate`, mã mới gọi `probe_verdict` thật, và probe thật vào Ollama đang khoẻ trả về
*"HTTP 200 nhưng response rỗng"*. `qwen3:8b` là model **suy nghĩ** — bốn token đi vào
`thinking`, `response` rỗng — nên probe cũ **không bao giờ** nói "có" với model này. Từ ngày đổi
model, mỗi lần cổng im-lặng trượt là một lần khởi động lại chắc chắn. Đo lại 08:41: mặc định
`thinking='Okay,' eval_count=4`; `think: false` → `response='1 + 1'`.

Ba sửa trong `scripts/ollama_watchdog.py` + 4 test mới + docs, một commit, chạy test và commit
trong cùng một lệnh để cây không bẩn lúc ranh giới kiểm. Xem `SURVIVING_AN_INTERRUPTION.md`.
Hai lần probe thật của tôi cũng làm nháy cửa sổ thêm hai đợt — cái giá của việc đo trên server
đang chạy sai cờ, ghi lại để không ai tưởng bản sửa chưa ăn.

## 2026-09-12, 08:50–09:10 — đổi ollama lúc an toàn, rồi chứng minh bằng đúng phép đo đã bắt lỗi

Không giết ollama giữa lúc chương 056 đang phân tích. Một task nền chờ ba điều kiện cùng đúng —
ollama không giữ model, không còn `llama-server` nào, project mới nhất đã sang `chapter_synthesis`
— rồi gọi đúng `restart_ollama()` vừa sửa: **08:50:34**, pid 36944 → 14188, cờ `0x8000200`.

Rồi nó đứng chờ lần nạp model kế tiếp và đếm cửa sổ, cùng cách đo đã bắt được ba phát nháy lúc
08:27:

    08:27 (cờ cũ)   llama-server ×2 + gpu-discover  ->  3 cửa sổ Windows Terminal, 0,4–0,6 s mỗi cái
    09:09 (cờ mới)  llama-server ×3 + gpu-discover  ->  0 cửa sổ trong 19 phút, 0 trong 5 s quanh runner

Cùng bộ ba tiến trình con, cùng máy, cùng bộ lấy mẫu; khác đúng một cờ. "Hết nháy" là con số đo,
không phải lời hứa. Watchdog chạy mỗi 5 phút theo Scheduled Task, đã đọc file mới; lần khởi động
lại sau nếu có sẽ dùng cờ mới và probe mới.

## 2026-09-12, 09:56–10:05 — kiểm các chương đúc lại, và tìm thấy va chạm thứ hai mình đã bỏ sót

Chạy `voice_pool_pressure` trên **mọi** project đúc lại (41 project, kể cả của các ranh giới
trước): 40 sạch, **1 có va chạm cùng chương — 071**: KANG + NPC THẰNG ĐIÊN cùng `thanh_binh_f100_p-04`,
mỗi người một câu. Bản ấy làm 22:52 ngày 10-09, trước bản vá holder, và KANG không có pin.

Vì sao hôm qua tôi nói "cả sách chỉ còn một va chạm cùng chương (023)": phép đo ấy gấp tên và
đếm 61 cái *tên*, bỏ NPC theo chương. Người nghe không biết NPC là gì; họ nghe hai người một giọng.
Quét lại đúng cách — `voice_pool_pressure` trên 38 project thắng của 118 chương, chỉ giữ chương
mà project ấy là bản thắng: **2** va chạm đang được ghép, 023 và 071. Đêm nay 023 được sửa; 071 ghi
vào danh sách ranh giới 6 → 7 (`3:071`). Sau đó, con số đo được sẽ là 0, và lần này đếm cả NPC.

Cũng kiểm 072 và 080 vừa đúc lại: MICHAEL, JAKE, SAM, NGƯỜI TRẢ LỜI, THỦ LÃNH đều về đúng giọng đa số.

## 2026-09-12, 10:26–10:32 — bản vá tuổi vẫn khớp cây sau ba bản vá đêm qua

`patch_a_pinned_person_outranks_a_ported_voice.py` được viết trước khi ranh giới 5 → 6 áp ba bản vá
vào `database.py` và `pipeline.py`. Thay vì để bước 1 của ranh giới sau phát hiện neo trôi lúc sáu
giờ sáng, áp thử lên một bản sao cây hiện tại: bốn file vá sạch, một test tạo, và **105 bài test
casting** (bài của bản vá + `test_cast_*`, `test_character_casting`, `test_port_*`,
`test_pin_the_book_cast`, `test_voice_matches_the_person`) xanh trên bản sao đã vá. Bản vá sẵn sàng
để xếp hàng **sau khi** ranh giới 5 → 6 chạy xong bước 7 — xếp sớm hơn thì `before_a_batch` từ
chối khởi động lô 6 vì "còn bản vá chưa áp".

10:40: **bộ test đầy đủ** trên bản sao đã vá (trừ hai bài phụ thuộc môi trường, vốn chỉ xanh trên cây
thật): 0 lỗi, 8 phút. Bước 1 của ranh giới 6 → 7 giờ là thứ đã biết.

## 2026-09-12, 10:45 — IVAN không cần `cast --age`: giọng con gái của anh ta là một pin bị mang sang

Đọc lại 062 trước khi lên kế hoạch ranh giới 6 → 7. IVAN ở đó `gender=male`, `age=unknown`, và
**`locked_voice_key = ngoc_linh_f107_p+02`** — một preset nữ warp lên kiểu trẻ con (formant 107,
pitch +2). Tức giọng con gái không phải allocator chọn lúc ấy, mà là **pin từ một project trước**
(nơi phân tích từng gọi anh ta là trẻ con) được `port_casting` mang sang nguyên vẹn. Văn bản 062
không có dấu hiệu trẻ con nào ("tôi không uống rượu", "gãi cổ, bất an", "lắp bắp").

Đó chính là ca của `_drop_pins_that_contradict_a_person` trong bản vá tuổi: nam + tuổi không phải
trẻ con + pin trỏ vào preset nữ → bỏ pin, cấp giọng nam. Nên kế hoạch ranh giới 6 → 7 gọn lại:
xếp bản vá tuổi vào ORDER **sau khi ranh giới 5 thoát**, rồi thả `--recast auto 3:071 3:062`;
không cần bước `cast --age` xen giữa bước 1 và 4b (vốn không có chỗ để xen). `cast --age` chỉ
cần nếu chủ sách biết tuổi thật của IVAN và muốn ghim.

## 2026-09-12, 12:04–12:08 — ranh giới 5 → 6 kết thúc; đối chiếu từng dự đoán ghi trước

Ranh giới thoát mã 0 lúc 12:04:35. Bước 6b giữ cách đọc ghim cho **111 chương**, ghép lại đủ 111,
0 lỗi, 0 khôi phục (một dòng khớp "thất bại" là văn bản của đoạn, không phải thông báo). Bước 7 chép
128 chương mới, sách **145 chương (000–144), 2,21 GB**, thẻ đủ, tên đĩa vẫn là chỗ giữ chỗ.

Dự đoán ghi trước — kết quả đo trên sách mới:

    một người hai giọng trong CÙNG chương          dự đoán 0      đo 0
    --across --min-chapters 5                       chỉ còn KANG   đúng: 3:066 3:067 3:087 3:090 3:091 (5 chương f093 của KANG)
    keep_the_locked_reading --book (thử khan)       không còn gì   đúng: mọi project "không đoạn nào đang phát bản đọc-theo-chữ-viết"
    giọng sai phái                                  chỉ IVAN       đúng: 1 dòng, IVAN 062, ngoc_linh_f107_p+02 (ranh giới 6 → 7 sửa)
    va chạm cùng chương trên 145 chương thắng       chỉ 071        đúng: 1, KANG + NPC THẰNG ĐIÊN (ranh giới 6 → 7 sửa)
    assemble_book --verify                          0 lệch         đúng: đúng thời lượng, kênh, tần số, không trùng khít

Năm dự đoán, năm đúng. THỦ LÃNH, NGƯỜI TRẢ LỜI, THALIA, WILLEM đã rời danh sách nhiều-giọng; 023 hết
va chạm. Ranh giới 6 → 7 thả 12:06 với bản vá tuổi trong hàng và `--recast auto 3:071 3:062`; sau nó,
hai dòng cuối của bảng trên về 0.

## 2026-09-12, 13:00 — bảng nhịp nói thêm hình dạng dữ liệu, không chỉ một cái chuông

Làm mục đã xếp hàng từ ca chương 140: `pace_retry_reachability.py` giờ in cạnh `p/lần` hai cột
**giá trị** (số giá trị phân biệt trong các lần thử) và **trống** (khoảng trống rộng nhất), đánh
dấu `*` khi không lần nào rơi vào dải *và* cả dải nằm trọn trong một khoảng trống. Cái chuông
được giữ nguyên — nó nói 38,9% và lượt sau chứng minh nó đúng — nhưng bảng nói rõ nó khớp vào
dữ liệu gì, và ghi chú kết luận đúng: "trong tầm với" là câu hỏi của **một lượt**, lượt vá đổi
phiếu diễn nên đừng nới cận vì bảng này, hãy để bước 3 phân tích lại.

Năm test, kể cả một test chạy `main()` trên log giả có đúng mười lần thử của 140 và đọc dòng
`4  12.34*` ra khỏi bảng. Script không bị khoá; commit cùng lệnh với test để cây không bẩn lúc
ranh giới 6 → 7 kiểm.

## 2026-09-12, 15:27–15:45 — lô 6 khoá dàn giọng: một dự đoán đúng, một dự đoán sai, và bản vá thứ ba

Dàn giọng lô 6 (`lo06_99a908b8f8`): 20 người nam trên 10 giọng (kho 14), 7 nữ trên 5, 5 giọng bị
dùng chung, **0/5 va chạm nằm trong cùng chương** — dự đoán "0 va chạm cùng chương" đúng lần thứ
hai liên tiếp ở quy mô thật. Dự đoán "không bậc nào quá 3 người" **sai**: `thai_son_f100_p+00`
gánh **6** nhân vật phụ (KAIN REICHARDT 8 câu, ERWIN 6, DAMIAN 4, LEON 2, GÃ 1, DORON 1), và cảnh
báo "nhiều nhân vật dùng chung một giọng" bật một lần.

Nguyên nhân nằm đúng một dòng: hết bậc trống thì `_first_free_variant` xếp theo (số chương
chung, chỉ số bậc). Người mới chưa gặp ai thì mọi bậc đều 0 chương chung, và hoà thì lấy bậc
**thấp nhất** — nên tất cả cùng rơi về một bậc, trong khi bốn bậc khác cũng 0 chương chung chỉ có
một người giữ. Không ai trong sáu người cùng chương nên người nghe lô 6 không lẫn, nhưng sáu
người một giọng là mười lăm cặp có thể gặp nhau ở lô sau.

Bản vá `patch_a_tie_goes_to_the_emptier_step.py`: chèn "số người đang giữ bậc" vào giữa hai khoá
— khoá đầu (không cùng chương) không đổi, chỉ rải người lạ ra các bậc trống-như-nhau. Hai test:
ba người lạ phải ở ba bậc; và một bậc đông-mà-lạ vẫn thắng một bậc vắng-mà-có-bạn-diễn. Áp thử
sạch trên bản sao cùng bản vá tuổi; test casting hiện có xanh. Chưa xếp hàng, ranh giới 7 → 8.

## 2026-09-12, 18:07–18:25 — ranh giới 6 → 7 dừng ở bước 1: bảy test đỏ, và cả bảy đỏ vì bước 6b của
## ranh giới TRƯỚC đã sửa đúng cái ca mà test dựa vào

Lô 6 xong 18:07 (22/22, 0 hỏng). Bước 1 áp bản vá tuổi sạch, rồi bộ test đầy đủ đỏ **7 bài**, không
bài nào thuộc bản vá tuổi: 5 ở `test_keep_the_locked_reading`, 1 ở `test_one_promoted_take…`, 1 ở
`test_a_failed_reassembly…`. Cả ba file **trỏ thẳng vào project sống** `lo03r_084b` làm "ca gốc":
đoạn 107 đang phát bản đọc-theo-chữ-viết dù có bản đọc-ghim chỉ trượt bài chính tả. Lúc 11:30,
bước 6b của ranh giới 5 → 6 đã **sửa đúng ca ấy trên project thật** (7 đoạn của 084), và lô 6 chạy
với bản vá 1 nên không bao giờ sinh ra ca ấy nữa. Bộ test xanh lúc 10:40 trên bản sao và đỏ lúc
18:07 trên cùng mã: dữ liệu đổi, không phải mã.

Không còn bản sao nào trước 6b trên đĩa (ba bản `klr_*` trong scratchpad đều đã bị diễn tập áp lên).
Nên dựng lại: lấy DB thật sau 6b và **đảo đúng những gì 6b ghi**, theo sổ cái nó để lại
(`machine_take_substitutions` 7 dòng → ứng viên ghim về `invalid`, chữ-viết về `promoted` với
`promoted_at`/`final_check_id` lấy lại từ dòng check đã đề cử nó; xoá 8 `quality_checks`
`keep_locked_reading_over_spelling_take`, 7 chấp nhận máy, 10 `runtime_events`). Tự kiểm bằng ba
con số độc lập, cả ba đúng: ghim promoted **2** (test cũ chờ 2), chữ-viết promoted **7** (đúng số
đoạn 6b đổi), finder(107) → **#13**. Lần đầu vấp CHECK của bảng (promoted phải có `promoted_at` và
`final_check_id`) — ràng buộc ấy chính là thứ bắt bản dựng phải trung thực.

Fixture đóng băng ở `D:/Novels/Audiobooks/_fixtures/lo03r_084b_pre6b/` (ngoài repo, 4,3 MB, kèm
README và script dựng), ba file test trỏ sang đó; 25 bài của bốn file xanh trên cây thật, bộ test
đầy đủ đang chạy. **Luật:** test không được trỏ vào project sống — pipeline có quyền sửa nó, và đã
sửa. Cái giá: GPU nghỉ từ 18:07 tới khi ranh giới được thả lại.

## 2026-09-12, 18:32–18:35 — thả lại ranh giới 6 → 7, và một lỗi cú pháp của tôi làm 071/062 bị bỏ qua

Bộ test đầy đủ xanh 18:32 → commit `b1aa363` (bản vá tuổi + test trỏ fixture + docs), tag
`v0.2.0-lo06v`, ghi vân tay xanh cho đúng cây ấy, thả lại ranh giới 18:33:16. Nó chạy đúng thứ tự:
hàng chờ rỗng → không chương hỏng → **"lô 3 chương 062 đã đúc lại hoàn thành - bỏ qua"**, 071 cũng
vậy → tag `v0.2.0-lo07` → khởi động lô 7 (26 chương 167..192, gieo từ lô 6, `before_a_batch` nhận
vân tay xanh nên không chạy lại bộ test) → 6b (không còn gì để giữ) → ghép sách.

Lỗi là của tôi, không phải của ranh giới: 062 và 071 **đã có** bản đúc lại hoàn thành từ các ranh
giới trước (`lo03r_062`, `lo03r_071`), nên luật chạy-lại-thì-bỏ-qua (`already_done … recast`) làm
đúng việc của nó. Muốn ép làm lại phải đánh dấu `!` — tôi đã dùng đúng dấu ấy cho `2:054! 2:056!`
đêm qua và quên ở đây. Lô 7 đang bay nên không chen đúc lại được nữa (`before_a_batch` từ chối khi
có lô đang chạy). **Ranh giới 7 → 8 phải thả với `--recast auto 3:071! 3:062!`**, cùng hai bản vá
đang chờ. Cái giá: va chạm 071 và giọng nữ của IVAN ở 062 ở lại trong sách thêm một lô.

## 2026-09-12, 18:44 — bộ test đầy đủ xanh trên bản sao có cả ba bản vá của ranh giới 7 → 8

Bản sao cây (`scratchpad/age_tree`) mang bản vá tuổi (đã vào cây thật ở `b1aa363`) cộng hai bản vá
đang chờ (supervisor không `DETACHED`, hoà-thì-chọn-bậc-ít-người) và ba file test trỏ fixture: **0
lỗi**, 8 phút, trừ hai bài phụ thuộc môi trường vốn chỉ xanh trên cây thật. Bước 1 của ranh giới
7 → 8 (quãng 02:30 sáng 13-09) giờ là thứ đã biết — lần này kiểm cả phần dữ liệu, không chỉ phần mã.

## 2026-09-12, 22:30–22:50 — lô 7 khoá dàn giọng: va chạm cùng chương đầu tiên sau bản vá holder, và nó là một lớp mới

Lô 7: 17 người nam trên 7 giọng, 9 nữ trên 7, 6 giọng dùng chung, **1/6 va chạm nằm trong cùng
chương** — chương 186: AEREN (nam, trẻ con, 3 câu) và NPC CON TRAI (nam, trẻ con, 1 câu) cùng
`ngoc_linh_f107_p+02`. Lô 5 và 6 đều 0 nên đây không phải bản vá holder hỏng, mà là chỗ nó không
với tới: **tuổi ấn định bậc formant**, nên `_first_free_variant` (nơi luật tránh-cùng-chương sống)
không được gọi cho trẻ con. Với trẻ con preset là trục đa dạng duy nhất, mà khoá xếp hạng
`usage[name]` đếm theo pool có-tên / NPC — đứa có tên và NPC đều thấy Ngọc Linh "chưa ai dùng".
Cùng lớp với CÔNG TƯỚC/ÔNG LÃO ở alpha.55: hai sổ, một giọng.

Bản vá `patch_two_children_in_one_chapter_get_two_voices.py`: sau khi xếp hạng, nếu tuổi ấn định
bậc thì hỏi thẳng sổ người giữ — preset hạng đầu mà bậc-theo-tuổi đã có người cùng chương giữ thì
lấy preset kế tiếp; không ai rảnh thì về hạng đầu. Ba test: hai đứa trẻ cùng chương → hai giọng;
đứa đầu vẫn nhận Ngọc Linh; hai đứa khác chương vẫn được dùng chung giọng ưa thích. Áp thử sạch
trên bản sao đã có ba bản vá kia, test casting xanh; xếp vào hàng ranh giới 7 → 8 (ba bản vá).

Cũng ở lô 7: IVAN không có pin (chuỗi gieo lô 7 không mang pin nữ của `lo03r_062`), được cấp
`thanh_binh_f100_p-04` — giọng nam — 65 câu ở 188–192. Chương 186 sẽ được đúc lại ở ranh giới
7 → 8 sau khi bản vá này áp; thêm `3:186!`? Không: 186 thuộc lô 7 (`7:186`), và bước 4 `--recast
auto` của ranh giới 7 tự thấy va chạm cùng chương ấy và đúc lại — đó chính là việc của bước 4.

## 2026-09-13, 02:01–02:10 — ranh giới 7 → 8 đi đúng, và 175 dạy thêm một biến

Lô 7 xong 01:34 (25 chương + 175 hỏng). Bước 1 áp ba bản vá, bộ test xanh, commit `f08435a`, tag
`v0.2.0-lo07v`. Bước 3 vá 175 → completed; bước 4 tự thấy va chạm cùng chương ở 186 và đang đúc lại
(`lo07r_186`, lần đầu chạy với bản vá hai-đứa-trẻ); rồi 4b ép 071 và 062, bước 6 lô 8.

175 qua ngay lần thử đầu với cùng phiếu diễn — nhưng phân tích lại gán câu cho người nói khác
(BẢN LINH → JULIANA), giọng khác, nhịp khác. Ghi vào `A_BAND_IN_THE_VALLEY.md` làm ca thứ hai:
phân bố nhịp thuộc về (văn bản, người nói → giọng, phiếu diễn); lượt vá đổi được cả ba.

## 2026-09-13, 02:31 — bản vá hai-đứa-trẻ chứng minh ở quy mô thật trên chính chương đã bắt lỗi

Bước 4 của ranh giới 7 → 8 đúc lại 186 (`lo07r_186_227f268641`) với bản vá vừa áp. Trước: AEREN và
NPC CON TRAI (cả hai nam, trẻ con) cùng `ngoc_linh_f107_p+02`. Sau:

    AEREN            male    child   ngoc_linh_f107_p+02   4 câu   (giữ đúng giọng người nghe ưa thích)
    NPC TRẺ CON #1   male    child   doan_trang_f113_p+01  2 câu
    NPC TRẺ CON #2   unknown child   truc_ly_f114_p+02     1 câu

`voice_pool_pressure`: "Không có giọng nào bị hai nhân vật dùng chung." Ba đứa trẻ, ba giọng, đứa
đầu không bị đẩy khỏi giọng ưa thích — đúng ba điều ba bài test khoá. Bước 4 tự thấy va chạm
(`auto: chuong co hai nguoi mot giong cung chuong:186`) và tự sửa; không cần ai gõ số chương.

4b đang chạy: 062 (ép, `lo03r_062b`) rồi 071 (ép); sau đó bước 6 khởi động lô 8.

## 2026-09-13, 03:00–03:10 — ranh giới 7 → 8 xong; sách 193 chương, 0 va chạm cùng chương; và giới hạn của luật bỏ pin

Ranh giới thoát mã 0 lúc 03:00: 062b (IVAN **giọng nam** `thanh_binh_f100_p-04`, 25 câu, 0 dùng chung),
071b (KANG `thanh_binh_f108_p-04`, 0 dùng chung), lô 8 khởi động 02:59 (29 chương 193..221), 6b không
còn gì, sách **193 chương** (000–192), 3,0 GB. Ranh giới 8 → 9 thả 03:02 với hàng rỗng và `--recast auto`.

Kiểm trên sách mới:

    một người hai giọng trong CÙNG chương          0
    va chạm cùng chương trên 193 chương thắng       0   (071 và 186 đã sửa — lần đầu cả sách về 0)
    giọng sai phái                                  1   NICAN, 062, 4 câu — xem dưới
    assemble_book --verify                          0 lệch
    người mang >1 giọng qua sách                    15  (REXERD 3 giọng / 15 chương; KANG 3 giọng / 15 chương)

**NICAN, và giới hạn thật của luật bỏ-pin-trái-giới.** Luật ấy so preset với **giới người nghe đã
ghim** (`locked_character_genders`, tức `cast --gender`), đúng như docstring: "trái với thứ NGƯỜI đã
ghim". Chưa ai ghim giới cho NICAN, nên luật không có gì để so. Truy vết 57 project: lô 3 phân tích
NICAN là **nữ** và cấp `ngoc_linh_f104`; pin ấy đi theo mọi lô; lô 7 phân tích thành `unknown`; 062b
và lô 8 phân tích thành **nam**. Cái tên "Nican" làm LLM đoán mỗi lần một khác, và dùng giới-theo-phân-
tích để bỏ pin sẽ cũng nhiễu y như thế. IVAN ở 062b có giọng nam **không phải nhờ luật này** mà vì
chuỗi gieo lô 7 không còn mang pin nữ của anh ta. Luật chưa từng được kích trên dữ liệu thật.

Kết luận: không vá. Nguồn chân lý cho giới là người nghe; nếu chủ sách biết Nican là ai thì
`cast --character NICAN --gender male` (hoặc `female`) và pin sai sẽ bị bỏ đúng ở lô sau. 4 câu.

**Mười lăm người mang nhiều hơn một giọng** (từ 11 lên 15 sau lô 7): người không có pin bị rút thăm
lại mỗi lô. REXERD giờ 3 giọng trên 15 chương, KANG 3 giọng (thêm f108 ở 071b). Số liệu cho quyết
định xếp-lại-pin của chủ sách đã ghi ở OPTIMISATION_QUEUE; mỗi lô trôi qua nó đắt thêm một chút.

## 2026-09-13, 07:03 — lô 8 khoá dàn giọng: lô đông nhất tới nay, và bản vá hoà-thì-chọn-bậc-ít-người rải đúng

Lô 8 (29 chương 193..221): **38 người nam** (20 có tên, 18 NPC) trên 15 giọng của kho 14 nam,
14 nữ trên 12 giọng. Hai mươi giọng bị dùng chung — bắt buộc, vì 38 > 14 — và **0/20 va chạm nằm
trong cùng chương**. Ba lô liên tiếp (5, 6, 8) về 0 sau bản vá holder; lô 7 có một ca trẻ con và đã
có bản vá riêng.

Dự đoán "bậc đông nhất thấp hơn 5" **đúng**: bậc đông nhất **4 người**, và ba bậc đông nhất đều 4 —
38 người trên 14 bậc trung bình 2,7, nghĩa là bản vá `patch_a_tie_goes_to_the_emptier_step` rải người
lạ ra gần đều thay vì chồng 6 lên một bậc như lô 6 (khi lô 6 chỉ có 20 người nam). Cùng một luật
tránh-cùng-chương, chỉ đổi cách hoà.

Lô 8 không có trẻ con nào nên dự đoán thứ ba chưa kiểm được ở đây. Cảnh báo "nhiều nhân vật dùng
chung một giọng" bật một lần, đúng vì dùng chung là bắt buộc; con số quyết định là 0 cùng chương.

## 2026-09-13, 09:56–10:00 — ranh giới 8 → 9 xong sạch; sách 222 chương; và một đường cong đang đi lên

Lô 8 xong 09:56, cả 29 chương, không chương nào hỏng. Ranh giới: hàng rỗng, không chương hỏng, bước 4
không thấy va chạm nào ("khong thay va cham cung chuong nao"), lô 9 khởi động 09:56 (31 chương
222..252), 6b không còn gì, sách **222 chương**, 3,39 GB. Ranh giới 9 → 10 thả 09:58.

Kiểm trên sách 222 chương: một-người-hai-giọng-cùng-chương **0**; va chạm cùng chương trên 53
project thắng **0** (lần thứ hai liên tiếp cả sách về 0); sai phái **1** (vẫn NICAN 062, chờ chủ sách
ghim giới); `--verify` 0 lệch.

Con số đi lên: người mang **hơn một giọng qua cả sách**

    sau lô 5   11
    sau lô 7   15
    sau lô 8   21      (--across ≥5 chương: 22 chương đáng đúc lại)

Cơ chế không đổi từ hôm qua: người không có pin bị rút thăm lại giọng ở mỗi lô, và kho nam 14 slot
đã có chủ hết nên `pin_the_book_cast` không ghim thêm được ai. Đây không phải lỗi mới, là cái giá
của quyết định chưa được đưa ra (xếp lại pin theo mức đã nghe, `OPTIMISATION_QUEUE`); mỗi lô nó
đắt thêm chừng 3–6 người. Người nghe không lẫn trong bất kỳ chương nào — nhưng một nhân vật phụ
quay lại sau mười chương có thể mang giọng khác.

## 2026-09-13, 14:06–15:20 — lô 9 khoá dàn giọng sạch; chương 223 hỏng và lộ ra hai lỗi, một cũ một mới

Dàn giọng lô 9: 22 người nam trên 15 giọng, 6 giọng dùng chung, **0/6 va chạm cùng chương**, bậc
đông nhất **3** — bốn lô liên tiếp về 0 va chạm sau bản vá holder; bản vá hoà-thì-chọn-bậc-ít-người
giữ bậc đông nhất ở 3–4 hai lô liền. Không có trẻ con trong lô, dự đoán thứ ba vẫn chờ.

**Chương 223 hỏng** lúc 14:0x với ba đoạn `ASR_MISMATCH_UNRESOLVED`: "Không không không không—"
(máy cho qua đúng luật), và hai đoạn bị từ chối cho qua vì **bộ sinh chạm trần khung** (1,92 s = 12
khung), tức có nhân chứng ngoài ASR nói bản thu hỏng:

1. `"Gục đi!"` — ứng viên #11 (vòng 0, 0,64 s, tự kết thúc) đủ bốn điều kiện, **finder chọn nó**,
   hook bản-hoàn-chỉnh-thay-bản-bị-cắt đã chạy, và `promote_segment_candidate(...,
   over_a_cut_off_incumbent=True)` **từ chối**: *"candidate dual-decode ledger does not contain two
   passing checks"*. Cờ ấy nới tập trạng thái nhưng chốt "hai đường phiên đều qua" ở dưới chỉ nới
   cho `keeping_the_locked_reading`. Hai đường phiên trượt lại chính là **định nghĩa** của ca này
   (văn bản dưới ngưỡng ASR phán xử). Bản vá 3 (ranh giới 5 → 6) mâu thuẫn với chính nó ở một dòng,
   và sống qua bộ test xanh vì test chỉ kiểm bốn điều kiện và finder bằng row giả, chưa bao giờ gọi
   đề cử thật với cờ ấy. Lô 9 là ca thật đầu tiên.
   → `patch_a_finished_take_is_promoted_without_two_passing_checks.py`: chốt nới cho cả hai cờ;
   phần kiểm "mã trượt chỉ là neo tên" vẫn chỉ thuộc ca giữ-cách-đọc-ghim. Test end-to-end gọi
   đề cử thật trên fixture đóng băng từ chính lô 9 (`_fixtures/lo09_223_cut_off`, backup sqlite
   nhất quán) — xanh; và một test khẳng định không có cờ thì cửa vẫn đóng (đóng ngay ở tập trạng
   thái, trước cả chốt kia — hai thông điệp, một nghĩa).

2. `"ÁAAAAA!!"` — năm ứng viên 0,96 s, bản cuối chạm trần, ASR bịa ra câu chào cuối video. Bộ
   chuẩn hoá `normalize_vocalizations_for_tts` **có** luật nguyên-âm-kéo-dài ("aaaa" → "A... a")
   nhưng mẫu đòi token chỉ gồm một nguyên âm lặp; Á đứng trước làm nó không khớp, chuỗi đi nguyên
   vào TTS — cùng hình với "Argh" mà đầu file đã kể.
   → `patch_a_stretched_cry_with_an_accent_is_still_a_cry.py`: mẫu nhận một nguyên âm dẫn đầu có
   dấu thanh cùng chữ cái gốc; "ÁAAAAA" → "Á... a", "Ôaaa" giữ nguyên, "Khôôôông" vẫn là việc khác.

Cả hai áp thử sạch trên bản sao có bốn bản vá trước, test liên quan xanh, xếp vào hàng ranh giới
9 → 10 (bước 1 quãng 19:00, trước bước 3 vá 223). Dự đoán ghi trước: lượt vá 223 sau bản vá sẽ
đề cử ứng viên tự kết thúc cho "Gục đi!" và không còn chạy tới trần với "Á... a!!"; chương lên sách.
