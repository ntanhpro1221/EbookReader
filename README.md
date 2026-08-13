# Ebook Reader

Ứng dụng Windows chạy local, chuyển một hoặc nhiều chapter `.txt` tiếng Việt thành audiobook MP3 có phân vai và cảm xúc.

## Bắt đầu

1. Giải nén toàn bộ ZIP vào SSD còn đủ dung lượng.
2. Double-click shortcut **`Ebook Reader`** ở thư mục gốc hoặc mở **Ebook Reader** từ Start Menu.
3. Lần đầu, file này tự cài môi trường và tải model; khi nâng cấp, setup tái sử dụng venv/model cache thay vì xóa runtime cũ.
4. Trong ứng dụng, chọn nhiều file TXT hoặc chọn một folder chứa các chapter TXT.

Khi muốn chuyển từ project đang mở sang đầu vào khác, bấm **Book mới**. Settings hiển thị của project cũ
được đồng bộ từ cấu hình đã khóa, nên thay đổi control trên màn hình không thể âm thầm đổi giọng khi resume.

Không cần tự mở PowerShell hoặc chạy file setup riêng. Launcher hiện một console ngay khi bắt đầu,
liên tục báo trạng thái trong lúc GUI đang nạp và tự đóng console ngay khi chính GUI báo đã hiển thị.
Nếu source mới chỉ thiếu dependency Python, launcher repair tăng dần mà không cài lại PyTorch/model.
Mọi phiên khởi động được ghi vào `_internal/runtime/logs/startup.log`; khi lỗi, console không tự đóng.
Nếu Ebook Reader đã chạy, lần mở tiếp theo chỉ đưa cửa sổ hiện có lên trước thay vì tạo instance thứ hai.

## Chạy hoàn toàn nền

CLI chính thức không mở GUI hay console con, dùng cùng pipeline/SQLite/checkpoint với ứng dụng và mặc định
khởi động worker ẩn ở mức ưu tiên thấp. Từ thư mục `_internal`, có thể tạo đúng một dải chapter và chạy ngay:

```powershell
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli create `
  --source-dir "D:\Books\Text_Tmp" --range 000..099 `
  --output-root "C:\Users\<user>\Audiobooks" --title "Tên sách" `
  --profile high_quality --start --json
```

Nên thêm `--dry-run` ở lần đầu để xác nhận chính xác số file, file đầu/cuối, manifest hash và đường dẫn project
mà không ghi dữ liệu. Các lệnh vận hành còn lại:

```powershell
# Không nạp model; kiểm tra dependency/tool/cache cơ bản
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli doctor --json

# Đọc trạng thái/QA/log mà không migrate hoặc ghi SQLite
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli status "<project-root>" --json
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli report "<project-root>" --json
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli log "<project-root>" --lines 100

# Yêu cầu dừng tại checkpoint an toàn; chạy lại `run` để resume
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli stop "<project-root>" --timeout 60 --json
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli run "<project-root>" --json

# Test từng tầng hoặc toàn bộ, không mở model/GUI thật
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli test parser casting asr-policy audio db recovery pipeline-mocked --json
.\runtime\.venv\Scripts\python.exe -m ebook_reader.cli test full --json
```

`status`, `report`, `log` và `create --dry-run` là read-only. Lệnh `run` chỉ trả thành công sau khi worker đã
giữ được project lock và xác minh settings/source; PID, thời điểm tạo process, project và instance token đều
phải khớp trước khi stop cưỡng bức, tránh tác động nhầm một lượt chạy mới.

## Những gì nằm ở thư mục gốc

```text
Ebook Reader/
├── Ebook Reader.lnk  # shortcut ứng dụng có icon, trỏ thẳng tới _internal\Ebook Reader.vbs
├── README.md     # hướng dẫn sử dụng
└── _internal/    # chứa Ebook Reader.vbs, source, setup, test, model cache và tài liệu kỹ thuật
```

Người dùng bình thường không cần mở `_internal`. Tài liệu dành cho agent/lập trình viên cũng được giữ bên trong thư mục này.

## Cách xử lý một book

- Tool natural-sort các chapter theo tên file.
- Phân tích toàn book trước để xây character registry theo speaker name, cách phát âm và voice casting thống nhất.
- Nếu stream Ollama kết thúc dở, app chia đôi batch hiện tại và tiếp tục với các batch nhỏ hơn. Nếu JSON
  đã kết thúc nhưng vẫn thiếu ID bắt buộc sau các lần retry, app cũng chia batch thay vì dừng cả book.
  Ollama do app tự chạy ghi stdout/stderr vào
  `_internal/runtime/logs/ollama-server.log` để chẩn đoán runner/GPU khi có lỗi.
- Người dùng lọc preset người kể theo giới tính và miền ngay trong Thiết lập; dropdown chỉ hiện tên của
  toàn bộ giọng Bắc, Nam và Trung không thuộc kiểu tin tức. Label `Giọng kể chuyện` là header foldout
  với chevron nhỏ cùng style dropdown ở đầu; bên dưới có ba dòng con thụt vào khoảng chiều rộng bốn chữ `o`
  và có ba dòng con theo thứ tự: `Nghe thử`, `Giới tính`, `Miền`. Phạm Tuyên và Ngọc Linh
  đứng đầu danh sách. Hai dòng lọc giới tính/miền chỉ hiện khi giọng kể chuyện còn được chỉnh sửa;
  dòng nghe thử vẫn giữ lại khi thiết lập sách đã khóa.
- Chọn một preset trong dropdown sẽ tự phát WAV preview; nút `Nghe thử` cho phép nghe lại. App đóng gói
  sẵn preview cho cả 10 preset hợp lệ nên không nạp model TTS chỉ để nghe thử.
- Chất lượng và giọng người kể được lưu cùng sách và khóa sau khi sách bắt đầu. Chế độ tài nguyên
  và ngưỡng GPU là setting global, không tạo sách mới khi thay đổi và được worker nhận tại checkpoint kế tiếp.
  Bấm `Sách mới` đặt lại thiết lập sách về `Chất lượng cao`, mọi giới tính, mọi miền và giọng `Phạm Tuyên`,
  nhưng giữ nguyên hai thiết lập global này. Nút này chỉ bật khi đang mở một sách đã tồn tại; trong bản
  nháp sách mới chưa chạy, nút bị vô hiệu hóa vì không có sách cũ nào cần rời khỏi.
- Nhân vật có tên ưu tiên cao nhất giọng tự nhiên miền Bắc, tiếp theo là giọng tự nhiên miền Nam. Các giọng còn lại
  giữ thứ tự Bắc → Nam và tự nhiên → kể chuyện. Preset tin tức không được
  phân vai; giọng Trung chỉ tham gia pool NPC vô danh/cục bộ ngắn sau các giọng phổ thông để tăng đa dạng có kiểm soát.
- Nhân vật phụ có dấu hiệu cục bộ như “áo xanh”, “áo đỏ” được giữ thành hai vai riêng trong cuộc thoại;
  trường hợp thực sự không phân biệt được vẫn tách tối thiểu theo nam/nữ/chưa rõ.
- Voice được khóa theo normalized speaker name trên toàn sách: mọi `Lucien` ở mọi chapter bắt buộc dùng cùng
  một character/voice profile. Hai tên khác nhau như `Hạ Phong` và `Lucien` không được tự hợp nhất dù câu chuyện
  cho thấy nhân vật đổi tên, đổi thân phận hoặc chuyển sinh. Tên xuất hiện trong cách gọi trực tiếp như
  “Anh Lucien!” hoặc “Iven, …” không được dùng làm speaker;
  nếu người nói chưa rõ danh tính, app giữ một vai NPC cục bộ riêng và ghi warning thay vì đổi nhầm giọng.
- Mỗi nhân vật giữ nguyên một preset và một biến thể cao độ. Khoảng hạ giọng được giới hạn
  theo cao độ median đo từ preview: Phạm Tuyên không bị hạ, Xuân Vĩnh/Thái Sơn/Ngọc Trân chỉ hạ tối đa
  `-1`, các preset còn lại hạ tối đa `-2`; mọi preset chỉ nâng tối đa `+2` bán âm. Khi nhiều vai
  dùng chung preset, biến thể này tạo khác biệt vừa phải mà không đổi tốc độ; cảm xúc không đổi
  sang người đọc khác giữa chừng.
- Mọi độc thoại nội tâm dùng giọng người kể, không xác định và không lưu danh tính nhân vật đang nghĩ.
- Tên tiếng Anh được đối chiếu với CMU Pronouncing Dictionary đóng gói cục bộ; chuỗi âm vị tiếng Anh
  được Qwen chuyển thành âm tiết thuần Việt như `Michael → Mai-cồ`, `Gary → Ga-ri`. Tên fantasy không có
  trong từ điển vẫn được xét theo ngữ cảnh. Cách đọc được khóa trong SQLite theo sách, áp dụng đồng nhất
  cho mọi giọng, chapter, lần resume và câu đối chiếu ASR. Mỗi tên hợp lệ được checkpoint riêng; ranh giới
  âm tiết kiểu `A-der-on` được sửa cơ học thành `A-đe-ron`, còn retry chỉ gửi lại đúng các tên vẫn chưa hợp lệ
  cùng lý do từ chối thay vì chạy lại toàn batch với cùng prompt.
- Ở profile chất lượng cao, metadata delivery do Qwen đề xuất phải qua semantic/host gate và một lượt director critic
  thứ hai trước khi checkpoint. Generator và critic dùng cùng model nên đây chỉ là self-review có kiểm soát; critic
  không được phép vượt qua luật tất định hoặc âm thầm sửa field. Candidate, request intent, evidence, model digest và
  ngân sách retry được ghi vào ledger SQLite trước/sau request, vì vậy kill giữa chừng sẽ tiếp tục đúng candidate thay
  vì reset vòng phản biện. Batch đã được critic chấp nhận có thể hoàn tất transaction sau khi resume mà không gọi Ollama lại.
- Sau khi khóa settings/giọng, tool tạo và kiểm tra audio theo từng chapter.
- Mỗi file TXT luôn tạo đúng một MP3 chapter tương ứng; app không tự ghép thêm MP3 toàn book.
- Từ tượng thanh như `rầm`, `uỳnh` ở nguyên trong câu của người kể hoặc nhân vật, được đọc và kiểm tra tốc độ như
  nội dung bình thường. Cụm cảm thán như `ha...`, `haiz...`, `hừm...` cũng giữ speaker/kind của câu gốc.
- App không dùng các cue phi ngôn ngữ thử nghiệm của VieNeu. Chỉ bản sao `spoken_text` đưa vào TTS được chuẩn hóa,
  ví dụ `haizzzzz → hầy`, `[cười] → ha ha`, `[thở dài] → hầy`; văn bản và hash nguồn trong SQLite không đổi.
- Giao diện hiển thị tiến độ riêng cho chuẩn bị văn bản, phân tích, phân vai, tạo audio, Whisper,
  sửa lỗi, ghép MP3 và xuất báo cáo.
- Nút **Bắt đầu** chỉ bật khi đã có chapter nguồn. Mỗi dòng Log có timestamp để phân biệt tiến trình
  đang chạy với thông tin cũ.
- Trong lúc chạy, tool không dừng để hỏi lựa chọn. Trường hợp mơ hồ được xử lý theo policy và ghi vào report.

## An toàn và phục hồi

- WAV/MP3 ghi qua file `.part`, kiểm tra rồi mới atomic rename.
- SQLite là nguồn trạng thái chính; không coi file tồn tại là đã hoàn tất.
- Candidate analysis đã qua host gate và mọi attempt critic cũng là checkpoint bền trong SQLite. Event ACCEPTED,
  pronunciation proposal và toàn bộ segment trong batch chỉ chuyển trạng thái cùng một transaction có CAS/hash;
  không có trạng thái nửa batch hoặc evidence gắn nhầm candidate sau crash.
- Mỗi project chỉ cho phép một worker; settings trong SQLite và source hash được kiểm tra lại khi resume.
- Byte TXT dùng để segment phải khớp đúng hash đã khóa; source đổi ngay trong lúc đọc cũng làm job dừng.
- Có thể đóng hoặc kill app bất kỳ lúc nào; phần đang dở được tạo lại, phần đã commit được giữ.
- Giao diện chỉ có một nút **Dừng**; worker kết thúc ở ranh giới gần nhất và lần sau có thể tiếp tục.
- Bấm `X` chỉ ẩn cửa sổ xuống system tray để worker tiếp tục. Chọn **Thoát hoàn toàn** trong menu tray
  mới kết thúc app và cả cây process con; transaction SQLite, file `.part`, atomic replace và recovery
  bảo vệ dữ liệu đã commit.
- Không chèn im lặng để che đoạn TTS bị lỗi.
- Mức âm lượng được cân bằng theo K-weighted LUFS của từng segment trước khi ghép chapter;
  giọng kể chuyện có anchor nhỉnh hơn hội thoại trung tính, còn khoảng cách của `loud` được giữ nhỏ. Chỉ các
  chỉ dẫn như thì thầm, quát hoặc cao trào mới chủ động lệch khỏi mức chuẩn.
- Xử lý pitch dùng WORLD vocoder chuyên cho tiếng nói: tách F0, spectral envelope và aperiodicity,
  chỉ thay đường F0 rồi tổng hợp lại để giữ formant/chất giọng và nguyên thời lượng. Nếu đoạn
  phi ngôn ngữ không có đủ voiced frame hoặc bước pitch hiếm khi lỗi, app giữ waveform gốc và ghi warning
  thay vì tạo lại lời đọc hoặc làm hỏng chapter.
- Giới hạn sinh audio được tính theo độ dài và pace của từng segment để một câu rất ngắn không chạy tới
  trần toàn cục của model. Ngân sách frame VieNeu và giới hạn kiểm tra dùng chung một chính sách thời lượng,
  nên app không thể vừa cho model sinh dài hơn rồi tự từ chối chính kết quả đó. Sai lệch tốc độ nhẹ được ghi
  warning và chuyển qua Whisper; chỉ sai lệch cực đoan mới retry.
- Câu chỉ có một từ ngắn dùng tối đa 24 frame và sampling thận trọng hơn để VieNeu không có khoảng sinh dư
  rồi nối thêm lời ngoài văn bản. Riêng tiếng thở `Ha...` đứng độc lập được gửi thành `Hà... hà...` để tạo
  hai âm vị tiếng Việt rõ; tiếng kéo dài như `Aaaaah`/`Uuu` cũng được đổi thành hai âm tiết ổn định. Output dùng
  hết `max_new_frames` được đánh dấu để kiểm tra tín hiệu và Whisper, không còn bị kết luận sai chỉ từ độ dài.
- Mọi segment narration/dialogue/thought đều dùng chung chính sách thời lượng, kiểm tra tốc độ khi đủ dài và đối chiếu
  Whisper bằng đúng `spoken_text`. App không cắt audio để lách validation; kết quả quá dài phải retry hoặc thất bại.
- Transcript dài bất thường và gần như không liên quan tới câu nguồn chỉ được coi là mismatch nghiêm trọng khi số
  từ còn có thể tồn tại trong thời lượng WAV. Transcript có tốc độ vật lý bất khả thi được đánh dấu là Whisper
  hallucination, không dùng để kết luận TTS nói thêm lời.
- Circuit breaker chỉ đếm các segment TTS thất bại hoàn toàn liên tiếp với cùng nguyên nhân và reset sau mọi segment
  thành công; lỗi rải rác ở nhiều chapter không bị cộng dồn để dừng cả sách.
- Whisper đọc và resample WAV ngay trong process, không bật FFmpeg console theo từng segment.
- Phản hồi JSON từ Ollama có giới hạn schema, token và thời gian theo batch. Trong lúc chờ, app ghi
  nhịp hoạt động mỗi phút; bấm **Dừng** sẽ đóng stream thay vì đợi hết timeout dài.
- Khi Ollama chưa chạy, Ebook Reader tự mở `ollama serve` ở chế độ ẩn và tự dừng tiến trình đó sau khi
  phân tích/phân vai xong. Một Ollama đã chạy từ trước được coi là tiến trình bên ngoài và không bị tự ý kill.
- Sau mỗi lần VieNeu tạo audio hoặc trả lỗi, app thu hồi cache inference. Nếu RAM tụt tới mức critical giữa hai
  segment, app unload model/cache rồi đo lại; chỉ tự dừng, giữ checkpoint và gửi Windows notification khi RAM
  vẫn không hồi phục. Critical SSD/GPU/driver và lỗi nghiêm trọng vẫn dừng ngay tại ranh giới an toàn.
- Resource Manager tự nhường CPU/GPU/RAM/SSD cho ứng dụng foreground, sau đó tự tăng tải lại khi máy rảnh.

## QA nghe tự động

- Mỗi WAV phải qua kiểm tra tín hiệu và đối chiếu nội dung bằng Whisper; WAV đủ dài còn được UTMOSv2 so với preview đã khóa của đúng giọng đọc trước khi chapter được xuất bản.
- Mỗi lượt nghe Whisper (direct/repeated, beam/greedy) có evidence riêng gắn với checksum WAV. Lặp câu ngắn chỉ được
  dùng để nâng một verdict thành đạt; nếu lượt lặp vẫn lỗi, tool giữ transcript và metric direct tốt hơn thay vì che lỗi.
- Tên tiếng Anh đã khóa phát âm được kiểm tra như anchor riêng ở từng lượt giải mã. Tool chỉ chấp nhận đúng spelling
  nguồn, đúng chuỗi âm tiết đã khóa hoặc dạng ghép âm tiết xác định; các alias gần giống như `Lucy/Lucian` không thể
  lọt qua chỉ vì metric của cả câu vẫn cao.
- Khi hai lượt Whisper xác nhận mismatch, tool tạo lại bằng delivery `clarity`: giữ nguyên nhân vật, giọng, pitch và
  câu đọc, chỉ giảm độ ngẫu nhiên của sampling. WAV sửa chỉ được duyệt khi cả beam và greedy đều đạt; số vòng được
  checkpoint nên dừng/chạy lại không bỏ qua xác nhận hoặc sửa vô hạn.
- UTMOSv2 chỉ là bằng chứng bổ sung về độ tự nhiên, không thay thế Whisper và không tự chứng minh audio đạt. Baseline được khớp theo đúng giọng và mức pitch thực tế. Câu ngắn dưới `1,5` giây được miễn MOS sau khi smoke thật cho thấy model dễ phạt sai câu cảm xúc ngắn; nội dung của chúng vẫn bắt buộc qua Whisper.
- Segment bị UTMOS yêu cầu review được tạo lại tối đa hai vòng bằng seed mới; mỗi vòng đều phải qua lại Whisper và UTMOS. Nếu vẫn không đạt, chapter bị giữ lại thay vì xuất bản hoặc lặp vô hạn cùng một WAV.
- `audiobook_quality_report.json` ghi final transcript/CER-WER, từng decode evidence, verdict, MOS, baseline, độ lệch,
  checksum và policy cho từng segment. Một chapter chỉ được tính đạt khi toàn bộ segment có evidence hiện hành,
  không còn warning chặn và MP3 qua mastering/decode/checksum.
- Setup tải checkpoint và hai snapshot model nền theo revision bất biến vào `_internal/runtime`, rồi smoke-load hoàn toàn offline. Worker chất lượng cao kiểm toàn bộ runtime contract trước recovery nên không phân tích/TTS cả sách rồi mới phát hiện thiếu model.

## Đầu ra

Mỗi book được lưu thành một project riêng với database, log, audio trung gian và thư mục `output` chứa MP3 chapter,
playlist, `pronunciations.json`, metadata tùy chọn và report. Project đã hoàn tất chỉ xác minh MP3/checksum rồi thoát nhanh,
không cần khởi động Ollama, không băm lại toàn bộ WAV hoặc ghép lại full-book nếu artifact vẫn nguyên vẹn.

## Trạng thái alpha

Kiến trúc, recovery, resource policy và pipeline mock đã có test. Các model thực, Windows notification và hành vi CUDA/RTX 5060 vẫn cần smoke test trên máy đích với một chapter khoảng 2.000–5.000 từ trước khi chạy book rất lớn.

Tài liệu kỹ thuật và kết quả test nằm trong `_internal/docs/`.
