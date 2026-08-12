# AGENTS.md — Ebook Reader

Đọc file này trước khi sửa code. Không tạo tài liệu agent song song; cập nhật trực tiếp file này khi invariant hoặc kiến trúc thay đổi.

## Mục tiêu

Ứng dụng Windows local nhận nhiều chapter `.txt` hoặc một folder chứa TXT của cùng một book, phân tích toàn book để giữ nhân vật/giọng/cách phát âm đồng bộ, rồi tạo MP3 theo từng chapter nguồn.

Yêu cầu bắt buộc:

- workflow GUI mở shortcut **Ebook Reader** ở root hoặc trong Start Menu; workflow tự động dùng
  `python -m ebook_reader.cli`/entrypoint `ebook-reader-headless` và tuyệt đối không điều khiển cửa sổ;
- không hỏi người dùng trong lúc job đang chạy;
- settings, model, voice mapping, seed và threshold bị khóa theo book;
- dependency trực tiếp được pin; setup nâng cấp phải tái sử dụng runtime, không `uv venv --clear`;
- runtime đã tồn tại nhưng thiếu dependency Python phải dùng nhánh repair `pip install -e .` nhẹ;
  không cài lại PyTorch, không pull lại model và không chạy full setup cho trường hợp này.
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
→ character registry theo speaker name + pronunciation
→ khóa voice mapping/preset/seed/settings
→ unload LLM
→ từng chapter: TTS → unload TTS → Whisper → repair → FFmpeg verify
→ chapter MP3
→ reports + M3U8
```

Không đổi sang phân tích cuốn chiếu nếu người dùng chưa thay đổi ưu tiên đồng bộ toàn truyện.

## Invariant an toàn

- `interactive_prompts=false`; pipeline/worker không mở prompt hoặc `QMessageBox`.
- CLI `status`/`report`/`log` và `create --dry-run` là read-only: không mkdir, migrate SQLite, recovery,
  dọn lease hay chạm file control; SQLite đang chạy phải được đọc bằng URI `mode=ro`, không dùng `immutable=1` vì có WAL.
- Background start chỉ gửi `READY` sau khi worker đã giữ `.worker.lock`, nạp settings khóa và xác minh toàn bộ source.
  State/control JSON ghi atomic trong `runtime/background`; recovery tuyệt đối không xóa `.part` trong namespace này.
- Background identity gồm project path + instance token + PID + process create-time. Force-stop phải khóa launch ownership,
  đối chiếu lại đủ identity ngay trước khi kill/ghi state và từ chối nếu một instance mới đã thay thế instance được yêu cầu.
- Hai tiến trình tạo cùng title/manifest phải serialize bằng OS creation lock xuyên suốt bước chọn project root,
  ghi settings và initialize SQLite; profile khác nhau không được ghi chéo settings/DB.
- Mọi process nền trên Windows dùng `pythonw`/`CREATE_NO_WINDOW`, redirect stdio UTF-8 vào log; POSIX dùng session riêng.
- SQLite là source of truth; không dùng existence/mtime làm bằng chứng hoàn tất.
- WAV/MP3 luôn ghi `.part`, validate + checksum rồi atomic replace.
- MP3 phải được FFmpeg decode toàn bộ trước khi commit.
- TTS retry theo thứ tự: seed VieNeu khác → chia nhỏ an toàn nếu câu đủ dài → `failed`; câu cảm thán
  ngắn không được split vì sẽ làm sai nội dung.
- Biến thể pitch chỉ là lớp trang trí sau inference: dùng WORLD vocoder để chỉ scale F0, giữ nguyên
  spectral envelope và aperiodicity; không dùng phase-vocoder hay `torchaudio.functional.pitch_shift`.
  Lỗi pitch hoặc không đủ voiced frame phải giữ waveform gốc, ghi warning và không retry TTS.
- Ngân sách frame VieNeu và giới hạn validation phải lấy từ cùng `segment_duration_policy`; codec VieNeu v3
  dùng 3.840 sample/frame ở 48 kHz. Mọi tổ hợp kind/pace/độ dài phải có headroom validation được test.
- Chỉ có `narration`/`dialogue`/`thought`; từ tượng thanh và cụm cảm thán giữ nguyên trong câu đọc bình thường.
  Không audio nào được cắt để lách validation; kết quả quá dài phải retry hoặc `failed`.
- Chapter còn segment `failed` không được publish.
- ASR mismatch dài bất thường chỉ được dùng để kết tội TTS khi transcript có thể tồn tại trong thời lượng WAV;
  transcript vượt tốc độ từ vật lý phải được đánh dấu là Whisper hallucination và không kích hoạt repair TTS.
- Mỗi lượt Whisper trực tiếp, lặp-ngắn, beam và greedy phải ghi evidence riêng theo đúng checksum WAV/policy.
  Lặp-ngắn chỉ được thay kết quả trực tiếp khi nó chuyển verdict thành `pass`; một kết quả lặp vẫn lỗi không được
  ghi đè transcript/similarity/WER trực tiếp tốt hơn. Evidence decode không được dùng thay final segment gate.
- Mỗi pronunciation tiếng Anh đã khóa và thực sự được thay trong `spoken_text` phải tạo anchor theo đúng ID/occurrence.
  ASR chỉ được chấp nhận spelling nguồn, spoken-form token hoặc dạng ghép token xác định; không fuzzy-alias tên khác.
  Tất cả occurrence phải gắn đúng vị trí bằng alignment toàn câu ở từng direct/repeat/beam/greedy decode; không được
  lấy một homograph ở vị trí khác để lấp tên bị sai. `ASR_INCONCLUSIVE` vẫn giữ precedence.
- ASR repair phải giữ nguyên speaker, voice profile, pitch và `spoken_text`; chế độ `clarity` chỉ hạ sampling variance.
  WAV clarity chỉ được commit `verified` khi beam và greedy đều `pass`. Repair round phải nằm trong signal checkpoint
  để crash/resume không bỏ qua lượt xác nhận kép hoặc vượt quá `asr.repair_rounds`.
- Mỗi WAV clarity phải được ghi vào candidate path bất biến riêng; không được thay file hoặc con trỏ SQLite của artifact
  đang giữ trước khi candidate qua đủ beam + greedy. Final quality-check, CAS đổi con trỏ segment và trạng thái `promoted`
  phải commit trong cùng một transaction. Candidate hỏng/mất file phải thành terminal `invalid`; hết budget phải đóng gate
  trên đúng checksum incumbent và giữ nguyên audio incumbent.
- Vocalization cực ngắn/kéo dài phải được chuẩn hóa thành âm tiết tiếng Việt ổn định. Output chạm đúng trần frame
  của VieNeu phải đi tiếp qua signal/Whisper validation, không được tự động coi là audio sai chỉ từ sample count.
  Nếu endpoint vẫn còn hoạt động ở đúng trần thì phải repair kể cả Whisper nhận đúng; không fade/cắt waveform để lách.
- Câu một hoặc hai từ có tối đa tám ký tự đọc được phải dùng ngân sách cực ngắn 24 frame. Nếu câu đó đã chạm
  trần frame rồi bị Whisper xác nhận lệch hoặc endpoint còn hoạt động, repair tiếp theo phải giảm xuống 12 frame để
  chặn VieNeu đọc thêm; câu chỉ có một ký tự đọc được giảm xuống 6 frame. Cap repair phải checkpoint riêng trong
  SQLite, giữ qua các vòng ASR, failure và resume, rồi chỉ xóa sau khi ASR pass; không áp dụng giảm repair cho lần tạo đầu.
- TTS circuit breaker chỉ đếm failure hoàn toàn liên tiếp cùng signature và phải reset sau một segment thành công.
- Mọi kết thúc với `BookStatus.ERROR` phải gửi `finished.ok=false`; nhánh `completed_with_errors` gửi đúng
  một Windows notification nếu policy cho phép, đồng thời giữ nguyên checkpoint/chapter đã commit.
- Không giữ TTS và Whisper đồng thời trên GPU khi không cần.
- Trên Windows, sau khi unload VieNeu hoặc Whisper phải trim working set của worker để các trang model
  không còn dùng được trả về hệ điều hành trước khi nạp model kế tiếp.
- Sau mỗi attempt VieNeu đã trả waveform hoặc lỗi, phải thu hồi object rác và CUDA allocator cache tại ranh giới an toàn.
- RAM critical đơn lẻ phải unload model/cache rồi đo cưỡng bức lại; chỉ chuyển book sang `critical_stop` và gửi notification
  nếu lần đo sau thu hồi vẫn critical. Critical SSD hoặc nhiệt GPU vẫn dừng ngay.
- Khi foreground pressure xuất hiện: hoàn thành đơn vị inference hiện tại, checkpoint, ngừng cấp việc mới, giảm tải/unload nếu cần.
- Không kill CUDA giữa kernel chỉ để nhường tài nguyên.
- Khi resume, settings hash và voice mapping phải giữ nguyên.
- TXT phải được decode từ đúng byte đã hash; ưu tiên BOM/UTF-8/CP1258 và chỉ thử UTF-16 không BOM khi có NUL heuristic.
- Pronunciation confidence được lưu trong SQLite; cùng một text đã chuyển cách đọc phải được dùng cho TTS và expected ASR.
- Chuẩn hóa pronunciation phải validate và checkpoint theo từng tên. Kết quả hợp lệ không được bỏ chỉ vì tên khác
  trong batch lỗi; resume chỉ xử lý phần chưa khóa. Lỗi ranh giới âm tiết có thể sửa cơ học an toàn như
  `A-der-on → A-đe-ron`; nếu không sửa được, retry chỉ tên lỗi với feedback cụ thể, không gửi lại nguyên prompt/batch.
- Trước khi finalize casting, mọi token tên Latin viết hoa (kể cả chỉ xuất hiện một lần) phải qua bước chuẩn hóa tên:
  CMUdict cục bộ cung cấp ARPAbet và bắt buộc tên tiếng Anh được chuyển thành âm tiết thuần Việt; tên fantasy ngoài
  từ điển do Qwen phân loại theo ngữ cảnh. Kết quả chuyên biệt hợp lệ phải `locked=1` trong SQLite để cùng một tên
  không đổi cách đọc theo giọng, chapter, confidence threshold hoặc lần resume.
- Mọi normalized speaker name dùng đúng một character và một voice profile trên toàn sách; cùng tên không được
  đổi preset theo chapter, cảm xúc hoặc khi resume. Không hợp nhất hai tên khác nhau vì đổi tên/thân phận/chuyển sinh.
- Cảm xúc chỉ thay đổi sampling, pace và mức âm lượng mục tiêu trên cùng preset. Không dùng cue phi ngôn ngữ thử nghiệm
  của VieNeu và không thay identity giọng để giả lập cảm xúc.
- Chuẩn hóa các cách viết như `haizzzzz`, `hừmmmm` hoặc `[thở dài]` chỉ được áp dụng lên `spoken_text` dùng chung cho
  TTS và expected ASR; văn bản nguồn, hash và segment đã checkpoint không được sửa.
- Preset được phân bổ theo giới tính và ưu tiên dùng hết pool phù hợp trước khi tái sử dụng. Trong cùng mức sử dụng,
  giọng tự nhiên miền Bắc đứng đầu, tiếp theo là giọng tự nhiên miền Nam; các giọng còn lại giữ thứ tự cũ.
- Pitch âm phải theo giới hạn từng preset đo trên preview: Phạm Tuyên không hạ; Xuân Vĩnh, Thái Sơn,
  Ngọc Trân tối đa `-1`; các preset không tin tức còn lại tối đa `-2`; pitch dương tối đa `+2`.
- NPC có nhãn cục bộ được giữ identity riêng trong phạm vi chapter/batch; NPC không phân biệt được
  ít nhất phải tách pool nam, nữ và chưa rõ giới tính.
- Nhãn NPC cục bộ trùng chính xác với tên nhân vật trong cùng chapter phải được hợp nhất trước khi
  phân vai, tránh cùng một người bị khóa hai giọng hoặc hai pitch khác nhau.
- Tên trong lời gọi trực tiếp như `Anh Lucien!` hoặc `Iven, ...` là addressee, không phải bằng chứng về speaker.
  Nếu analysis vẫn gán tên đó làm người nói, validation phải tách thành NPC cục bộ `người gọi <tên>`, áp dụng
  nhất quán cho cùng local speaker trong batch và ghi event `ADDRESSEE_SPEAKER_REPAIRED`.
- Segment mới được cân theo K-weighted LUFS; giọng kể có anchor nhỉnh hơn hội thoại trung tính và
  chênh lệch `loud` phải tiết chế. Sample peak cap vẫn bắt buộc sau khi áp gain.
- Ngoặc kép kéo dài qua nhiều paragraph phải giữ state hội thoại; ngoặc đơn cong `‘…’` là hint
  độc thoại nội tâm và mọi segment `thought` bắt buộc dùng `NARRATOR`, không gắn với character identity.
- Whisper phải nhận WAV đã đọc/resample trong process; không truyền đường dẫn cho API Whisper vì bản
  dependency hiện tại sẽ gọi FFmpeg subprocess cho từng segment và gây nháy console trên Windows.
- Recovery xóa `.part`, reset stage dở và chỉ reuse artifact có checksum + validation hợp lệ.
- Project `completed` được fast-path nếu toàn bộ chapter/full-book MP3 còn decode + checksum hợp lệ.
- Dừng cưỡng bức phải kết thúc process con trước process worker để không bỏ lại FFmpeg/Ollama helper.
- Ollama ẩn phải ghi stdout/stderr vào `runtime/logs/ollama-server.log`; không bỏ mất bằng `DEVNULL`.
- Stream Ollama kết thúc thiếu `done=true` phải chia đôi batch hiện tại và chạy batch con; không retry nguyên
  batch lớn nhiều lần. Segment chỉ còn một phần tử mới dùng retry thông thường.
- Phản hồi Ollama đã kết thúc nhưng thiếu ID segment bắt buộc được retry theo policy; nếu batch nhiều phần tử
  vẫn thiếu sau các lần retry, phải chia đôi batch và tiếp tục. Chỉ được kết luận lỗi bắt buộc khi batch đơn
  không thể tạo đủ kết quả hợp lệ.
- Phản hồi analysis đúng schema vẫn phải qua semantic delivery gate trước checkpoint. `notes` chỉ có dấu câu,
  emotion `happy` mâu thuẫn, hoặc cả batch bị co về `neutral/intensity=0/normal` dù có nhiều cue cảm xúc rõ ràng
  phải bị từ chối; gate ghi đúng cue đã khớp và gửi feedback cụ thể
  vào lần retry và chia đôi batch nếu vẫn sai. Nhãn đồng nhất đơn thuần không đủ để kết tội một batch hợp lệ.
- Một segment có đúng signature `neutral/intensity=0/pace=normal/volume=normal` và cue cảm xúc mạnh phải bị
  từ chối riêng ở mọi `kind`, kể cả khi batch đã chia xuống dưới ngưỡng dominance hoặc singleton. Với dialogue/thought,
  `neutral` vẫn bị từ chối khi có cue trực tiếp, trừ trường hợp thật sự có cả affect dương và âm; cue nằm đúng phạm vi
  phủ định/ngăn cấm không được tính là mâu thuẫn.
- Profile `high_quality` bắt buộc chạy một lượt director critic thứ hai trên candidate analysis bất biến. Critic không
  được thấy confidence, notes hoặc personality tự chấm của generator; response phải có đúng schema, đúng một verdict
  cho mọi ID và khớp chính xác candidate hash. Critic dùng cùng model chỉ là self-review có tương quan, không phải model
  độc lập, nên không bao giờ được vượt qua semantic gate tất định hoặc biến một field khác candidate thành pass.
- Confidence được commit phải nằm trên ngưỡng khóa và không vượt cap của director. Model name + digest Ollama phải được
  khóa bền ở cấp book, kiểm tra lại trước và sau mọi request generator, critic và pronunciation; tag/digest đổi giữa
  request hoặc giữa hai lần resume phải fail-closed. Project high-quality legacy đã có analysis checkpoint nhưng chưa có
  critic contract không được trộn dữ liệu cũ/mới; phải tạo project sạch.
- Batch được critic chấp nhận, event evidence và pronunciation proposal đã validate phải commit trong cùng một transaction
  SQLite với CAS trên ID, source hash và trạng thái segment. Crash không được để lại batch analyzed thiếu event hoặc thiếu
  pronunciation; retry critic/schema giữ nguyên candidate hash, còn singleton persistent failure phải dừng hữu hạn.
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
- `cli.py`: CLI headless create/run/resume/status/stop/log/validate/report/doctor/test; nhánh quan sát là read-only.
- `background_runner.py`: supervisor ẩn, handshake, process identity, persistent stop request và event log.
- `pipeline.py`: orchestration và state transition.
- `database.py`: schema/transaction API.
- `analysis.py`: Qwen structured analysis.
- `character_registry.py`: canonical speaker name và voice mapping; không hợp nhất identity khác tên.
- `tts.py`: VieNeu preset adapter, emotion delivery và deterministic retry.
- `asr.py`: Whisper và transcript metrics.
- `audio_io.py`: validation, atomic audio, playlist.
- `resource_manager.py`: resource snapshot/decision.
- `recovery.py`: integrity/checksum recovery.
- `notifier.py`: Windows notifications.
- `process_utils.py`: kết thúc an toàn cây process worker/native helper.
- `scripts/start_windows.ps1`: hiện một console ngay khi khởi động, báo tiến độ trong lúc kiểm tra runtime/nạp GUI,
  mở app bằng `pythonw.exe` và tự đóng console theo ready marker do GUI ghi sau khi cửa sổ đã render;
  mọi output được append vào `runtime/logs/startup.log`; lỗi được bắt ở boundary ngoài cùng và console
  phải giữ mở cho tới khi người dùng chủ động nhấn phím/đóng cửa sổ.
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
python -m compileall -q ebook_reader tests scripts
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
