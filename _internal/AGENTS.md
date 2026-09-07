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

- **Trong lúc pha phân tích chạy, đừng chạy việc nặng nào khác trên máy** — kể cả `pytest`.
  Phân tích của dự án này tái lập hoàn hảo: alpha.48, .49 và .51 giống nhau **từng byte**.
  alpha.52 lệch **54 phân vai** so với cả ba, và hình dạng là *một* nhóm lệch ở thứ 45/201 rồi
  lan ra 57 nhóm phía sau, vì registry nhân vật mang cái lệch ấy đi tiếp. Lúc nhóm 45 chạy thì
  tôi đang chạy một lượt pytest đầy đủ. Chưa chứng minh được nhân quả (một quan sát, không phải
  thí nghiệm), nhưng chờ thì tốn **không gì cả**, còn đoán sai thì tốn cả một quỹ đạo phân tích.
  Chi tiết: `docs/VERSIONS.md`.
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
- **Ba tầng biến đổi giọng, đừng trộn lẫn.** Người nghe tiếng Việt so cùng một câu từ `-6` đến `+6` bán âm
  (F0 từ 106 Hz lên 206 Hz) và nghe ra **cùng một người**, chỉ khác trạng thái — điềm tĩnh, gấp gáp. Dịch F0
  là **cách thể hiện**, không phải danh tính. Nhận diện người nói nằm ở **formant**.
  - *Danh tính nhân vật* ← `formant_ratio`, khoá theo nhân vật cả sách. Dải **riêng cho từng preset**,
    suy từ chiều dài khoang miệng đo bằng Praat trên chính preview của nó (`L = 5c / 4F3`). Warp hệ số `r`
    đọc ra thành khoang miệng dài `L/r`, nên dải hợp lệ là phần giữ `L/r` trong khoảng người lớn
    `12,8`–`19,7` cm. Preset nam đo được `16,4`–`16,9` cm, nữ `13,9`–`15,5` cm — nên nam **còn ít chỗ đi
    trầm, nhiều chỗ đi sáng**, nữ thì ngược lại. Một dải chung là sai theo hai hướng ngược nhau. Cận trên
    tái lập đúng giới hạn người nghe tìm ra bằng tai: Thanh Bình `0,82` nghe tù bí (khoang `20,6` cm),
    `0,86` chấp nhận được (`19,7` cm). **Phải giao với ràng buộc thứ hai, độc lập với giải phẫu:** phép
    biến đổi tự nó xuống cấp khi hệ số rời xa `1,0`, bất kể giọng gốc là gì. Mốc này **bất đối xứng và
    đảo chiều theo giới**: giọng nam chịu được sáng hơn nhiều hơn là trầm đi (`-0,15 / +0,20`), giọng nữ
    ngược lại (`-0,20 / +0,15`). Hai ràng buộc chặn **hai đầu ngược nhau** tuỳ giọng: giọng nam khoang dài bị giải phẫu chặn
    phía trầm và thuật toán chặn phía sáng, giọng nữ khoang ngắn thì đảo lại. Kiểm chứng: giao của hai
    ràng buộc cho Thanh Bình ra đúng `[0,86, 1,20]` — chính là dải người nghe chốt bằng tai trước khi đo
    bất cứ thứ gì.
  - **Hai tác vụ độc lập, hai engine khác nhau, mỗi cái là cái được duyệt bằng tai cho đúng việc đó.**
    Chất giọng nền là đổi **F0** → dùng **WORLD** (`apply_pitch_variant`), vì nó giữ nguyên envelope nên
    kết quả luôn là cấu hình khoang miệng có thật, và vòng round-trip của nó chỉ tốn `-0,015` MOS.
    Danh tính nhân vật là đổi **formant** → dùng **Praat**. Gộp cả hai vào một lệnh Praat sẽ biến phần
    chỉnh F0 thành PSOLA — không phải thứ đã được duyệt cho nó.
  - Phép biến đổi formant dùng **Praat "Change gender"** qua parselmouth, không dùng WORLD warp hay PARCOR. Praat
    resample để dời formant rồi PSOLA khôi phục cao độ — **không bao giờ ước lượng hay dựng lại phổ**.
    So bằng tai: PARCOR tệ rõ rệt, WORLD không phân biệt được với Praat. UTMOSv2 xếp ngược lại nhưng nó đã
    ba lần mâu thuẫn với người nghe ở đúng vùng này, nên không dùng nó để chọn.
  - *Cách thể hiện* ← F0 và sampling, theo từng câu, do đạo diễn quyết.
  - *Chất giọng nền của preset* ← `PRESET_BASE_PITCH_SEMITONES`, hiệu chỉnh một lần bằng tai cho mỗi preset.
    Giá trị này **không** bị chặn bởi `PRESET_MIN_PITCH_SEMITONES` — giới hạn đó suy từ baseline UTMOSv2,
    mà UTMOSv2 đã hai lần mâu thuẫn với tai người nghe ở đúng vùng này.
- Biến đổi giọng là lớp trang trí **sau inference và sau toàn bộ thẩm định**: áp ở bước ghép chương, không
  áp lúc sinh audio. Segment WAV đã verify là bất biến; mọi gate chấm bản gốc. Vòng WORLD tính thuế phẳng
  `~0,27` MOS và `~0,06` WER bất kể dịch nhiều hay ít — chấm bản đã dịch chỉ là đo chính phép biến đổi, và
  đó là thứ từng làm segment bị dịch fail gấp 3,4 lần một cách vô cớ.
- Dùng WORLD vocoder: scale F0 và warp spectral envelope theo trục tần số; không dùng phase-vocoder hay
  `torchaudio.functional.pitch_shift`. Đo thực tế: rubberband (có sẵn trong FFmpeg của project, chế độ giữ
  formant) tệ hơn WORLD `0,2`–`0,3` MOS ở cả hai chiều. Lỗi pitch hoặc không đủ voiced frame phải giữ
  waveform gốc, ghi warning và không retry TTS.
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
  ASR chỉ được chấp nhận spelling nguồn, spoken-form token, dạng ghép token xác định, hoặc token có **chuỗi phoneme
  tiếng Việt bằng đúng** spoken form (`gi` và `d` cùng là /z/ nên `Giôn` và `dôn` là một âm). Đây vẫn là phép so bằng,
  không phải ngưỡng khoảng cách: `Lucy` vẫn không thể thỏa anchor của `Lucien`. Tuyệt đối không fuzzy-alias tên khác.
  Tất cả occurrence phải gắn đúng vị trí bằng alignment toàn câu ở từng direct/repeat/beam/greedy decode; không được
  lấy một homograph ở vị trí khác để lấp tên bị sai. `ASR_INCONCLUSIVE` vẫn giữ precedence.
- Anchor tên riêng **không có quyền chặn publish**. Whisper là model đa ngữ thiên lệch tiếng Anh: nó viết `Giô-en`
  đọc đúng thành "joanne" và `Ai-vân` thành "ivan", nên chính tả nó chọn **không phải bằng chứng về cách phát âm**.
  Anchor không khớp sinh evidence review; quyền fail thuộc về similarity/WER cấp câu, đo trên text canonical.
  Trong metric canonical, anchor không khớp phải được canonical hóa ở **cả hai vế** để một bất đồng về tên không bị
  tính lỗi hai lần — trước đây nó vừa bị anchor bắt vừa làm phồng WER, đẩy câu ngắn vượt ngưỡng chỉ vì cái tên.
  Anchor bị bỏ hẳn khỏi transcript (`delete_anchor`) vẫn tính là lỗi. Miễn trừ này chỉ hợp lệ khi còn đủ nội dung
  thường để tự đứng vững: dưới `CANONICAL_ANCHOR_WAIVER_MIN_ORDINARY_TOKENS` token thường thì anchor giữ nguyên
  quyền hard-fail, vì bỏ tên khỏi "Anh Lucy" là không còn gì để kiểm. Repair vẫn chạy đủ vòng; chỉ trạng thái cuối
  đổi từ `failed` thành publish kèm `ASR_LOCKED_NAME_ANCHOR_REVIEW`. Caller không truyền ngưỡng canonical thì giữ
  nguyên hành vi hard-fail cũ.
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
- Pronunciation chỉ được lưu theo **từng từ**. Entry nhiều từ phải được tách thành một entry cho mỗi từ;
  không tách được (số từ hai vế lệch nhau) thì bỏ hẳn, vì các từ vẫn có đề xuất riêng trong cùng batch.
  Mỗi từ tách ra phải qua đúng bộ lọc như khi đứng một mình. Lý do: entry đã khóa được khóa theo
  `normalized_surface` của chính nó, nên `Lucien Evans` và `Lucien` không bao giờ đụng nhau — một lần chạy
  thật đã khóa cùng một nhân vật thành cả `Lu-si-en` lẫn `Lư-xi-ên`, và người nghe nghe ra hai cái tên khác nhau.
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
- **Biến thể pitch là nguyên nhân hỏng chất lượng lớn nhất đo được, không phải preset hay vùng miền.**
  Trên 597 segment của ba lần chạy: `pitch = 0` fail **2,8%** với WER trung vị `0,050`; `pitch ≠ 0` fail
  **9,4%** với WER trung vị `0,154` — tệ hơn 3,4× và 3×. UTMOSv2 nói cùng một điều một cách độc lập: dịch
  `-1` bán âm làm mất `0,33`–`1,17` MOS tuỳ preset. Người nghe tiếng Việt còn **không nhận ra đó là giọng
  của preset gốc nữa**, nên pitch không chỉ hạ độ tự nhiên mà đổi luôn nhận diện giọng.
  `PRESET_MIN_PITCH_SEMITONES` hiện giới hạn theo **khả năng dịch cao độ** đo trên preview, chứ không theo
  **cái giá phải trả**. Đừng đổ lỗi cho một preset khi số liệu chỉ vào biến thể pitch của nó: `Xuân Vĩnh`
  ở `pitch 0` fail **0/13**, còn các biến thể `-1/+1/+2` của chính nó fail 25–33%.
- Whisper sai **thanh điệu** tiếng Việt ở mọi segment, cả đạt lẫn fail — verified median `0,000` nhưng p99
  `0,362`, so với median `0,296` của segment fail, và có segment đạt với tỉ lệ `1,000`. Hai phân bố không
  tách nhau, nên chênh lệch thanh **không mang tín hiệu** về chất lượng take. Content gate vì thế gấp thanh
  ra khỏi phép đo và lấy kết quả tốt hơn giữa hai cách đọc, để phép gấp **không bao giờ** làm fail thứ mà
  so chữ đã cho qua. Hệ quả phải nói rõ: ASR gate không còn phát hiện lỗi thanh của TTS — nhưng nó vốn cũng
  chưa từng phát hiện được, vì không phân biệt nổi lỗi thanh của TTS với lỗi thanh của ASR.
- Miễn trừ anchor tên riêng phải **theo tỉ lệ**, không theo số token tuyệt đối: tên không được chiếm đa số
  những gì đang kiểm, và phải còn ít nhất hai token thường. `Giô-en cười trừ` còn 2 token thường trên tên
  2 token nên vẫn kiểm được; `Anh Lu-si-en` chỉ còn `anh` trên tên 3 token nên anchor giữ quyền hard-fail.
- Giọng miền Trung **không bao giờ được phân vai**, kể cả cho NPC, kể cả qua nhánh fallback khi pool cạn.
  Tiếng Trung là phương ngữ khó hiểu nhất với người nghe hai miền còn lại, và hệ thanh điệu của nó lệch xa
  nhất so với chính tả chuẩn miền Bắc mà audiobook đọc từ đó; đo trên audio đã commit, preset Trung sai thanh
  ở **từ thường** chứ không phải ở tên riêng (`khốn kiếp` → `khôn kiêp`), mà thanh điệu mang nghĩa từ vựng.
  Preset vẫn nằm trong catalog vì VieNeu có chúng và sách cũ có thể đã khóa chúng — chỉ là không được cast.
  Mọi đường dẫn tới preset đều phải tôn trọng `CASTING_REGIONS`; một fallback quét cả catalog sẽ đưa chúng
  quay lại sách.
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
  nhất quán cho cùng local speaker trong batch. Repair marker chỉ được dùng tạm trong validation; projection speaker
  đã sửa mới là dữ liệu được candidate ledger và critic khóa.
- Segment mới được cân theo K-weighted LUFS; giọng kể có anchor nhỉnh hơn hội thoại trung tính và
  chênh lệch `loud` phải tiết chế. Sample peak cap vẫn bắt buộc sau khi áp gain.
- **Mọi target loudness phải nằm trong khả năng vật lý của trần peak.** Cân mức là
  `min(loudness_gain, peak_safe_gain)` và master chương cũng không vượt được trần true-peak, nên target cao hơn
  `trần − crest factor` chỉ có thể trượt. Giọng nói TTS tiếng Việt đo được crest median 17,6 dB, xấu nhất 20,6 dB
  ở segment và 17,9 dB trên cả chương. Vì chương được master về một target chung ở cuối nên **chỉ tương quan giữa
  các segment mới quan trọng**: hạ đều anchor cho tới khi peak cap không còn chạm là cách sửa đúng, không dùng
  nén động hay limiter. UTMOSv2 bất biến với mức âm lượng (lệch MOS trung bình `-0,006` ở `-6 dB`) nên hạ anchor
  không mất điểm tự nhiên. `test_loudness_targets_stay_inside_the_peak_ceiling_speech_allows` khóa ràng buộc này.
- `segment_endpoint_floor_dbfs` đo trên WAV **đã cân mức** nên phải dịch theo anchor loudness; còn
  `segment_active_floor_dbfs` đo trên waveform **trước gain** nên phải giữ nguyên. Trộn hai cái này lại sẽ âm thầm
  làm gate "endpoint còn hoạt động ở trần frame" mất độ nhạy.
- Ngoặc kép kéo dài qua nhiều paragraph phải giữ state hội thoại; ngoặc đơn cong `‘…’` là hint
  độc thoại nội tâm và mọi segment `thought` bắt buộc dùng `NARRATOR`, không gắn với character identity.
- Với profile `high_quality`, batching phải giữ nguyên source unit gồm các segment cùng paragraph và phần tiếp nối của
  cùng một ngoặc kép ngoài qua nhiều paragraph. Source unit không quá cap 5 segment không được chia lại khi retry; unit
  vượt cap mới được hard-split hữu hạn. Lời dẫn narration cùng paragraph phải đi chung với lượt thoại để attribution không
  bị cắt khỏi speaker.
- Whisper phải nhận WAV đã đọc/resample trong process; không truyền đường dẫn cho API Whisper vì bản
  dependency hiện tại sẽ gọi FFmpeg subprocess cho từng segment và gây nháy console trên Windows.
- Recovery xóa `.part`, reset stage dở và chỉ reuse artifact có checksum + validation hợp lệ.
- Project `completed` được fast-path nếu toàn bộ chapter/full-book MP3 còn decode + checksum hợp lệ.
- Dừng cưỡng bức phải kết thúc process con trước process worker để không bỏ lại FFmpeg/Ollama helper.
- Ollama ẩn phải ghi stdout/stderr vào `runtime/logs/ollama-server.log`; không bỏ mất bằng `DEVNULL`.
- Lỗi transport Ollama (`ConnectionError`, `Timeout`, `ChunkedEncodingError`) tuyệt đối không được kết thúc cả book.
  Kết nối chết trước khi nhận được ký tự response nào là replay an toàn: request được gửi lại tối đa
  `OLLAMA_TRANSPORT_RECONNECT_ATTEMPTS` lần trong cùng attempt đã reserve, có backoff và vẫn tôn trọng wall timeout
  cùng stop request. Khi đã nhận một phần response thì không được replay vì stream không còn tái lập được.
  Transport fault thoát ra khỏi lớp replay trong lượt director critic bền phải tiêu đúng attempt đã reserve giống hệt
  một lần crash sau reserve, ghi event `ANALYSIS_CRITIC_TRANSPORT_FAULT`, rồi để vòng lặp durable đọc lại candidate và
  đi tiếp; hết ngân sách thì rơi vào nhánh terminal/split thông thường, không raise xuyên pipeline.
- Stream Ollama kết thúc thiếu `done=true` phải chia đôi batch hiện tại và chạy batch con; không retry nguyên
  batch lớn nhiều lần. Segment chỉ còn một phần tử mới dùng retry thông thường.
- Phản hồi Ollama đã kết thúc nhưng thiếu ID segment bắt buộc được retry theo policy; nếu batch nhiều phần tử
  vẫn thiếu sau các lần retry, phải chia đôi batch và tiếp tục. Chỉ được kết luận lỗi bắt buộc khi batch đơn
  không thể tạo đủ kết quả hợp lệ.
- Phản hồi analysis đúng schema vẫn phải qua semantic delivery gate trước checkpoint. Emotion `happy` mâu thuẫn
  hoặc cả batch bị co về `neutral/intensity=0/normal` dù có nhiều cue cảm xúc rõ ràng
  phải bị từ chối; gate ghi đúng cue đã khớp và gửi feedback cụ thể
  vào lần retry và chia đôi batch nếu vẫn sai. Nhãn đồng nhất đơn thuần không đủ để kết tội một batch hợp lệ.
- Một segment có đúng signature `neutral/intensity=0/pace=normal/volume=normal` và cue cảm xúc mạnh phải bị
  từ chối riêng ở mọi `kind`, kể cả khi batch đã chia xuống dưới ngưỡng dominance hoặc singleton. Với dialogue/thought,
  `neutral` vẫn bị từ chối khi có cue trực tiếp, trừ trường hợp thật sự có cả affect dương và âm; cue nằm đúng phạm vi
  phủ định/ngăn cấm không được tính là mâu thuẫn.
- Narration có đồng thời bằng chứng tổn thương hô hấp nghiêm trọng và suy giảm ý thức không được checkpoint thành
  `neutral/intensity=0`; một mô tả thể chất hoặc quan sát lâm sàng đơn lẻ không đủ để kích hoạt rule này.
- Hai cue narration nguồn hẹp `narration_recalled_persistent_fear` và `narration_stunned_blank_mind` phải khóa
  nguyên `kind=narration` và lần lượt chỉ cho phép emotion `afraid` hoặc `surprised`. Predicate nguồn dùng chung với
  DB replay là thẩm quyền duy nhất; không lan cue từ hàng xóm, không tự sửa output model và không dùng khóa này để
  bỏ qua director critic.
- Rule `narration_sleep_paralysis_helplessness` chỉ được kích hoạt cho grammar nguồn allowlist: đúng tiền tố
  `giống như mấy lần`, đúng chủ thể trực tiếp, hoặc `giống như <đúng chủ thể>`; sau đó phải có liền mạch
  bóng đè -> nhận thức đang mơ -> muốn thoát -> bất lực điều khiển cơ thể, cùng một chủ thể và không có phủ định,
  giả định, lời trích, meta, affect đối nghịch hoặc trạng thái đã giải quyết. Rule khóa đồng thời
  `kind=narration` và `emotion=afraid`; câu kể ngôi ba “cậu biết... muốn...” không phải thought trực tiếp.
- Rule affect nguồn hẹp phải chạy trước semantic cue chung. Constraint deterministic đã phát hiện phải được tích lũy trong
  suốt retry của cùng target group, không được ghi đè bởi lỗi của lần sau hoặc chuyển thành feedback tự do.
- Mọi `allowed_emotions` source-authoritative từ host affect/physical-collapse phải khóa schema generator ở lần retry theo
  đúng ID bằng `segments.items.oneOf`; nhiều host constraint cùng ID phải lấy giao và giao rỗng phải fail-closed trước HTTP.
  `allowed_emotions` của `SEMANTIC_DELIVERY_MISMATCH` chỉ là advisory và tuyệt đối không được thu hẹp schema emotion.
- Khi một target group bị chia, toàn bộ feedback typed đã tích lũy của group cha phải được lọc theo `stable_id` rồi chuyển
  vào đúng group con trong cùng lượt phân tích. Không được để split làm mất constraint của câu đã sửa; source unit
  high-quality vẫn giữ nguyên tử theo invariant batching ở trên.
- `DIRECTOR_FIELD_MISMATCH` phải gửi lại cho generator projection advisory canonical của critic, nhưng chỉ cho các field
  delivery allowlist `emotion|intensity|pace|volume`; không chuyển kind, speaker, source text, quote hoặc rationale.
  Projection này không phải host lock và không được thu hẹp schema. Retry sinh lại từ đầu nên giá trị đã sửa phải được giữ
  qua các lượt/split; correction mới chỉ ghi đè đúng field nó thay đổi, còn field critic vừa đồng ý phải tiếp tục được nhắc.
- Semantic cue chung chỉ được dùng `allowed_emotions` source-derived làm lựa chọn retry advisory khi chính candidate
  `emotion=neutral` bị từ chối. Tập lựa chọn phải hợp deterministic từ cue trực tiếp không bị phủ định/meta/lịch sử và
  không có affect đối nghịch, không chứa source/cue/rationale trong payload. Đây không phải host whitelist, semantic lock
  hay exact-membership gate: model vẫn phải chọn delivery tốt nhất và candidate sửa xong vẫn qua đủ validation + critic.
- Ba cue nhận thức mơ hồ `thất thần|bàng hoàng|hỗn loạn` thuộc lớp nội bộ `disoriented`: chúng là bằng chứng chống
  `happy` sai nhưng không được coi là cue trực tiếp để từ chối `neutral`, không tạo `allowed_emotions` và không tự ép
  thành `afraid`/`surprised`. Cue sợ hãi rõ ràng cùng xuất hiện vẫn được xét độc lập theo contract `afraid`.
- Với narration/NARRATOR chỉ có đúng cue active `disoriented`, không có dấu hỏi/cảm thán và candidate tiết chế
  `neutral`, intensity `0|1`, pace/volume `normal`, host được phép giữ candidate trước critic tự-review suy diễn
  `afraid` kèm ít nhất một escalation intensity hoặc pace. Override compatibility chỉ được phủ tập con
  `emotion,intensity,pace`; mọi cue affect khác, delta `kind/speaker/volume`, intensity không tăng, pace không thành
  `fast` hoặc emotion khác `afraid` đều phải fail-closed. Raw verdict/delta vẫn lưu đầy đủ; SQLite phải dựng lại exact
  rule từ source text/hash, source kind, candidate, critic và partition khi critic completion, reopen và commit.
- Candidate qua rule affect nguồn hẹp phải mang semantic lock source-bound vào critic row và durable clearance. Với lock một
  field, critic correction chỉ được host override khi có delta duy nhất trên field khóa và giá trị đề xuất nằm ngoài tập host
  cho phép. Riêng rule bảo vệ cả source kind và emotion được phép compose hai override đúng hai field đó; mọi raw verdict/delta
  vẫn phải lưu và `intensity/pace/speaker/volume` không được che. Không delta được host suy là agreement; mọi delta chưa được
  lock bao phủ hoặc đổi giữa hai giá trị đều được host cho phép phải fail-closed. Chỉ cần một verdict trong payload critic sai
  protocol thì toàn payload là `critic_invalid` và retry nguyên durable candidate, không lưu nửa batch thành rejected evidence.
- Profile `high_quality` bắt buộc chạy một lượt director critic thứ hai trên candidate analysis bất biến. Critic không
  được thấy confidence, notes hoặc personality tự chấm của generator; response phải có đúng schema, đúng một verdict
  cho mọi ID và khớp chính xác candidate hash. Critic dùng cùng model chỉ là self-review có tương quan, không phải model
  độc lập, nên không bao giờ được vượt qua semantic gate tất định. Field delta chỉ có thể thành pass qua structural lock,
  semantic/source-kind lock hoặc compatibility override `disoriented` hẹp đã mô tả và được DB replay độc lập ở trên.
- Director critic cho source `kind_hint=thought` chỉ nhận `previous_context_only`: giữ đúng source trước liền kề để hiểu
  lời dẫn/attribution nhưng bắt buộc để `next_text` rỗng, ngăn sự kiện tương lai cho mượn emotion/intensity/pace/volume
  vào suy nghĩ hiện tại. Generator vẫn nhận adjacent context; narration/dialogue critic thông thường vẫn dùng
  `adjacent_context`.
- Director critic cho source narration đứng ngay trước source thought ở paragraph kế tiếp phải dùng
  `narration_precedes_next_paragraph_thought`: giữ previous source nhưng xóa `next_text` để thought tương lai không cho
  mượn câu hỏi, kind hoặc affect vào target. Đây chỉ là context mask: generator vẫn nhận adjacent context, policy không tự
  tạo `host_locked_fields`, semantic clearance, feedback constraint hay source-kind override. Raw critic verdict/delta vẫn
  phải được lưu và mọi dissent chưa có authority độc lập vẫn fail-closed. Semantic lock nguồn khác vẫn được compose bình
  thường. SQLite phải tính lại context hash từ current + neighbor stable ID, text SHA, chapter, seq, paragraph và kind ở
  allocate/reopen/critic completion/commit; policy, neighbor hoặc lock/override bị chèn sửa phải bị từ chối.
- Source `kind_hint=dialogue` phải tạo kind-only host lock `dialogue` trong generator/critic contract. Lock này chỉ bảo vệ
  ranh giới lời nói, tuyệt đối không cấp authority cho speaker: critic dissent chỉ trên kind có thể được source-bound override,
  nhưng mọi delta speaker vẫn unresolved và làm row fail-closed. SQLite phải tái dựng lock từ source text/hash/kind khi
  allocate, reopen, critic completion và commit; evidence thiếu lock, giả rule hoặc giả partition đều bị từ chối.
- Director critic cho narration là lời dẫn ngay trước source thought cùng chapter và paragraph phải dùng
  `narration_before_thought_previous_only`: giữ previous source nhưng xóa `next_text` từ immutable original context.
  Source parser sở hữu bất biến `kind=narration`: generator vẫn nhận đủ adjacent context nhưng validation/feedback phải
  dùng chính immutable original context để từ chối relabel thành thought trước khi cấp candidate. Critic row mang
  kind-only host lock tách biệt semantic clearance; nếu critic vẫn đổi kind thì evidence phải giữ nguyên verdict/delta thô
  và chỉ được override đúng field `kind`. Override bền phải khóa stable ID + SHA-256 của target và thought kế tiếp;
  SQLite tính lại hash từ text related khi allocate/reopen/accept/commit. Mọi delta emotion/intensity/pace/speaker/volume
  chưa có semantic lock riêng vẫn unresolved và fail-closed; kind-only context lock không làm tăng semantic-lock count.
- Model không được sở hữu `notes` hoặc `personality_hint` được commit. Host phải tạo note canonical chỉ từ delivery cuối
  sau repair; personality model phải rỗng và segment note không được chứa marker điều khiển. Marker repair chỉ là state tạm
  trong một lượt validation và phải bị xóa trước candidate. Candidate ledger + critic khóa projection analysis đã chấp nhận;
  bước casting sau đó chỉ được phép reconcile speaker bằng phép biến đổi source-derived, deterministic và được khóa bằng
  fingerprint stage riêng. SQLite phải tính lại và từ chối note/personality/marker không canonical khi allocate, reopen,
  direct update và commit. Speaker repair không được sao chép note từ segment khác, và character registry không được dùng
  prose delivery làm personality hoặc dùng marker legacy làm quyền điều khiển identity.
- Tiêu đề chương chỉ được nhận diện bằng source metadata đầu chapter và grammar tiêu đề độc lập. Host phải khóa delivery
  tiêu đề về narrator trung tính cùng confidence candidate `0.95`, không gửi ngữ cảnh hàng xóm cho row đó và vẫn giữ
  nguyên proposal/confidence/verdict thô để audit. Critic confidence vẫn phải qua floor nhưng chỉ là evidence thô cho row
  cấu trúc; derived/validated/commit confidence của tiêu đề đã khóa phải luôn giữ đúng `0.95`, kể cả khi critic hoặc cap thấp hơn.
  Content row mới tính confidence commit bằng `min(generator, critic, cap)`.
  Structural override chỉ được phép cho đúng row đã khóa; mọi content row vẫn chịu critic bình thường. Mỗi verdict critic
  phải trích nguyên văn bằng chứng không rỗng từ chính text cùng ID, không được lấy bằng chứng từ row lân cận. Multi-row
  phải dùng canonical ordered per-ID source-anchor map: schema `items.oneOf` khóa từng nhánh vào exact ID + enum anchor,
  host kiểm exact membership và durable contract khóa map hash + tổng anchor count, không dùng union/substr tự do.
  Singleton có toàn bộ target dài từ 1 đến giới hạn quote phải khóa schema và contract vào exact
  full target + source hash. Singleton dài hơn giới hạn quote phải dùng tập source anchor deterministic, nguyên văn và không
  vượt giới hạn; schema chỉ chấp nhận đúng một anchor trong enum, còn contract bền phải khóa source hash, hash tập anchor và
  số anchor. Không được tự cắt, nối, chuẩn hóa hoặc chấp nhận một substring ngoài enum. Critic model không trả boolean accept:
  host suy agreement chỉ khi cả sáu delivery field không có delta, và evidence compatibility phải lưu accept đúng bằng kết
  quả host-derived đó.
- Với analysis bắt buộc ở profile `high_quality`, mọi content candidate dưới `low_confidence_threshold` phải bị từ chối
  bằng feedback số typed trước critic/candidate ledger. Prompt generator luôn phải mang đúng floor; schema áp floor trực tiếp
  cho batch không có tiêu đề, còn batch trộn tiêu đề+nội dung phải giữ proposal confidence thô của tiêu đề và dùng host gate
  để áp floor lên content. Tiêu đề cấu trúc được normalize trước gate này. Confidence được commit phải nằm trên ngưỡng khóa
  và không vượt cap của director. Contract critic phải khóa đúng floor/cap trong schema + prompt, evidence policy + target hash
  + anchor-set hoặc per-ID anchor-map hash/count;
  confidence dưới floor, rationale lỗi và evidence quote lỗi phải có reason host-derived riêng trong durable outcome.
  Model name + digest Ollama phải được
  khóa bền ở cấp book, kiểm tra lại trước và sau mọi request generator, critic và pronunciation; tag/digest đổi giữa
  request hoặc giữa hai lần resume phải fail-closed. Project high-quality legacy đã có analysis checkpoint nhưng chưa có
  critic contract không được trộn dữ liệu cũ/mới; phải tạo project sạch.
- Batch được critic chấp nhận, event evidence và pronunciation proposal đã validate phải commit trong cùng một transaction
  SQLite với CAS trên ID, source hash và trạng thái segment. Crash không được để lại batch analyzed thiếu event hoặc thiếu
  pronunciation; retry critic/schema giữ nguyên candidate hash, còn singleton persistent failure phải dừng hữu hạn.
- Candidate analysis high-quality phải có hai identity tách biệt: hash projection delivery mà critic nhìn thấy và hash
  acceptance envelope đầy đủ gồm source, metadata, confidence và pronunciation. Intent critic phải được reserve bền trước
  HTTP; mọi attempt, generator contract và kết quả phải re-hash khi đọc. Crash sau reserve tiêu attempt hiện tại, crash sau
  `critic_accepted` phải commit lại đúng envelope mà không gọi model, còn candidate projection lặp lại không được reset budget.
- Policy/group/context fingerprint của ledger phải khóa model digest, system/schema version, source hash và metadata ngữ cảnh
  mà host dùng (stable ID, chapter, paragraph, kind và hàng xóm). Parent candidate và lịch sử child attempt phải liên tục,
  khớp trạng thái; SQLite phải tự đối chiếu lại source role/seq/paragraph/kind/text của structural row. Mismatch/tamper phải
  fail-closed trước request hoặc commit. Chỉ cần ledger analysis đã có candidate là analysis đã bắt đầu, kể cả mọi segment
  còn `pending`; casting fingerprint đổi sau điểm đó phải yêu cầu project sạch.
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

## Quy trình dev: chạy thật và tự đánh giá

Mỗi phiên bản là một tag Git kèm một lần chạy thật; lịch sử lý do nằm ở `docs/VERSIONS.md`, không phải ở
commit message. Output audio của từng phiên bản được giữ lại ngoài repo tại
`D:\Novels\Audiobooks\_versions\<tag>\` để nghe đối chiếu và **không bao giờ được commit**.


Dev **không** mở GUI để thử. Vòng lặp chuẩn là headless, tự đọc log và tự chấm output:

```text
cli create --profile high_quality  →  scripts/run_book_job.py <project-root>
→ đọc JSONL message stream + cli status/report
→ chấm audio bằng scripts/audit_audiobook.py
→ sửa code → tạo project sạch → chạy lại
```

- `scripts/run_book_job.py` chạy `run_worker` trong process hiện tại và in mọi message dạng JSONL.
  Trên Windows phải reconfigure stdout/stderr sang UTF-8 trước khi in, vì tên nhân vật và log tiếng Việt
  sẽ làm luồng cp1252 chết và giết luôn thread drain.
- App **tự khởi động Ollama ẩn** bằng `ollama serve` + `CREATE_NO_WINDOW`, log vào `runtime/logs/ollama-server.log`.
  Không bao giờ mở Ollama desktop app. Nếu thấy icon Ollama ở system tray thì đó là do một lệnh `ollama`
  thủ công (ví dụ `ollama list`) đã kích hoạt stub tự khởi động `ollama app.exe --hide --fast-startup` của Windows,
  chứ không phải app này. Bằng chứng phân biệt: server do app khởi động luôn ghi dòng
  `--- Ebook Reader started Ollama at <thời điểm> ---` vào `runtime/logs/ollama-server.log`.
- Đổi bất kỳ file nào trong `QUALITY_IMPLEMENTATION_FILES` sẽ đổi quality-policy hash và làm project đang dở
  không resume được. Đây là hành vi đúng: sửa code xong thì tạo project sạch, đừng cố resume.
- Iterate bằng project nhỏ (2–3 chapter) để có audio nhanh, chỉ mở rộng phạm vi khi chất lượng đã ổn.

## Throughput

Đo ngày 2026-08-31 trong lúc chạy thật: GPU **14–18%**, VRAM **1,30/8,15 GB**, CPU **0,8/32 core**, đĩa
**99% idle**. Không tài nguyên nào bão hoà, mà vẫn mất ~6,7s cho ~7,4s audio. Nguyên nhân là VieNeu decode
**tự hồi quy từng frame**, tức latency-bound — thêm CPU hay đĩa không giúp gì.

- Nâng utilization của decode tự hồi quy **chỉ có thể** bằng cách cho nhiều câu chạy đồng thời.
- Nhưng `_set_generation_seed` seed **global cho cả process**, nên batching trong cùng process hoặc chạy
  nhiều luồng sẽ làm audio của một câu phụ thuộc vào hàng xóm trong batch, phá tính tất định khi resume và
  phá mô hình immutable candidate. **Không được nới lỏng chỗ này để lấy tốc độ.**
- Hướng hợp lệ duy nhất là song song theo **tiến trình**: mỗi process con có global RNG riêng và xử lý đúng
  một segment tại một thời điểm, nên audio giống hệt bản đơn luồng. Chỉ process cha được ghi SQLite;
  process con chỉ làm phần thuần hàm rồi trả metrics.
- Đĩa và CPU đang rảnh, nên **đừng** tối ưu fsync, checksum hay số lần ghi `.part` — chúng không phải nút
  thắt và chúng là thứ giữ artifact an toàn khi crash.

Chi tiết số đo, ranh giới thiết kế và test bắt buộc: `docs/THROUGHPUT.md`.

## Dependency, model và tool

Người dev project chịu trách nhiệm luôn cả stack: pin thư viện, revision model và tool ngoài.
`docs/DEPENDENCIES.md` giữ đánh giá rủi ro từng package; `scripts/check_dependency_updates.py`
là bước kiểm read-only chạy mỗi phiên bản (nó không bao giờ tự khởi động Ollama).

- `QUALITY_IMPLEMENTATION_FILES` bao gồm `../pyproject.toml` và `../uv.lock`, nên **mọi thay đổi
  dependency đều đổi quality-policy hash**. Nâng cấp luôn là một sự kiện phiên bản: nâng → project sạch
  → chạy lại → so audio → tag.
- **Không sửa bất kỳ file nào trong `QUALITY_IMPLEMENTATION_FILES` khi đang có job chạy**, kể cả chỉ đổi
  dòng `version` của `pyproject.toml`. Pipeline tính hash một lần lúc khởi tạo nên job đang chạy không chết
  ngay, nhưng lần resume kế tiếp sẽ bị từ chối.
- **`git merge` của một nhánh cũng là "sửa file", dù bạn không gõ vào file nào.** Ngày 05/09/2026 tôi merge
  `dev/alpha13` vào production để lấy một script trong `scripts/` — merge nhánh lấy **cả nhánh**, và nó kéo
  theo `analysis.py` đang nằm chờ trên đó. alpha.46 đang chạy dở. Không segment nào bị ghi sai hash (pipeline
  tính một lần lúc khởi tạo, đúng như dòng trên), nhưng chương 3 lúc ấy đang `failed` và **cần một lần
  `resume` để xuất** — mà resume thì sẽ bị từ chối. Đổi một script an toàn suýt mất một chương.
  - Muốn lấy một commit khi đang có job chạy: **`git cherry-pick` commit đó**, đừng merge nhánh.
  - Hoặc tốt hơn: đừng để việc chạm file bị khoá nằm chung nhánh với việc merge được.
  - Cách kiểm tra sau khi merge, mất một giây:
    `git diff --stat <trước> HEAD -- _internal/ebook_reader/` — phải rỗng.
  - Cách kiểm chứng job vẫn còn nguyên vẹn: tính lại `quality_policy_hash(build_quality_policy(settings))`
    từ `settings_json` của project và so với `generation_policy_hash` trong bảng `segments`.
- Chỉ nâng khi có lý do. `numpy`, `librosa`, `transformers`, `huggingface-hub`, `torch*` và `timm` ràng buộc
  với UTMOSv2/Whisper và với cache revision đã khóa; `pyworld` quyết định pitch; `vieneu` quyết định audio.
- `vieneu` 3.3.0 chuyển engine mặc định sang ONNX Runtime và đẩy torch xuống extra `legacy`; tham số `style`
  cũng đã bị deprecate. Mọi ngân sách frame hiện tại được đo trên engine torch cũ, nên đây là migration
  thật sự chứ không phải bump pin.
- Thư viện Python của VieNeu **không có** tham số tốc độ đọc (tính năng 0.5–3.0 chỉ có trong desktop app).
  Cách đúng để hiện thực hóa `pace` là hậu xử lý giữ nguyên cao độ bằng FFmpeg `atempo`.

## Đánh giá chất lượng audio

`scripts/audit_audiobook.py` là công cụ chấm khách quan cho output đã commit. Nó đọc SQLite + MP3 chương
và báo cáo các trục mà tai người nghe thật sự nhận ra, ngoài các gate đã có trong pipeline:

- tốc độ đọc (âm tiết/giây) theo từng segment, và độ lệch giữa các segment trong cùng một chương;
- khoảng lặng thực tế tại mối nối so với `break_ms` dự kiến, gồm cả phần câm mà TTS tự sinh ở đầu/cuối segment;
- độ đồng đều loudness giữa các segment và giữa narration với dialogue;
- phân bố pitch/preset theo nhân vật để phát hiện nhân vật bị trộn giọng.

Ngưỡng review của công cụ này là *chẩn đoán*, không phải gate publish. Muốn biến một phát hiện thành gate thì
phải thêm vào đúng module (`audio_io.py` cho tín hiệu chương, `pipeline.py` cho vòng repair) kèm test.

## Kiểm tra trước khi bàn giao

Từ thư mục `_internal`:

```text
python -m compileall -q ebook_reader tests scripts
python -m pytest
```

- Trên Windows/PowerShell, luôn gọi một interpreter tường minh rồi truyền toàn bộ test path trong cùng một
  invocation (có thể dùng array + splatting). Không bao giờ đặt các path `test_*.py` thành những câu lệnh trần
  ở các dòng riêng vì Windows sẽ mở `OpenWith.exe`/“Pick an app” cho từng file.

Definition of done:

- test liên quan pass;
- các mục root hiện cho người dùng vẫn chỉ có `Ebook Reader.lnk`, `README.md`, `_internal`; metadata Git ẩn được phép trong checkout;
- không tạo prompt giữa job;
- kill ở ranh giới bất kỳ không làm hỏng artifact đã commit;
- resume giữ settings và voice mapping;
- lỗi nghiêm trọng checkpoint + notification;
- cập nhật README hoặc `_internal/docs/TEST_REPORT.md` khi hành vi/test thay đổi.
