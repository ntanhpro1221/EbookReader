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
Trigger  : AtLogOn (user NGDtuanh), trễ PT3M
Action   : _internal\runtime\.venv\Scripts\pythonw.exe scripts\resume_interrupted.py
Thư mục  : D:\Novels\Ebook Reader\_internal
Principal: Interactive, RunLevel Limited
```

Vài lựa chọn có lý do:

- **`AtLogOn` chứ không phải `AtStartup`.** Worker cần GPU và cần phiên người
  dùng; chạy ở session 0 lúc khởi động thì không thấy GPU.
- **Trễ 3 phút.** Cho driver, dịch vụ và ổ đĩa ổn định trước. Không có gì gấp —
  cuốn sách đã dừng sẵn rồi.
- **`pythonw.exe` chứ không phải `python.exe`.** Tránh một cửa sổ console nháy lên
  mỗi lần đăng nhập.
- **`Interactive` / `Limited`.** Không cần quyền admin, và phải nằm trong phiên
  người dùng để thấy GPU.

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
trên (đúng đắn) không đụng vào. Cái chết là **ngữ cảnh CUDA**: driver huỷ ngữ cảnh
khi máy suspend, và lời gọi CUDA đầu tiên sau khi thức dậy trả về lỗi.

Xem `docs/VRAM_AND_CONTEXT.md`.

---

## Còn thiếu gì

- Máy sập nguồn giữa lúc đang ghi `state.json` — `atomic_write_json` lo phần ghi,
  nhưng chưa ai thử rút điện thật để kiểm chứng.
- Nếu người dùng có nhiều tài khoản Windows, task chỉ đăng ký cho `NGDtuanh`.
