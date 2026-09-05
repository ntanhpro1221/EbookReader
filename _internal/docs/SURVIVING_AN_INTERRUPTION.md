# Sống sót qua một lần máy bị ngắt

Một cuốn sách chạy hết đêm. Máy khởi động lại vì Windows Update, hoặc người dùng
tắt máy, hoặc máy ngủ rồi mất ngữ cảnh CUDA. Trước bản này, cả ba trường hợp đều
để cuốn sách nằm im tới khi có người nhìn thấy — với một run chạy đêm thì mất
nguyên đêm.

Không mất dữ liệu bao giờ: pipeline checkpoint liên tục vào `project.sqlite3`, và
`resume` luôn chạy tiếp được. Vấn đề chưa bao giờ là mất việc — mà là **không có ai
bấm nút**.

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

## Còn thiếu gì

Nói thẳng, vì chỗ này dễ tưởng là đã xong hơn thực tế:

- **Chưa có lần ngủ thật nào kiểm chứng phần 2.** Toàn bộ được test bằng lỗi dựng
  sẵn qua `run_worker` thật, chứ chưa ai suspend máy giữa một run rồi xem nó tự
  đứng dậy. Lúc viết, alpha.45 đang chạy nên không thử được.
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
