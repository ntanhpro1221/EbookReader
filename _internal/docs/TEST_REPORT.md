# Test report

Ngày cập nhật: 2026-08-30

Đợt sửa confidence contract V22: **634/634 test trọng tâm pass** cho analysis bắt buộc,
database safety và quality policy trên Python 3.11.9. Compileall cho source/test, `git diff --check`
và Ruff trên toàn bộ file bị ảnh hưởng đều pass; đợt này không chạy model/GPU hoặc pipeline audiobook thật.
Hardening sau bằng chứng V23 `“Ha…”` đã khóa critic schema/prompt theo durable floor, exact singleton target + source hash,
bỏ boolean accept khỏi model contract và tách reason confidence/rationale/quote; suite analysis + quality policy liên quan pass.
Hardening sau bằng chứng V24 giữ confidence derived/validated/commit của chapter heading structural-lock ở đúng `0.95`
trong cả agreement, structural override và batch trộn; raw critic confidence vẫn được lưu và vẫn phải qua durable floor,
còn content tiếp tục dùng `min(generator, critic, cap)`. Suite analysis/database/quality liên quan, Ruff, compileall và
`git diff --check` đều pass; đợt này không gọi model/GPU hay pipeline thật.
Hardening V27 sau failure thật tại seq18 dài 261 ký tự thay singleton substring tự do bằng tập source anchor deterministic:
contract khóa source SHA + anchor-set SHA/count, schema dùng exact enum và host chỉ nhận đúng membership. Regression dùng nguyên
text V26, biên 240/241 ký tự, short singleton và multi-row đều pass trong combined analysis + database + quality-policy suite;
đợt sửa này không gọi model/GPU hoặc pipeline audiobook thật.
Hardening V28 sau forensic V27 seq32 thay multi-row substring tự do bằng canonical ordered per-ID source-anchor map:
schema `items.oneOf` khóa từng nhánh vào exact ID + enum riêng, contract khóa map SHA/tổng anchor và host từ chối anchor
mượn từ ID khác. Narration dẫn ngay trước thought cùng chapter/paragraph giữ previous nhưng ẩn next thought khỏi critic
bằng policy source-bound riêng; generator vẫn thấy adjacent context và không có kind override. Regression dùng nguyên
seq31/32/33 V27, hai control khác paragraph/next dialogue và critic stub leak-sensitive đã pass trong combined
analysis + database safety + quality-policy suite **723/723**; Ruff, compileall và `git diff --check` cũng pass.
Đợt sửa không gọi model/GPU.
Hardening V29 sau failure thật V28 seq10 thêm authority nguồn hẹp cho motif bóng đè còn nhận thức nhưng bất lực:
predicate dùng chung với DB replay chỉ nhận grammar allowlist, cùng chủ thể và chuỗi cue liền mạch; phủ định, giả định,
meta, trích dẫn, affect đối nghịch, trạng thái đã giải quyết, chủ thể/tân ngữ mơ hồ và mọi tiền tố ngoài allowlist đều
fail-closed. Candidate khóa chính xác `kind=narration` + `emotion=afraid`; critic vẫn lưu nguyên verdict/delta thô và chỉ
compose override cho hai field đã khóa, còn `intensity/pace/speaker/volume` vẫn unresolved. Một verdict protocol-invalid
làm invalid toàn payload và retry cùng durable candidate. Regression exact seq10, negative adversarial, accepted/rejected
reserve/reopen/replay/commit và policy fingerprint đã pass **818/818** test trong ba file thay đổi; auditor độc lập không còn
P0/P1. Full repository **1.264/1.264** test, Ruff, compileall, `pip check` và `git diff --check` đều pass.
Runtime V29 chạy project sạch tới seq38: exact seq10 giữ `narration/afraid`, seq18 giữ đúng per-ID evidence và seq32 giữ
`narration_before_thought_previous_only`; mọi hash/candidate/critic/commit envelope kiểm lại hợp lệ. Lượt chạy dừng fail-safe
trước casting/TTS vì `hỗn loạn|thất thần` bị cue chung ép sai sang `afraid`, đồng thời source narration dẫn seq38 chưa có
kind lock nên generator/critic từng có thể đồng thuận relabel thành thought. Không có audio/casting dở được commit.
Hardening V30 tách đúng ba cue nhận thức mơ hồ thành lớp `disoriented`: vẫn chặn `happy` sai nhưng không từ chối `neutral`
hoặc phát `allowed_emotions`; explicit fear cùng câu vẫn hoạt động độc lập. Narration dẫn ngay trước thought cùng
chapter/paragraph trở thành kind-only source lock từ immutable original context ở cả generator và critic. Raw critic/delta
được giữ nguyên, override chỉ phủ `kind`, còn related stable ID/hash được bind và SQLite tính lại hash từ text khi
allocate/reopen/accept/commit; text-only tamper có stale hash bị chặn cho cả context mới và adjacent-wake semantic provenance.
Regression exact seq38, controls, composition, accepted/rejected replay/commit và tamper pass **845/845** test trong ba file
analysis/database/quality; auditor độc lập chạy 33 test và kết luận không còn P0/P1. Full repository **1.291/1.291** test,
Ruff, compileall, `pip check` và `git diff --check` đều pass trước runtime V30.
Runtime V30 chạy project sạch tới 24/107 segment rồi dừng fail-safe ở seq24 trước casting/TTS. Forensic cho thấy target là
narration không có câu hỏi, nhưng critic ở batch 1-2 dòng gọi nó là “câu hỏi bối rối” do mượn source thought seq25 đang lộ
trong `next_text`; ở batch lớn chính critic từng đồng ý cả delivery neutral lẫn afraid. Không có bằng chứng để khóa
emotion/intensity/pace hoặc nới kind authority qua mọi paragraph; project V30 không được resume sau khi policy đổi.
Hardening V31 thêm policy riêng cho narration đứng ngay trước thought ở paragraph kế tiếp: chỉ critic bị xóa `next_text`,
generator vẫn thấy adjacent context và policy mới không tự tạo kind/semantic lock hay override. Critic chỉ correction khi
candidate không tương thích, không correction vì một phương án khác cũng hợp lý; cue `disoriented` đơn lẻ vẫn cho phép
neutral, intensity 0/1 và pace normal. SQLite tính lại context hash từ current + neighbor stable ID, text SHA, chapter,
seq, paragraph và kind khi allocate/reopen/critic completion/commit; injected policy, lock, override và source tamper đều
fail-closed, còn semantic lock độc lập vẫn compose. Regression analysis/database/quality pass **886/886**, full repository
**1.332/1.332**; Ruff, compileall, `pip check`, `git diff --check` và hai audit độc lập đều sạch trước runtime V31.
Hardening V32 sau failure thật ở seq43 giữ source unit nguyên tử qua ranh giới batch: lời dẫn seq42 cùng paragraph và phần
ngoặc kép ngoài tiếp tục qua seq43–44 được đóng gói chung `[42,43,44]`, trong khi prefix thành `[38,39,40,41]`. Retry của
profile high-quality không cắt một source unit hội thoại không quá cap 5; unit vượt cap vẫn hard-split hữu hạn. Source
`kind_hint=dialogue` tạo kind-only lock bền; critic dissent trên kind được audit/override theo exact source, nhưng speaker
không bao giờ được lock che và vẫn fail-closed nếu còn delta. SQLite dựng lại text/hash/kind/lock khi allocate, reopen,
critic completion và commit, đồng thời từ chối evidence thiếu lock, giả rule hoặc giả covered/unresolved partition.
Regression exact seq42–44 cùng database replay/tamper và quality policy pass **897/897**; full repository **1.343/1.343**,
Ruff, compileall, `pip check`, `git diff --check` đều pass. Mọi test đều gọi interpreter rõ ràng; `OpenWith.exe` giữ **0**.
Runtime V32 dùng project sạch đã checkpoint 24/107 segment rồi dừng fail-safe trước casting/TTS ở exact seq24. Target
chỉ có cue active `hỗn loạn`, không có câu hỏi; cùng delivery `neutral/0/normal` từng được critic đồng ý trong batch,
nhưng các lượt singleton lại bịa “câu hỏi bối rối” và ép `afraid`, intensity `2|3`, pace `fast`. Project V32 không được
resume sau khi policy đổi và không có audio/casting dở được commit.
Hardening V33 thêm compatibility override source-bound duy nhất cho trường hợp này: source phải là narration/NARRATOR,
chỉ có cue active `disoriented`, không có dấu hỏi/cảm thán; candidate phải `neutral`, intensity `0|1`, pace/volume
`normal`; critic chỉ bị bác khi suy diễn đúng `afraid` kèm ít nhất một escalation intensity hoặc pace và toàn bộ delta
nằm trong `emotion,intensity,pace`. Cue affect khác, emotion khác, delta kind/speaker/volume, intensity không tăng hoặc
pace không thành fast đều giữ fail-closed. Verdict/delta thô vẫn được lưu; SQLite dựng lại exact rule từ source/hash,
candidate, critic và partition khi completion/reopen/commit, đồng thời từ chối override thiếu/giả hoặc xuất hiện trong
rejected evidence. Analysis/database/quality pass **908/908**; full repository **1.354/1.354**; Ruff, compileall,
`pip check`, `git diff --check` đều pass và `OpenWith.exe` giữ **0** trước runtime V33.
Runtime V33 dùng project sạch đã dừng fail-safe ở 8/107 segment, trước casting/TTS. Forensic exact batch seq8–11 cho thấy
parent đã tích lũy đúng correction cho seq9 và host lock `afraid` cho seq10, nhưng sau khi tách `[8,9,10] + [11]`, child
không nhận feedback của parent: ba lượt retry luân phiên sửa seq9 rồi làm seq10 quay về `sad`, nên host từ chối. Source unit
seq8–10 vẫn được giữ nguyên tử; project V33 không được resume sau khi fingerprint analysis đổi.
Hardening V34 khóa `allowed_emotions` source-authoritative của host theo từng request ID ngay trong schema generator
`segments.items.oneOf`; nhiều constraint cùng ID lấy giao, giao rỗng fail-closed trước HTTP, còn semantic choices vẫn chỉ
là advisory và không thu hẹp enum. Mọi đường split dùng chung một hàm lọc feedback typed theo `stable_id` và chuyển nó vào
đúng child, nên correction của câu khác không rò sang child và host lock đã có không bị mất. Policy nâng lên
`analysis_ledger_v19`, `per_id_host_emotion_enum_v1`, casting stage v22/algorithm v23. Regression schema per-ID,
intersection/conflict, semantic non-lock và split carry pass trong analysis/database/quality **911/911**; full repository
**1.357/1.357**; Ruff, compileall, `pip check`, `git diff --check` đều pass và `OpenWith.exe` giữ **0**. Runtime V34 chưa
được tính vào các kết quả này.
Runtime V34 dùng project sạch đã chứng minh hai sửa đổi trước hoạt động thật: child `[seq8,seq9,seq10]` nhận feedback cha,
pass ngay lượt đầu sau split và giữ exact seq10 `narration/afraid`; exact seq24 giữ
`narration/NARRATOR/neutral/0/normal`, raw critic vẫn ghi câu “câu hỏi bối rối” cùng delta `afraid/2/fast`, còn compatibility
override V33 được dựng lại đúng. Lượt chạy sau đó dừng fail-safe ở 25/107, trước casting/TTS, tại exact thought seq25
`‘Đây rốt cuộc là nơi nào?!`: generator chỉ nhận tên field mismatch nên qua nhiều batch/singleton vẫn trả neutral, trong khi
critic lặp correction `afraid|surprised`, intensity `2|3`, pace `fast`. Project V34 không được resume sau khi policy đổi.
Hardening V35 thêm `suggested_values` advisory typed cho `DIRECTOR_FIELD_MISMATCH`, chỉ cho phép enum/số canonical của
`emotion|intensity|pace|volume`; không chuyển kind, speaker, source, quote hay rationale và không thu hẹp schema như HOST.
Projection delivery đã sửa được giữ qua retry/split vì mỗi request sinh lại từ đầu; correction critic mới ghi đè đúng field
nó thay đổi nhưng không làm field vừa được critic đồng ý quay về mặc định. Policy nâng lên `analysis_ledger_v20`,
`per_id_host_emotion_director_advisory_v2`, casting stage v23/algorithm v24. Regression exact seq25, projection nhiều lượt,
split carry, advisory non-lock và payload độc hại/sai kiểu pass trong analysis/database/quality **917/917**; full repository
**1.363/1.363**; Ruff, compileall, `pip check`, `git diff --check` đều pass và `OpenWith.exe` giữ **0**. Runtime V35 chưa
được tính vào các kết quả này.

## Tổng hợp hardening và runtime V36–V43 (2026-08-24)

Hardening V36–V43 khóa retry khi `neutral` bị cue trực tiếp bác bỏ bằng rejection/advisory typed theo đúng ID, đồng thời
khóa `speaker` trong schema director vào exact speaker của candidate thay vì cho model phát sinh identity mới. Ledger hiện
ở `analysis_ledger_v26`/casting ledger v28; DB dùng aggregate validator chung cho state machine và mọi public read/mutation,
kiểm lại generator-contract history, critic-attempt history liên tục, terminal/superseded state và replay payload trước/sau
transition. High-quality ASR tăng immutable clarity repair budget từ **3 lên 5** và đưa giá trị này vào quality policy.

Runtime sạch V40 kết thúc **101 verified / 1 warning / 5 failed**. Runtime sạch V43 cải thiện thành
**102 verified / 1 warning / 4 failed**; exact `seq84` được cứu ở clarity round 3. Exact `seq99–101` cùng giữ provenance
speaker `NPC_LOCAL::c00001::rf4306ee4f88ce933::người phụ nữ áo đen`. Ở exact `seq45`, candidate `neutral` cho cue
“vẻ tự hào” bị rejection contract loại và lượt sau commit `happy/intensity=2/pace=normal`. V43 promotion đúng
**8 clarity + 4 perceptual**, chạy **3039.802 giây**, giữ `OpenWith.exe=0`; bốn segment fail vẫn chặn chapter nên không
xuất MP3, đúng fail-closed.

Sau V43, repeated-short ASR đã đổi khoảng lặng giữa ba bản sao từ **0,24 lên 0,50 giây**; các probe phát âm standalone
trên artifact đích cho kết quả tốt hơn mà không đổi content/timeline gate. Runtime sạch V44 sau thay đổi này kết thúc
**100 verified / 2 warning / 5 failed** trong **3156,396 giây**. Exact seq17 được dual-pass ngay round 0, còn seq106
chứng minh nhánh `source_spelling_v1` có thể sửa `Lucien` và promote an toàn. Tuy nhiên policy V44 vẫn luân phiên source
ở mọi round lẻ chỉ vì segment có locked name; seq43 và seq64 là lỗi content nhưng vẫn mất round 1 cho source, và seq43
kết thúc fail dù candidate canonical mới có thể cứu được.

## Evidence-gated pronunciation repair và runtime V45 (2026-08-24)

V45 chỉ cấp `source_spelling_v1` khi **candidate ngay trước đó** có đủ hai decode beam/greedy bền trong SQLite và ít nhất
một decode đã adjudicate đúng `ASR_LOCKED_NAME_ANCHOR_MISMATCH`. Evidence phải khớp policy hiện hành, incumbent SHA,
voice profile, selected decode, quality-check metrics/failure codes và locked-anchor metrics v2; evidence thiếu, stale,
méo hoặc bị sửa đều fail-closed. Lỗi content thuần giữ `locked_spoken_v1` và seed canonical; policy ASR nâng thành
`evidence_gated_name_pronunciation_delivery_v8`.

Full repository **1.438/1.438**, Ruff, compileall, `pip check` và `git diff --check` đều pass. Runtime sạch V45 dùng cùng
manifest `375bd57ab4ee8230d2ecb74da67bb526446f5a36f5a031ebfb40d5d6fceb1a6a`, kết thúc
**101 verified / 2 warning / 4 failed** trong **3150,150 giây**. Exact seq43 giữ canonical ở round 1, dual-pass rồi
được UTMOS xác minh/promote; seq64 giữ canonical ở round 1 và chỉ chuyển source ở round 3 sau khi greedy round 2 thật sự
ghi locked-name mismatch; seq106 vẫn chuyển source ở round 1 và đạt beam/greedy `1,0 similarity / 0,0 WER` trước promote.
Perceptual repair cũng cứu exact seq18 bằng candidate round 0 qua cả hai Whisper và UTMOS.

Hai warning cuối là seq8 `PERCEPTUAL_NATURALNESS_REVIEW` và seq83 `TTS_GENERATION_CEILING_REACHED`; bốn failure là
seq35/44/65 locked-name mismatch và seq64 content mismatch. SQLite schema v9 trả `integrity_check=ok`, không có lỗi khóa
ngoại; quality report được xuất, `validate --require-complete` từ chối publish và **0 MP3** tồn tại đúng fail-closed.
Sau khi worker thoát không còn Python/Ollama/FFmpeg con và `OpenWith.exe` giữ **0**.

Setup chỉ cài runtime dependency/model và chạy system check trên máy đích trước khi ghi marker hoàn tất;
pytest/Ruff không được cài hoặc chạy trong luồng mở app của người dùng.

## Immutable repair hardening và runtime V48 (2026-08-29)

Hardening sau V45 tách contract ASR/perceptual/TTS thành module độc lập, khóa lại provenance của mọi candidate và
checkpoint repair. Clause recovery có hai strategy bất biến: `sentence_v1` tối đa 170 ký tự và `clause_v1` tối đa
120 ký tự; final source-spelling candidate chỉ dùng clause split khi evidence trước thật sự yêu cầu. Root seed được
tính lại từ stable ID + voice key + salt canonical, từng part seed được tính lại từ stable ID part + exact prefix;
SQLite từ chối root/part seed, strategy, max chars, thứ tự, checksum text, voice, pitch hoặc pronunciation variant bị
sửa. Token đơn dài hơn giới hạn không còn làm worker crash: allocator nhận biết split không khả dụng và giữ finite
fallback, còn checkpoint đã cấp phát vẫn fail-closed bằng candidate TTS failure có thể resume.

Mọi candidate `dual_failed` và exhaustion summary giờ được dựng lại từ quality-check gốc thay vì tin JSON tổng hợp đã
lưu. Beam/greedy, failure code, selected result, ASR/signal blocker, UTMOS result và terminal reason đều được kiểm lại;
tamper một check, kết quả perceptual hoặc lý do exhaustion bị từ chối trước resume/finalize. Trường hợp ASR đã pass nhưng
UTMOS vẫn review hết budget kết thúc bằng `PERCEPTUAL_NATURALNESS_REVIEW`, không bị ghi nhầm thành ASR failure.

Delivery `ha_vocalization_v2` giới hạn 23 frame, temperature/top-p thận trọng và không còn chèn silence giả để đạt độ dài.
Raw/target/final sample count, padding bằng 0, sample rate, cap và endpoint-active được lưu, kiểm lại và xuất report.
Exact seq8 V48 bắt đầu bằng waveform 1,84 giây chạm trần; candidate round 1 tạo waveform 1,44 giây, không chạm endpoint,
beam/greedy cùng pass rồi được promote với transcript `Ha ha, ha!`.

Audit tiếp ngày 2026-08-30 nâng schema lên v11 và tách `generation_strategy=direct_v1|split_v1` thành ledger field bền,
không còn suy ra split chỉ từ seed. Strategy chỉ được chuyển một chiều direct -> split trong checkpoint generating và
bất biến sau khi signal đã commit; xóa toàn bộ split provenance đồng thời đổi root seed sang lịch direct vẫn bị từ chối.
`perceptual_required` có trigger bất biến và được đối chiếu lại với `settings.perceptual_qa.enabled` của quality policy
đã khóa khi allocate/resume/promote, kể cả caller gọi thẳng promotion API mà bỏ qua resume plan; sửa `true -> false`
không thể bỏ qua UTMOS. Direct promotion cũng kiểm lại split/vocalization/delivery provenance ngay trong cùng transaction.
Với profile `ha_vocalization_v2`,
WORLD pitch không được phép zero-pad: output pitch ngắn hơn bị bỏ, waveform thô được giữ, và coordinator hậu kiểm exact
sample count trước khi ghi provenance.

Runtime sạch V48 dùng lại manifest
`375bd57ab4ee8230d2ecb74da67bb526446f5a36f5a031ebfb40d5d6fceb1a6a`, cold bootstrap được đợi tối đa 120 giây.
Worker bị dừng sau checkpoint **59/107** rồi resume thế hệ kế tiếp mà không làm lại phần đã commit. Kết quả cuối là
**104 verified / 1 warning / 2 failed**, tốt hơn V45 **+3 verified / -1 warning / -2 failed**. Exact seq44 đi đủ năm
candidate, final source + `clause_v1` giữ nguyên văn bản thành bốn part dài **53/111/40/102** ký tự nhưng `Wayne` vẫn bị
nhận sai nên kết thúc `ASR_LOCKED_NAME_ANCHOR_MISMATCH`. Exact seq64 giữ đúng locked `A-đe-ron`; candidate cuối có beam
canonical pass nhưng greedy vẫn content mismatch nên kết thúc `ASR_MISMATCH_UNRESOLVED`. Exact seq83 là warning duy nhất
`TTS_GENERATION_CEILING_REACHED` với ASR đúng `Điên rồi!`.

Các probe đối chứng sau runtime không được đưa vào policy: hạ clarity temperature/top-p làm seq64 kém hơn, chia câu sau
`Aderon` làm nửa đầu kém hơn, và seed repair thứ sáu làm cả seq44/64 kém hơn. Vì vậy budget vẫn hữu hạn 5 round, dual gate
vẫn giữ nguyên, không đổi voice, không hạ threshold và không promote artifact chỉ có một decoder pass.

SQLite V48 thật được kiểm raw read-only, vẫn ở schema 10 và không bị migrate: `integrity_check=ok`, `foreign_key_check`
rỗng, worker lease rỗng sau exit; quality report đã xuất nhưng chapter bị hai failure chặn nên **0 MP3**, đúng fail-closed.
Bản sao calibration migrate lên schema 11 thành công, dựng lại đủ **34 candidate summary / 14 segment**, backfill
**33 direct / 1 split**, `integrity_check=ok` và foreign key bằng 0. Full repository **1.552/1.552** test pass; Ruff toàn
source/test, compileall, `pip check`, `git diff --check` đều pass. Tất cả Python trong runtime và validation đều được gọi
bằng interpreter `.venv` rõ ràng; sau toàn bộ run/probe `OpenWith.exe` giữ **0**.

## Phạm vi tự động

- CLI headless tạo exact numeric range inclusive, dry-run không ghi dữ liệu, đọc status/report/log qua SQLite read-only,
  chạy component test, validate artifact QA và phát JSON/exit code UTF-8 ổn định kể cả database hỏng;
- supervisor nền không mở console, redirect log, khóa double-start, xác minh PID/create-time/project/token,
  chỉ handshake READY sau worker bootstrap, giữ stop request bền qua process độc lập và chặn force-stop ABA;
- creation lock serialize hai lệnh tạo cùng manifest/title nhưng khác settings; recovery bỏ qua namespace control
  `runtime/background` để không xóa state/handshake atomic đang được ghi;
- settings bất biến và cấm prompt/silent replacement;
- import nhiều TXT hoặc folder, natural sort và loại file không hợp lệ;
- one-click startup qua shortcut `Ebook Reader` ở root/Start Menu trỏ thẳng tới `_internal\Ebook Reader.vbs`;
  console hiện ngay, báo tiến độ và tự đóng theo ready marker do GUI ghi sau khi render;
  output được append vào `runtime/logs/startup.log`, boundary ngoài cùng bắt lỗi và giữ console mở cho tới khi
  người dùng chủ động đóng; runtime cũ thiếu dependency chỉ chạy repair Python, không cài lại PyTorch/model;
- single-instance dùng local IPC: lần mở thứ hai chỉ kích hoạt/đưa cửa sổ đang chạy lên trước rồi đóng launcher;
- system tray có hành động hiện/ẩn/thoát hoàn toàn; nút `X` chỉ ẩn và giữ worker chạy, còn thoát từ tray
  kết thúc cây worker ngay;
- GUI không còn tiêu đề lớn, tự đổi nút `Bắt đầu`/`Tiếp tục`, tự mở project được chọn gần nhất;
  `Bắt đầu` bị vô hiệu hóa khi chưa có chapter nguồn và mỗi dòng Log có timestamp;
  nút chọn TXT/folder vẫn dùng được khi project cũ đang dừng và chuyển sang book mới sau khi chọn nguồn;
  khối `Thiết lập` chỉnh được ngay sau khi mở lại và thay đổi sẽ tạo project mới theo settings hash;
  thêm/xóa TXT tạo draft mới mà không sửa sách cũ; bốn nút nguồn có cùng kích thước; danh sách/bảng
  có alternate-row tối hơn nền thường và selection dùng đúng màu highlight của ô Log kể cả khi mất focus;
  nested splitter và từng cột tiến độ kéo được, kích thước cột được lưu, đường dẫn MP3 không bị elide;
  nhấn lặp vào ô MP3 dài không làm bảng tự kéo thanh cuộn ngang sau độ trễ double-click;
  nút chính tự đổi `Bắt đầu`/`Tạm dừng`/`Tiếp tục`, chỉ còn một nút `Dừng` riêng và chỉ xuất MP3
  theo từng chapter nguồn; WAV checkpoint bắt buộc được giữ nội bộ, không hiển thị như một tùy chọn;
  đóng cửa sổ kết thúc cây worker mà không đợi checkpoint;
- bảng chapter hiển thị riêng tiến độ phân tích, tạo audio, kiểm tra, giai đoạn và MP3;
- double-click ô MP3 trống không mở Explorer;
- progress event bao phủ chuẩn bị văn bản, TTS, Whisper, repair, ghép chapter và xuất báo cáo;
- analysis dùng ID ngắn bị ràng buộc theo batch rồi ánh xạ chính xác về stable ID;
- Ollama analysis chạy dạng stream có thể hủy khi dừng, giới hạn schema/token/wall-time và ghi
  heartbeat vào Log mỗi phút để không còn im lặng trong một request dài;
- stream analysis thiếu gói kết thúc được phân loại riêng và tự chia đôi batch ngay; batch con giữ nguyên
  checkpoint/progress, còn stdout/stderr của Ollama ẩn được nối vào `runtime/logs/ollama-server.log`;
- semantic delivery gate từ chối output Qwen đúng schema nhưng suy biến: batch `happy` mâu thuẫn hàng loạt hoặc
  template `neutral/intensity=0/normal` phủ lên nhiều cue cảm xúc rõ ràng; evidence ghi
  đúng cụm từ đã khớp, retry có feedback theo đúng ID rồi chia đôi hữu hạn; batch vui thật, narration trung tính,
  mixed-affect và cue nằm trong phủ định/ngăn cấm cục bộ vẫn được chấp nhận; template neutral-zero vẫn bị chặn
  riêng sau khi batch đã chia dưới 8 segment và kết thúc bắt buộc ở singleton thay vì checkpoint dữ liệu suy biến;
- cue `thất thần|bàng hoàng|hỗn loạn` được giữ ở lớp `disoriented` chống happy, không còn ép neutral thành afraid hay
  phát allowed-emotion advisory; cue sợ hãi rõ ràng cùng câu vẫn được xét độc lập;
- critic self-review chỉ có thể bị compatibility override ở đúng narration/NARRATOR `disoriented`-only, không có dấu
  hỏi/cảm thán, candidate neutral low-arousal và correction `afraid` tăng intensity hoặc pace; exact evidence source/hash,
  candidate/critic/delta được DB replay, mọi correction ngoài contract vẫn fail-closed;
- compound gate từ chối narration phẳng khi cùng một segment có cả tổn thương phổi/yết hầu và ý thức mơ hồ, nhưng giữ
  neutral cho suy kiệt thể chất hoặc quan sát lâm sàng đơn lẻ để không biến keyword gate thành đạo diễn cảm xúc rộng;
- host affect nguồn hẹp được adjudicate trước semantic cue chung và mọi constraint typed đã xác minh được tích lũy trong
  cùng target group, nên retry sửa câu sau không làm câu trước quay lại delivery đã bị từ chối;
- neutral bị semantic cue chung từ chối nhận `allowed_emotions` advisory là hợp deterministic các emotion tương thích với
  cue trực tiếp của chính source. Payload typed không mang source/cue/rationale; phủ định, historical/meta, affect đối nghịch,
  distressed chung và physical/host-rule không tạo lựa chọn này. Non-neutral không bị exact-membership gate hay auto-mutation,
  và candidate retry vẫn phải qua nguyên validation cùng director critic;
- hai rule narration hẹp cho nỗi sợ còn dai dẳng khi hồi tưởng và trạng thái sững người đầu óc trắng xóa dùng chung predicate
  source-only với DB replay; chúng khóa `kind=narration`, gửi allowed emotion typed theo đúng ID, không lan từ hàng xóm và
  vẫn bắt model trả candidate mới trước director critic;
- rule narration bóng đè/bất lực chỉ nhận đúng grammar tiền tố allowlist và chuỗi cue cùng chủ thể, source-only; nó khóa
  `kind=narration` + `emotion=afraid`, không relabel lời kể “cậu biết... muốn...” thành thought và fail-closed với mọi
  tiền tố/chủ thể/phủ định mơ hồ;
- semantic lock bền khóa affect rule vào source hash và critic candidate. Lock một field chỉ override đúng delta field đó;
  lock bóng đè được compose riêng source-kind + emotion nhưng vẫn giữ raw verdict/delta, còn mọi delta delivery khác bị chặn.
  Agreement luôn được host suy từ sáu field; protocol-invalid ở bất kỳ row nào làm invalid toàn critic payload;
- dialogue và thought boundary đã được source parser nhận diện là source-owned: model không được đổi chúng sang loại khác để
  né speaker/semantic lock. Narration dẫn ngay trước thought hoặc khớp semantic narration bắt buộc cũng source-owned;
  narration thường vẫn có thể được nâng thành implicit thought để giữ compatibility;
- `notes` và `personality_hint` tự do không còn thuộc output model hay acceptance envelope. Host tạo `delivery_note_v1`
  chỉ từ delivery đã kiểm; segment note không chứa marker điều khiển và marker repair tạm bị xóa trước candidate. Projection
  analysis đã chấp nhận nằm trong ledger+critic source-bound; bước casting chỉ reconcile speaker bằng transform source-derived,
  deterministic và có fingerprint stage riêng. DB tính lại và từ chối note/personality/marker không canonical khi allocate,
  reopen, direct update và commit. Character registry không còn dùng prose delivery làm personality hay marker legacy làm
  quyền điều khiển identity, và speaker repair không sao chép note lân cận;
- high-quality director critic chạy lượt self-review thứ hai mà không thấy confidence/notes/personality của generator;
  content generator confidence dưới floor bị feedback typed và retry trước mọi critic/ledger allocation; schema/prompt mang
  floor ở batch không có heading, còn batch hỗn hợp giữ schema floor `0` để proposal confidence thô của heading vẫn tới host.
  Contract critic khóa cả floor/cap và evidence policy. Singleton có target dài 1..240 ký tự dùng
  `singleton_full_target_v1`, exact source SHA và enum quote bằng toàn target; singleton dài hơn dùng
  `singleton_source_anchor_enum_v1`, exact source SHA + deterministic anchor-set SHA/count và enum chỉ gồm source anchor
  nguyên văn không quá 240 ký tự; multi-row dùng `per_id_source_anchor_enum_v1`, ordered map SHA/tổng anchor và
  `items.oneOf` khóa exact ID + enum riêng, không còn union/substr tự do.
  Model không còn trả boolean accept: host suy agreement từ sáu field không delta, correction từ field delta, rồi chỉ lưu
  `critic.accept` compatibility bằng đúng kết quả host-derived. Root/item thừa, ID thiếu/trùng/lạ, string thay số, NaN/Inf,
  confidence dưới ngưỡng, rationale lỗi và quote lỗi có category durable riêng;
  candidate hash, exact field agreement và confidence cap được kiểm tra trước checkpoint, còn deterministic semantic gate
  luôn có precedence vì critic cùng Qwen là correlated self-review chứ không phải model độc lập;
- source thought được gửi riêng cho critic theo `previous_context_only`: giữ lời dẫn trước nhưng xóa `next_text`.
  Narration dẫn ngay trước thought cùng chapter/paragraph dùng `narration_before_thought_previous_only`, giữ previous nhưng
  ẩn thought kế tiếp để critic không mượn affect. Kind narration được khóa từ immutable original context ngay trong generator
  và critic; bất đồng critic chỉ override đúng kind, giữ raw delta, khóa related stable/hash và tính lại hash từ source text
  trên mọi replay/commit. Narration/dialogue còn lại vẫn dùng adjacent context, generator vẫn giữ đủ adjacent context.
  Regression V21 seq13, V27 seq31/32/33 và V29 seq37/38/39 khóa split singleton, hash/contract resume source-bound,
  text-only tamper và ngăn cue tương lai bị mượn sang target;
- host affect gate khóa hẹp hai beat tự-bảo-toàn: thought có cue tử vong trực tiếp và wake/self-rescue thought liền kề;
  feedback là JSON typed/whitelist không chứa source/rationale tự do, trường hợp third-party/meta/khác chapter-paragraph không
  bị lan cue. Context/group fingerprint bao gồm stable ID, source hash, chapter, paragraph, kind và hai hàng xóm;
- tiêu đề chương thật được nhận diện hẹp bằng vị trí/metadata/grammar, canonical thành narrator trung tính với candidate
  confidence `0.95`, đồng thời giữ proposal confidence thô trong structural audit, rồi gửi critic theo `target_only` không có
  neighbor text. Critic confidence thô vẫn phải qua floor và được lưu để audit, nhưng confidence derived/validated/commit
  của heading đã khóa luôn giữ đúng `0.95`; bất đồng delivery thô
  trên riêng heading được lưu cùng structural override, còn bất đồng hoặc quote sai ở content vẫn từ chối cả batch;
- schema v8 lưu acceptance envelope đầy đủ, projection hash mà critic nhìn thấy, mọi generator contract và critic intent/outcome.
  Intent được reserve trước HTTP; protocol-invalid retry đúng candidate với seed mới, field mismatch lặp projection thì chia
  batch hữu hạn, còn crash sau `critic_accepted` resume/commit không gọi Ollama. Hash JSON, quan hệ parent-child, attempt liên tục,
  exact confidence `min(generator, critic, cap)` cho content cùng ngoại lệ deterministic heading khóa ở `0.95`,
  evidence policy/full-target SHA/anchor-set SHA/count, source role/seq/paragraph/kind/text và
  model/policy/context CAS đều được kiểm
  tra lại khi đọc/commit; forged content override, quote lấy từ row khác và structural clearance bị sửa đều fail-closed;
- resume coi durable analysis candidate là checkpoint đã bắt đầu ngay cả khi segment vẫn `pending`, vì vậy casting fingerprint
  mới không thể tái dùng ledger critic theo contract cũ;
- Ollama model name/digest được khóa bền theo book và đối chiếu trước/sau mọi request generator, critic và name review;
  digest đổi giữa request/resume fail-closed. Batch segment, pronunciation proposal và event ACCEPTED commit cùng một
  transaction CAS; regression trigger/reopen chứng minh lỗi event rollback cả segment lẫn pronunciation. Legacy
  high-quality đã có checkpoint trước critic bị từ chối để tránh trộn hai contract analysis;
- Ollama server do worker tự khởi động chạy ẩn, được theo dõi quyền sở hữu và chỉ tiến trình do app tạo
  mới bị dừng sau giai đoạn phân tích;
- project lock, voice profile lock và resume;
- Resource Manager: foreground, RAM, SSD và stop policy; RAM critical đơn lẻ unload model/cache, đo cưỡng bức
  lại và chỉ dừng nếu lần đo sau thu hồi vẫn critical;
- recovery: kill khi đang ghi `.part`, kill sau atomic replace nhưng trước SQLite commit, checksum và
  giữ nguyên WAV/MP3 đã commit hợp lệ;
- settings tamper, source mutation và khóa độc quyền một worker/project;
- source đổi cùng kích thước trong cửa sổ đọc, CP1258/UTF-16 không BOM và tên output an toàn;
- warning code hợp nhất và pronunciation ưu tiên confidence cao;
- chuẩn hóa tên tiếng Anh thu thập cả tên chỉ xuất hiện một lần; CMUdict nhận diện tên phổ biến và cung cấp
  ARPAbet bắt buộc Qwen trả cách đọc thuần Việt, còn từ/tên Việt bị loại theo ngữ cảnh; pronunciation chuyên biệt
  được khóa trong SQLite, áp dụng dưới mọi confidence threshold và không thể bị lần phân tích sau ghi đè;
- required-analysis batch failure không được fallback ngầm;
- stereo WAV bị từ chối, ASR optional chuyển lỗi inference thành warning;
- cụm từ đặt trong ngoặc kép không bị nhận nhầm thành hội thoại, segment chỉ có dấu câu không đi vào TTS;
- cụm cảm thán (`ha...`, `haiz...`, `hừm...`) và từ tượng thanh (`rầm`, `uỳnh`...) giữ nguyên trong câu
  narration/dialogue/thought; parser không tạo kind hiệu ứng riêng;
- `spoken_text` chuẩn hóa cách viết kéo dài và chuyển thẻ VieNeu thử nghiệm thành âm tiết có thể đọc, trong khi
  văn bản/hash nguồn không đổi; cùng `spoken_text` được dùng cho TTS và expected ASR;
- `Ha...`, `Aaaaah`, `Uuu` được đổi thành âm tiết ổn định; output VieNeu chạm đúng trần frame được giữ để
  signal/Whisper kiểm tra thay vì bị từ chối cơ học;
- mọi nội tâm bị ép về `NARRATOR` bất kể Qwen trả tên nhân vật nào và không phát warning danh tính;
- câu một từ ngắn bị giới hạn 24 frame, dùng sampling thận trọng và vẫn là ứng viên ASR repair;
- transcript Whisper có số từ không thể tồn tại trong thời lượng WAV được nhận diện là verifier hallucination;
- transcript Whisper kéo dài vô lý vào phần đệm 30 giây của model cũng được nhận diện là verifier hallucination,
  thay vì làm hỏng một vocalization ngắn có waveform hợp lệ;
- circuit breaker reset sau TTS thành công và không cộng dồn failure giống nhau nằm rải rác ở nhiều chapter;
- lần tạo lại audio xóa ASR/TTS warning cũ nhưng giữ warning phân tích; recovery đưa segment đã có
  analysis/voice profile về `analyzed`, không phân tích và phân vai lại rồi làm đổi giọng nhân vật;
- ngân sách frame và validator dùng chung một duration policy dựa trên codec VieNeu v3 3.840 sample/frame;
  ma trận kind/pace/độ dài chứng minh mọi ngân sách sinh đều còn headroom validation và không audio nào bị
  fade-out để lách kiểm tra;
- giới hạn frame VieNeu thay đổi theo độ dài/pace để câu ngắn không chạy tới trần model; lệch pace nhẹ
  trở thành warning còn sai lệch cực đoan vẫn bị từ chối;
- nhánh kết thúc còn chapter lỗi gửi Windows notification, giữ `BookStatus.ERROR`/checkpoint và worker phát
  `finished.ok=false` thay vì báo thành công;
- NPC có nhãn cục bộ giữ identity riêng, NPC vô danh tách nam/nữ; phân vai loại hoàn toàn preset tin tức,
  ưu tiên cao nhất giọng tự nhiên miền Bắc → tự nhiên miền Nam, giữ thứ tự cũ cho các giọng còn lại và chỉ đưa giọng
  Trung vào pool NPC ngắn;
- dropdown kể chuyện chỉ hiện tên của đủ 10 preset không phải tin tức; bộ lọc giới tính và miền không làm thay đổi
  preset đang chọn nếu preset đó vẫn còn trong kết quả lọc; label `Giọng kể chuyện` là header foldout có
  chevron style dropdown ở đầu, bên dưới lần lượt là nghe thử, giới tính và miền, thụt khoảng bốn ký tự;
  Phạm Tuyên và Ngọc Linh đứng đầu danh sách; hai dòng filter ẩn khi narrator bị khóa nhưng preview vẫn hiện;
- thay đổi narrator trực tiếp tự phát preview, nút preview phát lại; 10 WAV không phải tin tức được đóng gói
  bằng package-data và mapping preset nào cũng phải trỏ tới file tồn tại;
- profile chất lượng và narrator được khóa theo sách; resource mode và ngưỡng GPU là global, không detach
  sách đang mở và có thể cập nhật AdaptiveResourceManager khi worker đang chạy; `Sách mới` reset profile,
  bộ lọc và narrator về mặc định nhưng giữ nguyên resource mode và ngưỡng GPU; nút chỉ bật khi đang mở
  một project đã tồn tại và tắt trong bản nháp sách mới chưa chạy;
- cùng normalized speaker name giữ nguyên preset và biến thể cao độ; median F0 của 10 preview được đo để khóa
  pitch âm theo preset: Phạm Tuyên `0`, Xuân Vĩnh/Thái Sơn/Ngọc Trân `-1`, các preset còn lại `-2`;
  test tín hiệu xác nhận WORLD vocoder đổi F0 đúng bán âm, giữ nguyên thời lượng, spectral
  envelope và aperiodicity; không còn resampler integer-ratio từng gây allocation 2.442.336.000 byte;
  lỗi lớp pitch hoặc thiếu voiced frame giữ waveform gốc;
  mọi thought dùng narrator profile kể cả khi một row cũ còn chứa speaker/voice của nhân vật;
  segment mới dùng K-weighted LUFS thay active RMS, narrator có anchor `+0,5 dB`, target hội thoại
  trung tính `-19 LUFS` và `loud` thu hẹp còn `-17,8 LUFS`; test giọng thấp 100 Hz và sáng 260 Hz
  cùng hội tụ về target cảm nhận;
- nhãn NPC cục bộ trùng tên trong cùng chapter được hợp nhất trước casting; hội thoại ngoặc kép
  cong/ASCII kéo qua nhiều paragraph giữ nguyên kind và ngoặc đơn cong tạo thought hint;
- cùng speaker `Lucien` ở nhiều chapter khóa đúng một character/voice, trong khi tên khác như `Hạ Phong`
  vẫn là character độc lập; tên người được gọi trong “Anh Lucien!” hoặc “Iven, …” bị tách khỏi speaker;
- pronunciation checkpoint theo từng tên, tự sửa `A-der-on → A-đe-ron` mà không lặp request; khi một tên
  không thể sửa, các tên hợp lệ vẫn được khóa và retry chỉ còn đúng ID lỗi với feedback validator;
- Whisper nhận waveform mono 16 kHz được đọc/resample trong process, không gọi FFmpeg theo từng WAV;
- evidence của từng decode Whisper được lưu ở stage riêng và không thể làm final ASR gate đạt; repeated-short chỉ
  promote khi chính lượt lặp `pass`, còn lượt lặp vẫn lỗi không được ghi đè direct transcript/metrics tốt hơn;
- locked English-name anchor giữ pronunciation ID, source span và occurrence; regression chấp nhận đúng spelling,
  spoken form/dạng ghép token nhưng chặn `Lucien → Lucy/Lucian/Lusienne`, thiếu occurrence, sai thứ tự, repeat3 thiếu
  và homograph ở sai vị trí (`Mây may áo` không được lấy động từ `may` để thay cho tên bị đọc sai);
  mọi verdict `ASR_INCONCLUSIVE` giữ nguyên để không quy lỗi model/ngữ cảnh thành lỗi TTS;
- ASR repair dùng delivery `clarity` với voice/profile/pitch/text khóa nguyên và sampling variance thấp hơn; mỗi candidate
  nằm ở path bất biến riêng và không thay incumbent trước khi cả beam lẫn greedy cùng `pass`. Ledger SQLite khóa round,
  seed, voice/pitch, checksum và evidence; promotion commit final gate + CAS con trỏ + trạng thái trong một transaction.
  Regression bao phủ crash/reopen, replay payload khác, casting đổi, path trùng, WAV mất/tamper, promotion rollback,
  budget hữu hạn và exhaustion vẫn giữ đúng checksum/transcript incumbent;
- pipeline chạy ledger end-to-end: crash trước decode checkpoint chạy lại đúng candidate, WAV candidate bị tamper được
  đánh `invalid`, crash sau dual-pass chỉ resume giao dịch promotion mà không chạy lại TTS/Whisper; báo cáo
  `segment_repair_candidates` xuất từng policy/round/path/SHA/seed, signal, beam, greedy, UTMOS và trạng thái promote/fail;
- perceptual repair không còn reset/ghi đè incumbent: mỗi candidate phải qua signal gate, hai decode Whisper và UTMOS
  trên cùng checksum trước promotion. Review hết budget giữ nguyên path/SHA/bytes incumbent; restart không synth hoặc
  decode thêm, còn crash sau UTMOS pass chỉ resume transaction promotion;
- final ASR pass/fail cùng danh sách decode evidence, checksum và policy được xuất cho từng segment trong
  `audiobook_quality_report.json`;
- thermal hysteresis, atomic chapter assembly và cleanup file `.part` trong recovery;
- pipeline mock không cần model;
- cache inference VieNeu được thu hồi trong `finally` sau cả attempt thành công lẫn thất bại;
- unload VieNeu/Whisper trên Windows trim working set sau GC/CUDA cache release, tránh RAM physical
  bị giữ lại qua nhiều lần chuyển model trong book dài;
- hội thoại một hoặc hai từ có tối đa tám ký tự dùng ngân sách cực ngắn; waveform chạm trần vẫn qua
  Whisper, nhưng endpoint còn hoạt động buộc repair kể cả transcript đúng và câu ngắn không bị split;
- repair câu đã chạm trần VieNeu giảm ngân sách từ 24 xuống 12 frame, riêng câu một ký tự giảm xuống 6 frame;
  cap được checkpoint riêng trong SQLite qua `mark_generating`, failure, recovery/reopen và các vòng ASR, rồi
  chỉ xóa ở commit `verified`;
- FFmpeg thật: ghép, khoảng nghỉ, encode và decode verify.
- Windows `fsync` cho WAV/silence dùng descriptor read-write, được bao phủ bởi test FFmpeg thật.

GUI PySide6 đã mở thực tế trên Windows. Test6 đã chạy thật xuyên suốt bằng VieNeu-TTS và Whisper Turbo
trên CUDA: **11/11 chapter**, **1.080/1.080 segment**, **0 segment lỗi**, **11/11 MP3** giải mã/xác minh;
SQLite `integrity_check` trả `ok` và không có lỗi khóa ngoại. Các segment được tạo lại trong chapter 000,
002–006 vẫn giữ đúng narrator/Benjamin/Lucien/Hạ Phong đã khóa; báo cáo review được xuất lại sau lần chạy.

## Chưa xác nhận trên máy đích

- Windows Toast và foreground GPU detection;
- kill/resume giữa CUDA inference;
- OOM/backoff và thermal behavior dài giờ;
- startup thực tế sau khi đóng gói release;
- bộ dependency đã pin trên máy đích.

Bắt buộc smoke test một chapter 2.000–5.000 từ trước khi chạy book rất lớn.
