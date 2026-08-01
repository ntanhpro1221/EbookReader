# AGENTS.md — E Book Reader

Đọc file này trước khi sửa code. Không tạo tài liệu agent song song; cập nhật trực tiếp file này khi invariant hoặc kiến trúc thay đổi.

## Mục tiêu

Ứng dụng Windows local nhận nhiều chapter `.txt` hoặc một folder chứa TXT của cùng một book, phân tích toàn book để giữ nhân vật/giọng/cách phát âm đồng bộ, rồi tạo MP3 theo chapter và toàn book.

Yêu cầu bắt buộc:

- workflow người dùng chỉ là double-click `START.bat`;
- không hỏi người dùng trong lúc job đang chạy;
- settings, model, voice mapping, seed và threshold bị khóa theo book;
- dependency trực tiếp được pin; setup nâng cấp phải tái sử dụng runtime, không `uv venv --clear`;
- tận dụng tối đa tài nguyên trong giới hạn an toàn, tự nhường foreground và tự tăng lại;
- giả định GUI/worker/máy có thể bị đóng bất kỳ lúc nào;
- lỗi nghiêm trọng phải checkpoint, tự dừng an toàn và gửi Windows notification;
- tuyệt đối không chèn im lặng để thay nội dung TTS thất bại.

Máy đích hiện tại: Ryzen 9845HX, RTX 5060 Laptop, RAM 32 GB. Không hard-code batch hoặc VRAM theo một máy duy nhất.

## Luồng bắt buộc

```text
import + natural sort TXT
→ segment toàn book
→ Qwen phân tích toàn book, checkpoint theo batch
→ character registry + alias + pronunciation
→ khóa voice mapping/reference/seed/settings
→ unload LLM
→ từng chapter: TTS → unload TTS → Whisper → repair → FFmpeg verify
→ chapter MP3
→ full-book MP3 + M3U8 + reports
```

Không đổi sang phân tích cuốn chiếu nếu người dùng chưa thay đổi ưu tiên đồng bộ toàn truyện.

## Invariant an toàn

- `interactive_prompts=false`; pipeline/worker không mở prompt hoặc `QMessageBox`.
- SQLite là source of truth; không dùng existence/mtime làm bằng chứng hoàn tất.
- WAV/MP3 luôn ghi `.part`, validate + checksum rồi atomic replace.
- MP3 phải được FFmpeg decode toàn bộ trước khi commit.
- TTS retry theo thứ tự: seed khác → chia nhỏ → fallback engine → `failed`.
- Chapter còn segment `failed` không được publish.
- Không giữ TTS và Whisper đồng thời trên GPU khi không cần.
- Khi foreground pressure xuất hiện: hoàn thành đơn vị inference hiện tại, checkpoint, ngừng cấp việc mới, giảm tải/unload nếu cần.
- Không kill CUDA giữa kernel chỉ để nhường tài nguyên.
- Khi resume, settings hash và voice mapping phải giữ nguyên.
- TXT phải được decode từ đúng byte đã hash; ưu tiên BOM/UTF-8/CP1258 và chỉ thử UTF-16 không BOM khi có NUL heuristic.
- Pronunciation confidence được lưu trong SQLite; cùng một text đã chuyển cách đọc phải được dùng cho TTS và expected ASR.
- VieNeu mặc định chạy từng segment với seed ổn định; chỉ batch khi `deterministic_vieneu=false` đã được khóa theo book.
- Fallback phải là engine khác primary; không được ghi warning fallback nếu thực tế vẫn gọi cùng engine.
- Recovery xóa `.part`, reset stage dở và chỉ reuse artifact có checksum + validation hợp lệ.
- Project `completed` được fast-path nếu toàn bộ chapter/full-book MP3 còn decode + checksum hợp lệ.
- Dừng cưỡng bức phải kết thúc process con trước process worker để không bỏ lại FFmpeg/Ollama helper.

## Cấu trúc source

```text
START.bat
README.md
_internal/
├── AGENTS.md          # tài liệu dành cho agent/lập trình viên
├── app.py
├── e_book_reader/      # Python package chính
├── tests/
├── scripts/            # setup và system check
├── docs/               # test report và third-party notices
├── runtime/            # được tạo khi cài: venv + model cache
├── pyproject.toml
└── LICENSE
```

Tên kỹ thuật duy nhất là `e_book_reader`; tên hiển thị là `E Book Reader`. Không đưa file kỹ thuật mới ra root nếu không thật sự cần cho người dùng.

Module chính:

- `gui.py`: UI/controller, không chứa model logic.
- `worker.py`: process, heartbeat, watchdog, exception boundary.
- `pipeline.py`: orchestration và state transition.
- `database.py`: schema/transaction API.
- `analysis.py`: Qwen structured analysis.
- `character_registry.py`: canonical character, alias, voice mapping.
- `tts.py`: VoxCPM2/VieNeu adapters và fallback.
- `asr.py`: Whisper và transcript metrics.
- `audio_io.py`: validation, atomic audio, playlist.
- `resource_manager.py`: resource snapshot/decision.
- `recovery.py`: integrity/checksum recovery.
- `notifier.py`: Windows notifications.
- `process_utils.py`: kết thúc an toàn cây process worker/native helper.
- `scripts/start_windows.ps1`: kiểm tra runtime, gọi setup và mở app với thông báo UTF-8 an toàn.

## Quy tắc thay đổi

- Database/recovery change phải có crash/reopen test.
- Resource policy change phải test bằng snapshot giả lập.
- Pipeline change phải có mock adapter để test không cần model.
- Không đổi model revision hoặc tải model trong một job đang chạy.
- Không tuyên bố chất lượng/hiệu năng RTX 5060 nếu chưa test trên máy thật.
- Khi throughput xung đột với toàn vẹn output, chọn toàn vẹn output.
- Không đưa lại tên, lịch sử hoặc mô tả của các prototype/gói generate tạm vào source hay tài liệu.

## Kiểm tra trước khi bàn giao

Từ thư mục `_internal`:

```text
python -m compileall -q .
python -m pytest
```

Definition of done:

- test liên quan pass;
- các mục root hiện cho người dùng vẫn chỉ có `START.bat`, `README.md`, `_internal`; metadata Git ẩn được phép trong checkout;
- không tạo prompt giữa job;
- kill ở ranh giới bất kỳ không làm hỏng artifact đã commit;
- resume giữ settings và voice mapping;
- lỗi nghiêm trọng checkpoint + notification;
- cập nhật README hoặc `_internal/docs/TEST_REPORT.md` khi hành vi/test thay đổi.
