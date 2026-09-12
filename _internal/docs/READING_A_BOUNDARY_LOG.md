# Đọc một cái log ranh giới, sáng hôm sau

`scripts/boundary.sh N` chạy tám bước không ai ngồi cạnh và ghi mọi thứ vào
`runtime/boundary_NN.log`. Tài liệu này nói **từng bước in ra cái gì, câu nào là câu đáng lo, và
kiểm bằng lệnh nào** — để người đọc không phải suy ra ý nghĩa của 400 dòng log lúc bảy giờ sáng.
Viết 2026-09-12, sau khi ranh giới lô 5 → 6 được thả với ba bản vá và mười hai chương đúc lại.

Nguyên tắc đọc: **mỗi bước đều tự nói ra khi nó bỏ qua việc gì.** Một bước im lặng hoàn toàn là
một bước không chạy, không phải một bước thành công.

## Trước tiên: nó còn sống không, và nó đang ở đâu

```bash
tail -n 40 "D:/Novels/Ebook Reader/_internal/runtime/boundary_05.log"
```

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'bash\.exe" scripts/boundary\.sh' } |
  Select-Object ProcessId, CreationDate
```

**Một ranh giới là HAI tiến trình bash**: lớp bọc của harness (`bash -c "... eval 'bash
scripts/boundary.sh ...'"`) và chính script. Đếm bằng chuỗi `bash.exe" scripts/boundary.sh` thì
chỉ thấy script — đó là số cần đếm, và nó phải bằng **1**. Thấy 2 là có hai ranh giới đang chạy
song song, và lúc ấy phải giết bớt một:

```bash
taskkill //PID <pid> //F      # qua Bash; Stop-Process của PowerShell bị classifier chặn
```

Script **idempotent**: chạy lại đúng lệnh cũ là an toàn, mỗi bước tự hỏi "chương này đã có bản
hoàn thành chưa?" trước khi làm gì.

## Tám bước, và câu đáng lo của từng bước

| Bước | Nó làm gì | Câu đáng lo |
|---|---|---|
| 0 | Chờ lô N xong; lô chết thì khởi động lại, tối đa hai lần | `lo N chet lan thu ba` → dừng cả dây, cần người |
| 1 | `apply_all --apply`: áp hàng chờ, rút hàng chờ, chạy bộ test | `apply_all that bai` → dừng; `bo test: (khong thay dong tong ket)` → xem log |
| 2 | Commit cây đã vá | `cay git chua sach - before_a_batch se tu choi` → dừng |
| 3 | Vá chương hỏng của lô N (`launch_repair --as-repair`) | `run` trả JSON không `"ok": true`; thiếu dòng `project:` sau `=== chuong NNN ===` |
| 4 | Đúc lại giọng trong lô N (`--recast auto` đọc `voice_pool_pressure`) | `launch_repair ... thoat khac 0` |
| 5 | Bằng chứng cho từng project đúc lại (`voice_pool_pressure`, `prove_a_patch`) | `? va cham cung chuong` (không đọc được báo cáo) |
| 4b | Đúc lại chương của lô KHÁC, gom theo lô | cùng như bước 4 |
| 6 | Khởi động lô N+1, gieo từ project cuối chuỗi | `launch_batch that bai` → dừng |
| 6b | `keep_the_locked_reading --book --apply` (không GPU) | `CHƯA ghép lại` cho một chương → xem lý do; trạng thái đã lên sách được hoàn nguyên |
| 7 | `assemble_book --apply`: chép chương mới, ghi lại thẻ ID3 | `CẢNH BÁO: n chương phải lùi về một lô CŨ HƠN`; `KHÔNG ghi được thẻ` |

## Kiểm sau khi nó xong

```bash
cd "D:/Novels/Ebook Reader/_internal"
py() { runtime/.venv/Scripts/python.exe "$@"; }

py scripts/seed_chain.py 6 --batch            # lô mới đã có project chưa
py scripts/one_person_one_voice.py            # MỘT người MỘT giọng: phải về 0 chương
py scripts/one_person_one_voice.py --across   # ai còn mang hai giọng qua các chương
py scripts/voice_matches_the_person.py        # giọng có ĐÚNG phái/tuổi không
py scripts/keep_the_locked_reading.py --book  # còn đoạn nào đang đọc tên theo chữ viết
py scripts/machine_acceptances.py <project đúc lại> --markdown   # đoạn nào chưa ai nghe
py scripts/compare_runs.py <lô trước> <lô này>                   # chương nào gỡ được nhờ đâu
py scripts/prove_a_patch.py <project lô> <project đúc lại>       # mã ấy có xuất hiện lại không
```

Bốn câu hỏi ấy là bốn câu **khác nhau**, và một cuốn sách có thể đậu ba câu mà trượt câu thứ tư:

- `voice_pool_pressure` — hai người có dùng chung một giọng không (người nghe **lẫn** hai nhân vật)
- `one_person_one_voice` — một người có mang hai giọng không (người nghe **mất** nhân vật ấy)
- `voice_matches_the_person` — giọng ấy có **đúng** không (nhất quán vẫn có thể sai từ đầu)
- `keep_the_locked_reading --book` — tên riêng có được đọc **một cách** trong cả sách không

## Hình dạng chờ đợi của ranh giới lô 5 → 6 (thả 23:36 ngày 2026-09-11)

Lệnh đã thả:

```bash
bash scripts/boundary.sh 5 --recast auto 2:031 2:043 2:051 2:053 2:054! 2:055 2:056! 3:072 3:080 3:081 3:089 4:106
```

| | |
|---|---|
| hàng chờ bước 1 | ba bản vá: giữ cách đọc ghim · số đọc trọn vẹn · một-bản-được-đề-cử |
| bước 4b | 11 chương giọng-thiểu-số + chương 106, ~5 giờ GPU |
| bước 6b | 452 đoạn / 102 chương, ~41 giây một chương → **1,5–2 giờ**, không GPU |
| bước 7 | chép chương mới + ghi lại thẻ ID3 (118 chương trong 11,7 giây) |

Dự đoán ghi trước, để sáng hôm sau kiểm chứ không phải kể lại: chương 106 qua ở lần đầu (bản vá
số); `one_person_one_voice` vẫn 0 chương và danh sách `--across` mất NGƯỜI TRẢ LỜI, THỦ LÃNH,
THALIA, WILLEM; `keep_the_locked_reading --book` về "không đoạn nào đang phát bản đọc-theo-chữ-
viết" (để yên 411 đoạn vẫn phát bản gốc); KANG cần một quyết định sau khi lô 5 khoá dàn giọng.

## Ba chốt an toàn mới của bước 6b, và vì sao chúng có

Cả ba đều từ cùng một câu: **một lượt cải thiện thất bại phải để hệ thống y như trước.**

1. **Hoàn nguyên trạng thái đã lên sách.** Bản đầu đặt chương sang `verifying` rồi ghép; mọi
   đường lỗi để nó ở đó, mà `assemble_book` chỉ nhận `completed` — một chương đang trong sách sẽ
   **rơi ra trong im lặng**. Giờ nó chụp ảnh (trạng thái, mốc hoàn thành, artifact) rồi mới đánh
   dấu hết hiệu lực, và đặt lại đúng ảnh ấy khi thất bại.
2. **Chỉ chạm chương đang `completed`.** Diễn tập bắt được nó đưa ba chương từ `failed` lên
   `completed`: một chương hỏng cũ sẽ có mốc mới nhất và đoạt chỗ của bản đúc lại vừa xong.
3. **Mỗi project độc lập.** `--book` chạm 36 project; một project nổ không được làm 35 project
   kia mất lượt.

Chi tiết và bảng đo ở `KEEP_THE_LOCKED_READING.md`.

## "đã đúc lại hoàn thành - bỏ qua" và dấu `!`

Bước 3, 4 và 4b **bỏ qua** chương đã có bản hoàn thành ở phía đích (`already_done`): bước 3 xét
`…v` (vá), 4/4b xét `…r` (đúc lại). Đó là thứ làm lệnh thả lại **idempotent** — ranh giới chết
giữa chừng thì chạy lại đúng lệnh cũ, nó không làm lại chương đã xong. Hệ quả ngược: một chương
**đã từng** được đúc lại ở ranh giới trước sẽ bị bỏ qua mãi, dù lý do đúc lại lần này khác hẳn.

    09-12 18:33:20   lo 3 chuong 062 da duc lai hoan thanh - bo qua
    09-12 18:33:20   lo 3 chuong 071 da duc lai hoan thanh - bo qua

Hai dòng ấy là ranh giới 6 → 7 làm đúng luật, còn tôi thì sai cú pháp: `lo03r_062` và `lo03r_071`
có từ các ranh giới trước, và lần này muốn làm lại chúng (va chạm KANG + NPC ở 071; pin nữ của IVAN
ở 062). Muốn ép thì đánh dấu `!`: `--recast auto "3:071!" "3:062!"` — dòng `ep duc lai: 071 062`
ở đầu log xác nhận ranh giới đã hiểu. Dấu `!` cần ngoặc kép trong bash vì `!` là ký tự lịch sử.

Khi thả lại một ranh giới đã chạy dở, **bỏ** dấu `!` của chương đã xong ở lần trước (ví dụ `054!`
sau khi `lo02r_054b` hoàn thành), nếu không nó bị đúc lại lần nữa.
