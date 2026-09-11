# Sống sót qua một lần máy bị ngắt

Một cuốn sách chạy hết đêm. Máy khởi động lại vì Windows Update, hoặc người dùng
tắt máy, hoặc máy ngủ rồi mất ngữ cảnh CUDA. Trước bản này, cả ba trường hợp đều
để cuốn sách nằm im tới khi có người nhìn thấy — với một run chạy đêm thì mất
nguyên đêm.

Không mất dữ liệu bao giờ: pipeline checkpoint liên tục vào `project.sqlite3`, và
`resume` luôn chạy tiếp được. Vấn đề chưa bao giờ là mất việc — mà là **không có ai
bấm nút**.

> **Bổ sung 2026-09-07, và nó sửa một chỗ câu trên nói thiếu.** Không mất dữ liệu là đúng.
> Nhưng nếu bị ngắt **giữa pha phân tích** thì `resume` **đổi đầu ra**: nhóm đang dở được
> phân tích lại như một mảnh với ngữ cảnh cụt, nên người nói bị gán khác đi, sổ nhân vật đổi,
> casting đổi, seed đổi, audio đổi — và mọi phán quyết của chủ sách trên những đoạn ấy hết
> hiệu lực.
>
> Đã chứng minh bằng thí nghiệm có đối chứng: cùng code, cùng nguồn, một lần `stop`/`resume`
> ở 620/948 làm tập nhân vật tụt 23 → 19 và 18 đoạn đổi người nói, tất cả sau mốc bị ngắt.
> Xem `VERSIONS.md`.
>
> **Sau pha phân tích thì resume trung thành** — chương 1–4 của alpha.51 trùng khít alpha.48
> từng byte. Ranh giới là câu truy vấn này:
> `SELECT COUNT(*) FROM segments WHERE status='pending'`.
>
> Watchdog **vẫn nên** tự resume: một run chết nằm im tới sáng còn tệ hơn một quyển sách
> hơi khác. Nhưng nó phải **ghi lại** rằng lần resume ấy rơi vào pha phân tích, để sau này
> ai đó đối chiếu hai bản và thấy casting lệch thì biết ngay tại sao, thay vì đi truy ba
> tiếng như đêm nay.

Có hai kiểu ngắt, cơ chế khác hẳn nhau, nên phải xử lý riêng.

---

## 1. Máy tắt hẳn / khởi động lại / đăng xuất

Tiến trình chết. Supervisor chạy đúng một worker rồi thoát khi worker chết
(`while worker.is_alive()`), nó **không tự sinh lại**. Không có gì trong Task
Scheduler hay thư mục Startup trỏ tới project này.

### Cách phát hiện

Không cần viết thêm gì để phát hiện. `get_status()` vốn đã đối chiếu supervisor
được ghi trong `state.json` với tiến trình thật đang giữ pid đó
(`_validate_supervisor_identity`), và trả về **`"lost"`** khi bản ghi nói là đang
chạy nhưng tiến trình đã biến mất. Đó chính xác là trạng thái cần tìm.

Đừng tự đi so pid trong script — `get_status` đã làm, và làm đúng hơn (nó còn so
cả `create_time`, nên một pid bị hệ điều hành cấp lại cho tiến trình khác không
bị nhầm là supervisor còn sống).

### Script

`scripts/resume_interrupted.py` — quét `D:/Novels/Audiobooks/_versions`, và với
mỗi project:

| trạng thái | hành động |
|---|---|
| `lost` | **chạy tiếp** |
| `lost` nhưng `stop_requested` | bỏ qua |
| `running` | bỏ qua |
| `finished` / `failed` / `stopped` | bỏ qua |

Hẹp có chủ ý, vì sai ở đây thì hậu quả nặng hơn vấn đề đang sửa:

- **Không bao giờ ghi đè một yêu cầu dừng.** Người ta bảo nó dừng; nó sống lại sau
  một lần reboot thì tệ hơn hẳn khoảng trống đang được lấp.
- **Không đụng vào `running`.** `start_background` cũng tự chặn double-start
  (`previous_status.running` → `BackgroundAlreadyRunning`), nên đây là lớp thứ hai.
- **Một project hỏng không chặn những cái sau nó.**

Chạy tiếp = `start_background(project)`, đúng lời gọi mà `cli resume` dùng
(`cli.py:797`). Worker mở lại db và settings đã khoá sẵn có, nên nó **chạy tiếp từ
checkpoint chứ không làm lại cuốn sách từ đầu**.

### Scheduled Task

```
Tên      : EbookReaderAutoResume
Action   : _internal\runtime\.venv\Scripts\pythonw.exe scripts\resume_interrupted.py
Thư mục  : D:\Novels\Ebook Reader\_internal
Principal: InteractiveToken, LeastPrivilege
Trigger 1: LogonTrigger, trễ PT3M          — máy khởi động lại / đăng nhập lại
Trigger 2: EventTrigger Power-Troubleshooter ID 1, trễ PT1M — máy vừa thức dậy
Trigger 3: TimeTrigger lặp PT5M vô hạn     — lưới an toàn
```

Vài lựa chọn có lý do:

- **`AtLogOn` chứ không phải `AtStartup`.** Worker cần GPU và cần phiên người
  dùng; chạy ở session 0 lúc khởi động thì không thấy GPU.
- **Có trigger sự kiện thức dậy** vì **thức dậy từ sleep không kích hoạt
  `AtLogOn`** — không ai đăng nhập lại cả. Thiếu nó thì phần 2 dưới đây nằm chờ
  tới lần đăng nhập kế tiếp, tức là có thể cả đêm.
- **Lặp 5 phút** làm lưới an toàn cho mọi đường mà hai trigger kia bỏ sót.
  `start_background` tự chặn double-start nên chạy thừa là vô hại, và script chỉ
  đọc 28 file JSON.
- **Trễ 3 phút / 1 phút.** Cho driver, dịch vụ và ổ đĩa ổn định trước.
- **`pythonw.exe` chứ không phải `python.exe`.** Tránh cửa sổ console nháy lên.
- **Đăng ký bằng XML.** `New-ScheduledTaskTrigger -RepetitionDuration
  ([TimeSpan]::MaxValue)` của PowerShell 5.1 báo lỗi
  `P99999999DT23H59M59S ... out of range`; XML bỏ trống `<Duration>` là lặp vô hạn.

Xem / gỡ:

```powershell
Get-ScheduledTask -TaskName EbookReaderAutoResume
Unregister-ScheduledTask -TaskName EbookReaderAutoResume -Confirm:$false
```

### Nhật ký

Chạy lúc đăng nhập thì không ai đọc stdout, nên script ghi vào
`D:/Novels/Audiobooks/_versions/_auto_resume.log` — ngoài repo như mọi output
khác, và là *file* chứ không phải thư mục nên vòng quét version bước qua nó.

> **Bẫy:** `Get-Content` của PowerShell 5.1 đọc file bằng ANSI nên tiếng Việt hiện
> ra vỡ (`bá» qua`). File vẫn là UTF-8 đúng. Đọc bằng
> `Get-Content ... -Encoding UTF8`, hoặc bằng `tail`.

### Một lỗi đáng nhớ: in tiếng Việt làm chết cả run

Test chạy trên `tmp_path` thì xanh hết, nhưng chạy thật thì crash ngay:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u1ecf'
```

Windows đưa cho script một stdout cp1252 nhiều hơn là không — môi trường Task
Scheduler cũng vậy — và **mọi câu script này in ra đều là tiếng Việt**. `print()`
chết ở chữ "bỏ qua" và kéo theo cả run.

Nặng hơn nữa: `say()` lúc đó in **trước** rồi mới ghi log, nên cú crash xoá luôn
dấu vết duy nhất chứng minh có ai đó đã thử. Hai thay đổi:

1. **Ghi log trước, in sau.** Log là nửa bền; nửa mong manh không được phép kéo
   theo nó.
2. **`_say_safely()`** — `print`, rồi lùi về ghi utf-8 thẳng vào `sys.stdout.buffer`,
   rồi lùi về im lặng (dưới `pythonw` không có console nào cả).

Test cũ bỏ sót vì pytest bắt stdout bằng một object mã hoá utf-8 rất vui vẻ. Test
bây giờ dựng một stdout ném lỗi đúng như thật, và một stdout đã đóng. Bỏ guard đi
thì cả ba fail.

Bài học rộng hơn: **test trên `tmp_path` không thay được một lần chạy thật.**

---

## 2. Máy ngủ / ngủ đông rồi thức dậy

Khác hẳn. Tiến trình **vẫn sống** — nên `get_status` báo `running`, và phần 1 ở
trên (đúng đắn) không đụng vào. Cái chết là **ngữ cảnh CUDA**: Windows huỷ ngữ
cảnh khi máy suspend, và lời gọi GPU đầu tiên sau khi thức dậy ném lỗi.

### Vì sao "nhả model rồi nạp lại" không cứu được

Đây là điều phản trực giác và là lý do phần này không giống
`_recover_from_memory_pressure`. **Cả PyTorch lẫn CTranslate2 đều không dựng lại
được ngữ cảnh CUDA bên trong chính tiến trình đã mất nó.** `torch.cuda.empty_cache()`
không giúp gì; ngữ cảnh coi như mất suốt đời tiến trình. Thứ duy nhất chữa được là
**một tiến trình mới**.

Kiến trúc làm điều đó rắc rối hơn tưởng: pool TTS là các tiến trình con `spawn`
(nên chúng có thể được dựng lại), nhưng **ASR chạy ngay trong tiến trình worker
chính** (`asr.py` nạp faster-whisper lên `cuda`). Nên không có cách nào cứu tại chỗ.

### Cách xử lý

Worker phân loại lỗi (`is_lost_gpu_context`) và, nếu đúng là mất ngữ cảnh, **kết
thúc run như một lần dừng sạch** thay vì một thất bại: `BookStatus.STOPPED`, sự
kiện `GPU_CONTEXT_LOST`, và terminal event mang cờ `gpu_context_lost: true`.

Chỗ hay: **không phải sửa `background_runner.py` một dòng nào.** `_terminal_result`
vốn ánh xạ `ok=True, stopped=True` → state `"stopped"`, và `stop_requested` chỉ bật
khi có người thật sự yêu cầu. `_record_worker_event` giữ nguyên mọi key tuỳ ý, nên
cờ đi thẳng vào `last_event`. Watchdog nhận ra đúng tổ hợp đó:

> `state == "stopped"` **và** `last_event.gpu_context_lost` **và không** `stop_requested`
> = một lần dừng không ai yêu cầu, cần một tiến trình mới.

### Chặn vòng lặp vô hạn

Rủi ro của thiết kế này là một GPU hỏng thật sẽ khởi động lại mãi mãi. Hai lớp
chặn:

1. **Lỗi vĩnh viễn bị loại thẳng** và thắng mọi marker nhất thời trong cùng chuỗi:
   driver quá cũ, không có kernel image cho card này, device-side assert, illegal
   memory access, misaligned address. Những lỗi này sẽ hỏng y hệt trong tiến trình
   mới.
2. **Đếm có ràng buộc tiến độ.** `runtime/background/gpu_context_lost.json` giữ số
   lần thử. Số này **chỉ tăng khi lần mất trước không tạo ra tiến độ nào**; hễ số
   segment đã có audio tăng lên thì reset về 1. Nên một máy ngủ mỗi đêm không bao
   giờ tiến gần giới hạn, còn một card không tổng hợp nổi một segment thì sau 5 lần
   sẽ hỏng hẳn để người xem thấy.

### Nhận diện lỗi

Marker được so trên **toàn bộ chuỗi exception** (`__cause__` / `__context__`), vì
chuỗi thú vị hầu như không nằm trên exception nổi lên trên cùng — lỗi driver tới
dưới dạng `__cause__` của một `RuntimeError` từ pipeline.

Và chỉ tính khi thông điệp **có nói về GPU** (`cuda`, `cublas`, `cudnn`,
`ctranslate`, `gpu`, `nvidia`). Vài marker như `"unknown error"` hay
`"initialization error"` quá chung để tin một mình.

### Một lưu ý khi test

Test qua `run_worker` thật, không chỉ test các hàm rời — vì **định tuyến mới chính
là lỗi**. Vô hiệu hoá nhánh mới thì sách bị đánh dấu failed trở lại và test nói ra
điều đó. Test hàm rời không bắt được chuyện đó.

---

## 3. Ollama chết theo kiểu tệ hơn cả hai kiểu trên

Đây là thứ **chỉ một lần ngủ thật mới lộ ra**, và nó phủ nhận giả định ngầm của cả
phần 1 lẫn phần 2: rằng tiến trình của ta là tiến trình duy nhất giữ ngữ cảnh CUDA.
Không phải. Ollama là một dịch vụ riêng, cũng giữ ngữ cảnh CUDA, cũng mất nó khi máy
ngủ — nhưng nó **treo mà vẫn trông khoẻ**.

Đo lúc 18:45 ngày 05/09/2026, khoảng 90 giây sau khi máy thức:

| kiểm tra | kết quả |
|---|---|
| `GET /api/tags` | **HTTP 200 trong 17ms** |
| `GET /api/ps` | qwen3:8b, `size_vram` 6,03 GB, "đang nạp" |
| `nvidia-smi` | giữ 6762 MiB, **utilization 0%** |
| `POST /api/generate` | **không trả về gì sau 20 giây** |

Mọi phép kiểm tra rẻ tiền đều nói "sống". Câu hỏi trung thực duy nhất — *có nhả ra
được một token không* — nói "chết", và không có gì đang hỏi câu đó.

Pipeline thì xử lý đúng: coi kết nối rớt là lỗi truyền tải và thử lại, đúng như comment
trong `analysis.py` hứa. Nhưng nó **thử lại vào một cái xác**, với ngân sách hữu hạn —
2 lượt cho phản biện đạo diễn, 3 cho batch. Không can thiệp thì sách hỏng sau vài phút.

### `scripts/ollama_watchdog.py`

Khởi động lại `ollama serve`. Chỉ thế mới chữa được: ngữ cảnh mất là mất suốt đời tiến
trình, không có cách cứu tại chỗ nào để thử trước.

Dè dặt có chủ ý, vì **lỗi ngược lại cũng thật**: khởi động lại một Ollama khoẻ sẽ đuổi
một model 6 GB ra khỏi VRAM, và một probe xếp hàng sau request thật thì **trông y hệt**
một cái treo. Nên phải có hai tín hiệu độc lập:

1. Có project **đang chạy thật**, và log của nó **im quá `STALL_SECONDS` (10 phút)**.
   Batch phân tích rơi xuống mỗi 5–20 giây, tổng hợp còn ồn hơn, nên 10 phút im nằm
   ngoài mọi hành vi bình thường.
2. Probe sinh chữ, cho **`PROBE_TIMEOUT_SECONDS` (2 phút)** — đủ lâu để một request
   thật chạy xong trước nó. Dưới một phút là gọi một dịch vụ đang bận là đã chết.

Và **không giữ model nào thì không khởi động lại**: kiểu treo này là một model *đã nạp*
mà không sinh được chữ. Chưa nạp gì thì chẳng có gì kẹt quanh một ngữ cảnh chết.

Phần lớn test khoá lại **những lần nó từ chối hành động**, không phải lần nó khởi động
lại. Bỏ bất kỳ luật kiềm chế nào cũng làm test đỏ.

Chạy chung Scheduled Task với phần 1, là action thứ hai — cùng ba trigger, và nó chỉ
ghi log khi thật sự làm gì (`_ollama_watchdog.log` không tồn tại nghĩa là chưa phải
can thiệp lần nào).

## Còn thiếu gì

Nói thẳng, vì chỗ này dễ tưởng là đã xong hơn thực tế:

- **Đã có một lần ngủ thật (05/09/2026, ngủ 17:02 → thức 18:43).** Kết quả: trigger sự
  kiện thức dậy bắn đúng 1 phút sau (18:44:22), watchdog thấy project `running` nên
  đúng đắn không đụng vào, và worker sống sót qua giấc ngủ — nó kẹt ở một request HTTP
  xuyên 1h40 rồi rớt khi thức, và đường xử lý lỗi truyền tải có sẵn nhận đúng.
  **Đường mất-ngữ-cảnh-CUDA của phần 2 vẫn chưa chạy**, vì tiến trình của ta không phải
  cái mất ngữ cảnh — Ollama mới là (phần 3).
- **Danh sách marker lấy từ các lỗi hậu-suspend đã biết**, không phải từ một lỗi
  quan sát được trên chính máy này. Lần mất ngữ cảnh thật đầu tiên nên được đối
  chiếu với `GPU_CONTEXT_LOST_MARKERS`; nếu nó rơi vào nhánh failed thì thêm chuỗi
  vào đó.
- **Một run đang chạy không được bảo vệ bởi bản vá vừa merge.** Tiến trình worker
  đã nạp `worker.py` cũ vào bộ nhớ; sửa file trên đĩa không đổi được nó. Chỉ những
  lần khởi động sau mới có.
- Máy sập nguồn giữa lúc đang ghi `state.json` — `atomic_write_json` lo phần ghi,
  nhưng chưa ai thử rút điện thật để kiểm chứng.
- Nếu người dùng có nhiều tài khoản Windows, task chỉ đăng ký cho `NGDtuanh`.

## Ba tín hiệu "run còn sống", ba kiểu sai (2026-09-07)

`watch_listener_acceptances.py` cần biết run đã dừng chưa để tự thoát. Tôi làm sai ba lần,
và **cả ba lần đều vì một lý do giống nhau**: tôi kiểm tín hiệu lúc run đang chạy, không bao
giờ kiểm lúc run đã xong.

| lần | tín hiệu | hỏng thế nào | phát hiện ra sao |
|---|---|---|---|
| 1 | đọc `runtime/background/state.json` | **giết chết alpha.50** — trên Windows, đổi tên đè lên file đang mở thì lỗi `WinError 5`, và cứ 15 giây một lần thì sớm muộn cũng rơi trúng lúc supervisor ghi | run chết sau 44 phút phân tích |
| 2 | độ cũ của heartbeat trong lease | **chập chờn** — theo alpha.50 đúng suốt 5 tiếng, rồi alpha.51 xuất chương với lease cũ 2.380 giây, nên watcher về nhà sau 3 phút | tình cờ, 15 phút trước cửa sổ chương 3 |
| 3 | pid trong lease còn sống không | **không bao giờ bắn** — tắt sạch thì pipeline **xoá lease**, truy vấn trả về rỗng, và guard "chưa có lease thì chưa bắt đầu" nuốt luôn trường hợp này | **chủ sách đưa bảng background tasks**: watcher alpha.51 vẫn chạy lúc 10:22 cho một run kết thúc từ 08:52 |

Lần 3 là kiểu hỏng tệ nhất trong ba: không có gì sai cả, chỉ là một task treo im lặng chiếm
chỗ và không báo gì. Nếu chủ sách không mở bảng ấy ra thì nó còn chạy đến hết phiên.

### Vì sao truy vấn ấy không thể tự trả lời

```sql
SELECT pid FROM worker_leases WHERE state='running' ORDER BY heartbeat_at DESC LIMIT 1
```

Trả về rỗng ở **hai** tình huống trái ngược nhau: run **chưa bắt đầu**, và run **đã kết thúc
sạch**. Guard viết cho tình huống đầu (đúng — không được thoát trước khi run kịp khởi động)
che mất tình huống sau. Một test cũ ghim đúng nửa đầu ấy và không thể phát hiện nửa sau.

### Cách phân biệt

Hai nguồn tin, mỗi nguồn lấp chỗ trống của nguồn kia:

1. **Watcher có từng thấy lease chưa.** Thấy rồi mà giờ mất → run đã xong. Dùng cho run chết
   đột ngột chưa kịp ghi stage kết thúc.
2. **Stage của sách.** `completed` hoặc `completed_with_errors` → đã xong từ trước. Dùng cho
   watcher khởi động *sau* khi run kết thúc, nó không có gì để nhớ.

Và **lease còn sống thắng cả hai** — vì `resume` chạy trên cuốn sách mà stage vẫn còn ghi
`completed_with_errors` từ lượt trước. Đó chính là tình huống alpha.51, tức là tình huống
người ta bật watcher lên. Đảo thứ tự thì watcher thoát ngay giữa lượt chạy nó sinh ra để phục
vụ. Một test ghim riêng điều này.

**Bài học chung, không riêng script này:** một tín hiệu "còn sống" phải được kiểm ở **cả hai**
đầu — lúc chưa bắt đầu, lúc đang chạy, và lúc đã kết thúc. Ba lần liên tiếp tôi chỉ kiểm đầu
giữa.

## Nhánh `fix/resume-fidelity`: câu hỏi đã sắc lại (2026-09-07)

Trước đây tôi báo cáo nhánh này là "đúng nhưng chưa xong, và **hai** test cũ không đồng ý",
rồi để chủ sách quyết. Đọc kỹ lại thì cả hai vế đều cần sửa.

### Chỉ một test bất đồng, không phải hai

`test_pending_singleton_wake_retains_previous_source_lock_in_durable_critic` **không nói gì**
về chính sách tách nhóm. Chủ đề của nó là khoá ngữ nghĩa `adjacent_thought_wake_self_rescue`
giữ được `emotion="afraid"` khi director critic đòi đổi sang `neutral`. Dòng

```python
assert [str(row["stable_id"]) for row in group] == ["wake-thought"]
```

nằm **bên trong hàm mock**, chỉ để mock biết trả về đúng một mục. Nó vô tình ghim hành vi hiện
tại chứ không bảo vệ hành vi ấy. Nhóm to lên thì phải sửa mock, còn điều test bảo vệ không suy
suyển gì.

`test_resume_hole_splits_pending_runs_but_keeps_original_neighbor_context_and_scope` thì có
ghim thật (`target_groups == [["resume-hole-1"], ["resume-hole-3"]]`). Nhưng ba khẳng định
mang ý nghĩa của nó — `next_text`, `previous_text`, và phạm vi cục bộ — **vẫn đúng** sau fix,
vì gửi nguyên nhóm thì hàng xóm còn nguyên chứ không mất đi.

### Cái giá: dưới 0,42%

Đây là con số tôi chưa từng tính trước khi để câu hỏi treo, và nó đổi hẳn cán cân.

`stable_groups` dựng từ **mọi** dòng, nên nhóm đã xong hẳn thì bỏ qua, nhóm chưa động tới thì
gửi nguyên — **giống hệt cách cũ**. Hai cách chỉ khác nhau ở nhóm *vắt ngang* điểm ngắt, và
mỗi lần ngắt chỉ tạo ra **một** nhóm như vậy.

| điểm ngắt (trên 948 đoạn, nhóm 5) | nhóm vắt ngang | đoạn phân tích lại |
|---|---|---|
| 620 | 0 | 0 (0,00%) |
| 622 | 1 | 2 (0,21%) |
| 623 | 1 | 3 (0,32%) |
| 624 | 1 | 4 (0,42%) |

**Tối đa 4 đoạn.** Không phải "phân tích lại nửa cuốn sách" như cái giá tôi ngầm giả định khi
để câu hỏi lại cho chủ sách.

### Đổi lại được gì

Thí nghiệm có kiểm soát ngày 2026-09-07: cùng mã, cùng nguồn, cùng cách đọc đã gieo, một lần
dừng cố ý ở 620/948. Lượt liền mạch tìm ra **23 nhân vật**, lượt bị ngắt tìm ra **19**, với
**18 phân vai khác nhau** — và mọi khác biệt đều nằm sau điểm ngắt, kéo tới hết sách vì các
lần trộn registry là toàn cục.

### Đề xuất

Làm. Bốn đoạn phân tích lại đổi lấy chuyện một lượt bị ngắt cho ra **đúng cuốn sách** như lượt
liền mạch. Test thứ hai chỉ cần sửa mock; test thứ nhất cần đổi một khẳng định về `target_groups`
kèm ghi chú vì sao — ba khẳng định thật của nó vẫn xanh.

**Chưa gộp**: `analysis.py` là file khoá, và alpha.52 đang chạy. Chờ bản đó xong.

## Dừng một task của harness KHÔNG dừng script nó đã thả (2026-09-11)

Ranh giới lô 4 được thả rồi cần thả lại với danh sách chương khác. `TaskStop` báo thành công,
nhưng nó chỉ giết **lớp bọc** của harness; `scripts/boundary.sh` mà lớp ấy sinh ra vẫn chạy. Đo
lúc 00:27:

```
pid 28560   boundary.sh 4 --recast auto 3:084                 <- tưởng đã dừng
pid 25272   boundary.sh 4 --recast auto 1:007 2:054 ...        <- vừa thả
```

**Hai ranh giới cùng chờ một lô.** Khi lô 4 xong, cả hai sẽ áp bản vá, commit, tag và khởi động
lô 5 — hai lần. Không cổng nào chặn: mỗi tiến trình tự nó làm đúng thứ nó được bảo.

Cách kiểm, và nó là cách duy nhất đáng tin:

```powershell
Get-CimInstance Win32_Process -Filter "Name='bash.exe'" |
  Where-Object { $_.CommandLine -like '*boundary.sh*' } |
  Select-Object ProcessId, CommandLine
```

Đếm phải ra **một** dòng có `boundary.sh <số>` là *câu lệnh* của nó. Những dòng `bash -c "source
... snapshot ..."` là lớp bọc của harness và chứa cùng chuỗi ấy trong command line — đừng đếm
chúng thành ranh giới thứ hai; xem `ParentProcessId` để phân biệt.

Giết cả hai rồi thả lại đúng một cái. Giết `boundary.sh` **không** ảnh hưởng lô đang chạy: lô là
một tiến trình `ebook_reader.cli run` riêng, và nhịp tim của nó vẫn 3,8 giây sau khi giết ba
tiến trình bash (đã kiểm, không đoán).

## Đừng `git add -A` khi một ranh giới tự chạy đang bay (2026-09-11, 07:30)

Commit `7e5e4bd` mang thông điệp về chuyện tám người một bậc giọng, nhưng nội dung của nó gồm
**cả ba bản vá** mà `boundary.sh` vừa áp ở bước 1: `audio_io.py`, `character_registry.py`, bốn
file test mới, và việc rút hàng chờ. Lý do: tôi chạy `git add -A .` đúng lúc bước 1 vừa ghi xong
và bước 2 chưa commit.

Hậu quả **không** phải lỗi chức năng — bản vá đã áp, hàng chờ rỗng, cây sạch, và bước 2 của
ranh giới chỉ thấy "không có gì để commit" rồi đi tiếp. Hậu quả là **hồ sơ sai**: người đọc
`git log` sau này sẽ thấy ba bản vá vào cây dưới một commit nói về chuyện khác, và thông điệp
commit mà tôi viết cho chúng — với lý do, số đo và dự đoán — thì không tồn tại.

Không sửa lịch sử vì ranh giới đang chạy bảy tiếng nữa và `git add -A` của nó có thể đụng index
giữa lúc amend. Luật từ giờ, và nó rẻ: khi một ranh giới đang bay, **stage từng đường dẫn cụ
thể** (`git add docs/X.md`), đừng bao giờ `-A`. Cây làm việc không phải của riêng ai lúc ấy.

## Phiên Claude Code thoát thì ranh giới chết, còn lô thì KHÔNG (2026-09-11, 08:45 → 09:10)

Phiên trước thoát lúc ~08:45 trong khi `boundary.sh 4` đang ở bước 4b (đúc lại chương 007).
Sáng ra: **0** tiến trình `boundary.sh`/`launch_repair.sh`, nhưng project `lo01r_007` vẫn chạy
tiếp — lúc 08:48 nó ở 63/151, lúc 08:56 đủ 151/151 và đang `verifying`. Khác `TaskStop` (chỉ
giết lớp bọc), việc phiên thoát giết cả cây shell của harness; còn `cli run` có supervisor riêng
(`supervisor_pid`) không thuộc cây ấy nên sống sót. Hai hành vi ngược nhau của hai cách dừng, và
cả hai đều đã đo.

Hậu quả thật của lần này: ranh giới chết giữa chừng, và `boundary.sh` cũ **không chạy lại được**
— bước 3 sẽ vá lại 097/106 (lô 4 vẫn ghi chúng `failed`), bước 4 đúc lại 104 lần nữa, 4b tạo
project 007 thứ hai cạnh cái đang chạy. Nên nó được làm cho **chạy lại được**: mỗi bước hỏi
"chương này đã có một project HOÀN THÀNH trong thư mục đích chưa?" (có → bỏ qua; hỏng → chạy
lại, đúng cái 084 cần), đợi GPU rảnh trước mỗi lần tạo project và trước cả bước 1 (`apply_all`
từ chối khi còn lượt bay — đúng), bỏ qua bước 6 nếu lô kế đã có project. Kiểm trên dữ liệu thật
trước khi tin: 097/104/062 → bỏ qua, 106/007/084/054 → chạy.

Cũng nối lại chuỗi gieo qua các bước: `SEED` chạy từ project lô → lô vá → đúc lại (kể cả của lô
khác) → lô kế tiếp (`launch_batch.sh --seed-from`). Bản trước gieo lô 5 từ `seed_chain 4 --seed`,
tức bỏ qua mọi giọng vừa cấp ở 4b — một người hai giọng, lần nữa, ở tầng khác.

## Lần thứ hai cho một chương mở lại project cũ, và `run` từ chối trong im lặng (2026-09-11, 09:15)

Tên project vá / đúc lại là **địa chỉ theo nội dung** của (tiêu đề, nguồn): cùng chương, cùng
tiêu đề → cùng thư mục. Lần thứ hai cho một chương — 106 sau khi lần đầu hỏng, 007 sau khi bị
dừng dở, 084 hỏng ở lô 3 — vì thế **mở lại** project cũ thay vì tạo mới; rồi `run` từ chối resume
vì hash mã đã đổi sau bản vá; rồi `launch_repair.sh` đổ JSON ấy vào `/dev/null`; rồi vòng đợi
thấy lease chết và chương không "chưa xong" nên coi là xong. Log ghi `=== xong ca lo va ===` sau
hai phút, không có dòng `project:` nào. Ba tầng, mỗi tầng hợp lý một mình, cộng lại thành một
lần chạy không làm gì mà báo là xong.

Sửa ở hai tầng: tiêu đề thêm một chữ cái cho tới khi chưa có project nào mang nó
(`lo04v_106` → `lo04v_106b`), và `run` trả `"ok": false` thì in lỗi ra rồi đi tiếp thay vì im.
Kiểm cách rẻ nhất: sau mỗi `=== chuong NNN ===` phải có một dòng `project:`; không có là không
làm gì.

**Sửa một kết luận sai của tôi cùng buổi sáng:** tôi giết `launch_repair.sh 2` lúc nó đang đợi
chương 054 và viết rằng "lần này giết cả lượt chạy". Sai — `cli run` trả lời `Project đã có
background supervisor: 33256` và nhịp tim 4 giây; bộ lọc tiến trình của tôi không khớp dòng lệnh
của supervisor. Kết luận đúng vẫn là kết luận cũ: **giết shell không giết lượt chạy**, dù shell ấy
là `launch_batch.sh` đã tách ra hay `launch_repair.sh` đang đợi. Đo bằng nhịp tim, đừng đo bằng
danh sách tiến trình.

Và hai cờ mới của `boundary.sh` sinh ra từ lần chạy lại này: `4:097!` **ép** đúc lại chương đã
có project hoàn thành (hoàn thành ≠ đúng — 097/104 xong trước bản vá gạch dưới và mang một người
hai giọng), `--skip 106` để một chương chưa có bản vá không bị vá lại vô ích ở mỗi lần thả.
