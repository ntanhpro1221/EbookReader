# AGENTS.md — Ebook Reader

Đọc file này trước khi sửa code. Không tạo tài liệu agent song song; cập nhật trực tiếp file này khi invariant hoặc kiến trúc thay đổi.

## Mục tiêu

Ứng dụng Windows local nhận nhiều chapter `.txt` hoặc một folder chứa TXT của cùng một book, phân tích toàn book để giữ nhân vật/giọng/cách phát âm đồng bộ, rồi tạo MP3 theo từng chapter nguồn.

Yêu cầu bắt buộc:

- workflow người dùng chỉ là mở shortcut **Ebook Reader** ở root hoặc trong Start Menu; cả hai trỏ thẳng tới `_internal\Ebook Reader.vbs`;
- không hỏi người dùng trong lúc job đang chạy;
- settings, model, voice mapping, seed và threshold bị khóa theo book;
- dependency trực tiếp được pin; setup nâng cấp phải tái sử dụng runtime, không `uv venv --clear`;
- tận dụng tối đa tài nguyên trong giới hạn an toàn, tự nhường foreground và tự tăng lại;
- giả định GUI/worker/máy có thể bị đóng bất kỳ lúc nào;
- lỗi nghiêm trọng phải giữ nguyên checkpoint đã commit, dừng và gửi Windows notification;
- tuyệt đối không chèn im lặng để thay nội dung TTS thất bại.

Máy đích hiện tại: Ryzen 9845HX, RTX 5060 Laptop, RAM 32 GB. Không hard-code batch hoặc VRAM theo một máy duy nhất.

## Luồng bắt buộc

```text
import + natural sort TXT
→ segment toàn book
→ Qwen phân tích toàn book, checkpoint theo batch
→ character registry + alias + pronunciation
→ khóa voice mapping/preset/seed/settings
→ unload LLM
→ từng chapter: TTS → unload TTS → Whisper → repair → FFmpeg verify
→ chapter MP3
→ reports + M3U8
```

Không đổi sang phân tích cuốn chiếu nếu người dùng chưa thay đổi ưu tiên đồng bộ toàn truyện.

## Invariant an toàn

- `interactive_prompts=false`; pipeline/worker không mở prompt hoặc `QMessageBox`.
- SQLite là source of truth; không dùng existence/mtime làm bằng chứng hoàn tất.
- WAV/MP3 luôn ghi `.part`, validate + checksum rồi atomic replace.
- MP3 phải được FFmpeg decode toàn bộ trước khi commit.
- TTS retry theo thứ tự: seed VieNeu khác → chia nhỏ an toàn → `failed`.
- Biến thể pitch chỉ là lớp trang trí sau inference: dùng phase-vocoder + Soxr với bộ nhớ bị chặn,
  không dùng `torchaudio.functional.pitch_shift`; lỗi pitch phải giữ waveform gốc, ghi warning và không retry TTS.
- Ngân sách frame VieNeu và giới hạn validation phải lấy từ cùng `segment_duration_policy`; codec VieNeu v3
  dùng 3.840 sample/frame ở 48 kHz. Mọi tổ hợp kind/pace/độ dài phải có headroom validation được test.
- Chỉ `vocal_effect`/`text_sfx` được phép giới hạn thời lượng bằng fade-out khi runtime vẫn trả quá dài;
  narration/dialogue/thought tuyệt đối không được cắt để lách validation.
- Chapter còn segment `failed` không được publish.
- Mọi kết thúc với `BookStatus.ERROR` phải gửi `finished.ok=false`; nhánh `completed_with_errors` gửi đúng
  một Windows notification nếu policy cho phép, đồng thời giữ nguyên checkpoint/chapter đã commit.
- Không giữ TTS và Whisper đồng thời trên GPU khi không cần.
- Sau mỗi attempt VieNeu đã trả waveform hoặc lỗi, phải thu hồi object rác và CUDA allocator cache tại ranh giới an toàn.
- RAM critical đơn lẻ phải unload model/cache rồi đo cưỡng bức lại; chỉ chuyển book sang `critical_stop` và gửi notification
  nếu lần đo sau thu hồi vẫn critical. Critical SSD hoặc nhiệt GPU vẫn dừng ngay.
- Khi foreground pressure xuất hiện: hoàn thành đơn vị inference hiện tại, checkpoint, ngừng cấp việc mới, giảm tải/unload nếu cần.
- Không kill CUDA giữa kernel chỉ để nhường tài nguyên.
- Khi resume, settings hash và voice mapping phải giữ nguyên.
- TXT phải được decode từ đúng byte đã hash; ưu tiên BOM/UTF-8/CP1258 và chỉ thử UTF-16 không BOM khi có NUL heuristic.
- Pronunciation confidence được lưu trong SQLite; cùng một text đã chuyển cách đọc phải được dùng cho TTS và expected ASR.
- Mọi vai dùng preset VieNeu đã khóa; một nhân vật không được đổi preset theo cảm xúc hoặc khi resume.
- Cảm xúc chỉ thay đổi cách thể hiện trên cùng preset: cue phi ngôn ngữ được VieNeu hỗ trợ, sampling,
  pace và mức âm lượng mục tiêu. Không thay identity giọng để giả lập cảm xúc.
- Preset được phân bổ theo giới tính và ưu tiên dùng hết pool phù hợp trước khi tái sử dụng.
- Pitch âm phải theo giới hạn từng preset đo trên preview: Phạm Tuyên không hạ; Xuân Vĩnh, Thái Sơn,
  Ngọc Trân tối đa `-1`; các preset không tin tức còn lại tối đa `-2`; pitch dương tối đa `+2`.
- NPC có nhãn cục bộ được giữ identity riêng trong phạm vi chapter/batch; NPC không phân biệt được
  ít nhất phải tách pool nam, nữ và chưa rõ giới tính.
- Nhãn NPC cục bộ trùng chính xác với tên nhân vật trong cùng chapter phải được hợp nhất trước khi
  phân vai, tránh cùng một người bị khóa hai giọng hoặc hai pitch khác nhau.
- Segment mới được cân theo K-weighted LUFS; giọng kể có anchor nhỉnh hơn hội thoại trung tính và
  chênh lệch `loud` phải tiết chế. Sample peak cap vẫn bắt buộc sau khi áp gain.
- Ngoặc kép kéo dài qua nhiều paragraph phải giữ state hội thoại; ngoặc đơn cong `‘…’` là hint
  độc thoại nội tâm để analysis tìm giọng nhân vật thay vì gán sẵn narrator.
- Whisper phải nhận WAV đã đọc/resample trong process; không truyền đường dẫn cho API Whisper vì bản
  dependency hiện tại sẽ gọi FFmpeg subprocess cho từng segment và gây nháy console trên Windows.
- Recovery xóa `.part`, reset stage dở và chỉ reuse artifact có checksum + validation hợp lệ.
- Project `completed` được fast-path nếu toàn bộ chapter/full-book MP3 còn decode + checksum hợp lệ.
- Dừng cưỡng bức phải kết thúc process con trước process worker để không bỏ lại FFmpeg/Ollama helper.
- Ollama ẩn phải ghi stdout/stderr vào `runtime/logs/ollama-server.log`; không bỏ mất bằng `DEVNULL`.
- Stream Ollama kết thúc thiếu `done=true` phải chia đôi batch hiện tại và chạy batch con; không retry nguyên
  batch lớn nhiều lần. Segment chỉ còn một phần tử mới dùng retry thông thường.
- GUI chỉ cung cấp một lệnh **Dừng**; đây không phải một chế độ an toàn riêng. Lệnh Dừng yêu cầu worker
  kết thúc ở ranh giới gần nhất, còn đóng cửa sổ được phép kết thúc worker ngay.
- Tính an toàn phải đến từ transaction SQLite, file `.part` + atomic replace, checksum và recovery:
  app/worker bị kill ở bất kỳ thời điểm nào cũng không làm mất artifact đã commit; phần dở được reset khi resume.

## Cấu trúc source

```text
Ebook Reader.lnk
README.md
_internal/
├── Ebook Reader.vbs   # launcher thật; shortcut root/Start Menu trỏ trực tiếp vào đây
├── AGENTS.md          # tài liệu dành cho agent/lập trình viên
├── app.py
├── ebook_reader/      # Python package chính
├── tests/
├── scripts/            # setup và system check
├── docs/               # test report và third-party notices
├── runtime/            # được tạo khi cài: venv + model cache
├── pyproject.toml
└── LICENSE
```

Tên kỹ thuật duy nhất là `ebook_reader`; tên hiển thị là `Ebook Reader`. Không đưa file kỹ thuật mới ra root nếu không thật sự cần cho người dùng.

Module chính:

- `gui.py`: UI/controller, không chứa model logic.
- `worker.py`: process, heartbeat, watchdog, exception boundary.
- `pipeline.py`: orchestration và state transition.
- `database.py`: schema/transaction API.
- `analysis.py`: Qwen structured analysis.
- `character_registry.py`: canonical character, alias, voice mapping.
- `tts.py`: VieNeu preset adapter, emotion delivery và deterministic retry.
- `asr.py`: Whisper và transcript metrics.
- `audio_io.py`: validation, atomic audio, playlist.
- `resource_manager.py`: resource snapshot/decision.
- `recovery.py`: integrity/checksum recovery.
- `notifier.py`: Windows notifications.
- `process_utils.py`: kết thúc an toàn cây process worker/native helper.
- `scripts/start_windows.ps1`: hiện một console ngay khi khởi động, báo tiến độ trong lúc kiểm tra runtime/nạp GUI,
  mở app bằng `pythonw.exe` và tự đóng console theo ready marker do GUI ghi sau khi cửa sổ đã render;
  lỗi giữ console để người dùng đọc.
- GUI giữ một `QLocalServer` theo user session để khóa single-instance; lần mở sau gửi lệnh kích hoạt cửa sổ
  đang chạy rồi thoát sạch, không tạo thêm tray icon hoặc worker controller.

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
- các mục root hiện cho người dùng vẫn chỉ có `Ebook Reader.lnk`, `README.md`, `_internal`; metadata Git ẩn được phép trong checkout;
- không tạo prompt giữa job;
- kill ở ranh giới bất kỳ không làm hỏng artifact đã commit;
- resume giữ settings và voice mapping;
- lỗi nghiêm trọng checkpoint + notification;
- cập nhật README hoặc `_internal/docs/TEST_REPORT.md` khi hành vi/test thay đổi.
