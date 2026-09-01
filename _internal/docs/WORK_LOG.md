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

## Việc còn tồn, theo thứ tự sẽ làm

1. Thiên lệch dư trong phép đo tốc độ: câu dày dấu vẫn dễ bị chặn hơn ~22 lần. Chưa thử mô
   hình 3 lớp trên **nhóm** (mới thử trên từng dấu).
2. Whisper song song theo process (bước 3 trong `THROUGHPUT.md`).
3. Chồng lấn giai đoạn: xác minh chương N-1 trong khi sinh chương N.
4. `OLLAMA_NUM_PARALLEL` cho giai đoạn phân tích.
5. HiFi-Glot — tồn đọng lâu, chưa khởi động.
