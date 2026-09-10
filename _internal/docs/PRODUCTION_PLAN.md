# Kế hoạch chạy cả cuốn: 478 chương, 16 lô

Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động toàn bộ cho
ra sản phẩm"*, và về phân lô: *"phân lô thế nào cũng được, đừng để phân tích bị sai do phân lô
có vấn đề là được"*.

Câu thứ hai đã được đo và trả lời: **phân lô không làm hỏng phân tích** — xem
[VERSIONS.md](VERSIONS.md), mục *"Phân lô có làm hỏng phân tích không?"*. Tài liệu này là câu
trả lời cho câu thứ nhất: chạy hết 478 chương thì tốn bao nhiêu và đi theo đường nào.

## Toàn cảnh

```
478 chương · 1.125.675 từ · 58.258 segment
16 lô, mỗi lô ~8 giờ máy (~3.700 segment)
tổng ~128 giờ máy  ≈  5,3 ngày chạy liên tục
```

Sinh bằng `scripts/plan_batches.py "D:/Novels/Tools/Text" --hours 8`. Cân theo **giờ máy**,
không theo chương và cũng không theo từ: máy tính tiền theo **segment**, và cùng một số từ thì
số segment chênh tới 40% giữa chương nhiều đối thoại và chương tự sự. Chia theo 73.000 từ cho
ra những lô lệch nhau tới 2,7 giờ; chia theo giờ máy cho ra 15 lô trong khoảng 7,9–8,2 giờ và
một lô cuối 5,9 giờ.

| lô | chương | số chương | segment | giờ máy | |
|---|---|---|---|---|---|
| 1 | 000..029 | 30 | 3.727 | 8,1 | ← `lo01b_768c98bb4f`, chạy lại 2026-09-08 19:45 |
| 2 | 030..059 | 30 | 3.762 | 8,1 |  <!-- giờ cho máy rảnh; xem THE_MACHINE_IS_SHARED.md -->
| 3 | 060..091 | 32 | 3.675 | 7,9 |
| 4 | 092..118 | 27 | 3.795 | 8,2 |
| 5 | 119..144 | 26 | 3.720 | 8,0 |
| 6 | 145..166 | 22 | 3.636 | 7,9 |
| 7 | 167..192 | 26 | 3.692 | 8,0 |
| 8 | 193..221 | 29 | 3.713 | 8,0 |
| 9 | 222..252 | 31 | 3.735 | 8,1 |
| 10 | 253..278 | 26 | 3.693 | 8,0 |
| 11 | 279..305 | 27 | 3.678 | 7,9 |
| 12 | 306..342 | 37 | 3.701 | 8,0 |
| 13 | 343..375 | 33 | 3.670 | 7,9 |
| 14 | 376..406 | 31 | 3.634 | 7,9 |
| 15 | 407..447 | 41 | 3.706 | 8,0 |
| 16 | 448..477 | 30 | 2.721 | 5,9 |

## Chương 000–027 đã có audio rồi — vẫn phải làm lại

Ba lô đầu tiên của lịch sử (`000..009`, `010..018`, `019..027`) đã chạy xong, nhưng bằng **mã
cũ**, và mã ấy có bốn lỗi đã sửa từ đó:

| lỗi | ảnh hưởng lên audio đã có |
|---|---|
| nhịp đọc đếm chữ số thay vì chữ đọc | tiêu đề chương bị chấm sai, có chương trượt oan |
| ngoặc kép không đóng làm dừng cả sách | 8 chương nguồn không segment được |
| bản thu chạm trần khung không được thu lại | đoạn lảm nhảm lọt vào sách |
| `k`/`c` trong kiểm phát âm tên | tên đúng bị chấm sai |

Audio cũ **không sai ở chỗ nghe được** trong đa số trường hợp, nhưng nó được duyệt bởi những
phép kiểm đo nhầm thứ — nên "đã qua" ở bản cũ không nói lên điều gì về bản hiện tại. Lô 1 của
kế hoạch này (`000..029`) chạy đè lên chúng, và đó là lý do bảng trên bắt đầu từ 000 chứ không
từ 028.

## Lô vá là chỗ TỆ để chứng minh một bản vá

Ba bản vá giờ nằm ở đúng cùng một vị trí, vì đúng cùng một lý do:

| bản vá | chạy lại ở | vì sao không chứng minh được |
|---|---|---|
| `patch_ceiling_repairable` | alpha.62 | đoạn `'"Gì cơ?"'` lần sau dài 0,56s, không chạm trần |
| `patch_pace_relaxed_is_a_decision` | lô vá lô 1 | đoạn nhịp lần sau đọc 14,07 ký tự/giây, vừa qua sàn |
| `patch_finished_take_beats_a_cut_off_one` | lô vá lô 2 | đoạn `'"Bất bại?"'` lần sau dài 1,36s, không chạm trần |

Cả ba lỗi **phụ thuộc seed**: chúng là tính chất của một lần lấy mẫu cụ thể từ model, không phải
của văn bản. Chạy lại là **rút một lá khác**, nên một lô vá ba chương cho ba lá — xác suất trúng
lại đúng lá cũ rất thấp. Ba lần liên tiếp không trúng không phải trùng hợp; đó là điều đáng
mong đợi.

Chỗ chúng được chứng minh là **lô kế tiếp**: ba mươi chương mới cho ba mươi lá mới. Và điều ấy
đã xảy ra thật hai lần:

- `patch_edge_fade` + `patch_loudness_review_ships` được chứng minh trên lô vá (ba chương chạy
  lại đều đo được số mới) **và** ở quy mô trên lô 2: 0 chương hỏng ở tầng QA chương so với 3.
- `patch_rate_impossible_is_the_same_family` được chứng minh trên lô vá lô 2, chương 031: đoạn
  tiếng cười **tái diễn** (Whisper phiên `'Há há há…'` 19 lần), mã vẫn nổ, nhưng giờ là `warning`
  chứ không `failed` và chương xuất bản được. Chương 043 thì lỗi không tái diễn — chỉ 10 lần
  "ah" nên không vượt ngưỡng — nên **043 không chứng minh gì**, và nói nó chứng minh là nhầm
  một chương xanh với một bản vá đã chạy.

Bài học thực dụng: sau một lô vá, đừng hỏi "chương xanh chưa?" mà hỏi **"mã ấy có xuất hiện lại
không, và nó đi đường nào?"**. Với ba bản vá trên, câu trả lời là "chưa xuất hiện lại", và cột
*đã chứng minh* trong [WHAT_BLOCKS_A_CHAPTER.md](WHAT_BLOCKS_A_CHAPTER.md) phải ghi "chưa".

## Khi một lô có chương hỏng: một lệnh nữa

```bash
bash scripts/launch_repair.sh 2      # lô vá cho lô 2
```

Nó đọc chương hỏng **từ chính SQLite của lô** chứ không từ danh sách người gõ lại, in cảnh báo
của `plan_repair_batch.py` trước khi chạy, đi qua `before_a_batch`, rồi chạy **từng chương một**
theo thứ tự — chúng tranh nhau cùng một GPU nên chạy song song không nhanh hơn.

Nó **từ chối** khi lô chưa chạy xong, vì lúc ấy mọi chương chưa tới lượt đều đọc thành "cần vá",
và một danh sách như thế là chạy lại thừa cả chục chương.

Vì sao từng chương chứ không một dải: `--range` nhận một dải liên tục, còn chương hỏng thì rải
rác. Đo trên lô 1: chạy lại cả lô ~13 giờ, chạy lại bốn chương hỏng ~4 giờ.

## Ghép cuốn sách: theo số chương, KHÔNG theo tên file

```bash
python scripts/assemble_book.py                          # liệt kê, không chép
python scripts/assemble_book.py --apply --out <thư mục>  # chép thật
```

Cái bẫy ở đây im lặng. Tên MP3 có dạng `00004_003.mp3`, và **tiền tố là số thứ tự trong
project, không phải số chương**: chương 003 là `00004_003.mp3` ở lô 1 nhưng `00001_003.mp3` ở
lô vá, vì tiền tố đếm theo dải chương mà project ấy bao. Gom 16 lô bằng cách sắp theo tên file
là xáo trộn cả cuốn sách, và không ai nhận ra cho tới khi ngồi nghe.

Nguồn sự thật là `chapters.title`. Khi một chương có ở nhiều lô, bản `completed_at` muộn nhất
thắng, và script in ra mọi bản thua.

**Cảnh báo quan trọng nhất của nó** là khi một chương phải **lùi về một lô cũ hơn**: nghĩa là
một lô mới hơn đã chạy chương ấy và không cho ra MP3, nên bản đang dùng mang dàn giọng và cách
đọc của phiên bản cũ. Đo lúc viết, trước khi lô vá xong:

```
CẢNH BÁO: 1 chương phải lùi về một lô CŨ HƠN lần chạy gần nhất.
  chương 016: đang lấy v0.2.0-alpha.56
```

Chín phiên bản trước, dàn giọng khác. **Không cổng nào bắt được** — mỗi chương tự nó vẫn hợp
lệ, chỉ có cuốn sách là không nhất quán. Đó là lý do phép kiểm này tồn tại ở tầng ghép chứ
không ở tầng chương.

## Đĩa: không phải chuyện cần lo, đo một lần cho xong

`min_free_disk_gb = 12` là một cửa chặn thật, nên đáng đo trước chứ không đáng gặp lúc lô 12
đang chạy. Đo 2026-09-09:

```
D:  tổng 954 GB, còn trống 590 GB
lô 1 (30 chương, cả WAV từng đoạn lẫn MP3)  =  3,35 GB
16 lô  ->  ~54 GB
```

Còn dư hơn mười lần. Không cần dọn gì giữa các lô, và cũng **không nên** dọn: giữ WAV từng đoạn
là thứ cho phép `compare_runs.py` và `discarded_cures.py` truy lại chuyện đã xảy ra.

## Dự đoán cho lô 2, viết TRƯỚC khi chạy

Ghi ở đây để nó sai được. Giải thích sau khi biết kết quả thì lúc nào cũng khớp.

Lô 1 hỏng 4 trên 30 chương vì **ba** nguyên nhân — `join discontinuity` đánh hai chương, và
đó chính là hình dạng rẻ tiền mà mục này nói tới:

```
000  loudness delta 0,62 LU          -> patch_loudness_review_ships
003  join discontinuity 0,219        -> patch_edge_fade
016  join discontinuity 0,216        -> patch_edge_fade
007  TTS_PACE_BAND_RELAXED           -> patch_pace_relaxed_is_a_decision
```

Cả bốn đã vào cây và ba đã được chứng minh trên audio thật ở lô vá. Nếu chúng đủ, **lô 2 phải
hỏng 0–1 chương trên 30** — và bất kỳ chương nào hỏng cũng phải hỏng vì một nguyên nhân *chưa
từng thấy*, không phải vì bốn cái trên.

Hai kết cục và điều mỗi cái nói:

- **Hỏng 0–1, nguyên nhân mới** → chiến lược "chạy một lô, vá theo cái nó hỏng" đúng, và đuôi
  nguyên nhân đang cạn. Cứ thế đi tiếp mười bốn lô còn lại.
- **Hỏng 3–5, toàn nguyên nhân mới** → đuôi **không** cạn: mỗi lô sẽ đẻ ra bốn nguyên nhân mới
  vô hạn, và vá từng cái là đuổi theo chứ không phải về đích. Lúc ấy đáng dừng lại hỏi vì sao
  chính sách high_quality lại có nhiều cửa chặn độc lập đến thế, thay vì vá cửa thứ tám.

Con số đáng đếm là **số nguyên nhân khác nhau**, không phải số chương hỏng: một nguyên nhân
đánh sáu chương thì rẻ hơn nhiều so với sáu nguyên nhân mỗi cái đánh một chương.

`python scripts/plan_repair_batch.py <project>` in thẳng con số ấy:

```
3 nguyên nhân khác nhau trên 4 chương:
  2x  QA chương: join discontinuity   (003, 016)
  1x  QA chương: loudness delta       (000)
  1x  cảnh báo segment: TTS_PACE_BAND_RELAXED   (007)
```

## Một chương không phải truyện, và đúng một chương thôi

`000.txt` dài 137 ký tự và không phải nội dung tiểu thuyết — nó là ghi chú của người đăng về
mấy tấm fan art ("các bức ảnh trên"), những tấm ảnh không có trong file text. Đường ống đọc nó
thành 2 segment và xuất ra một MP3 191 KB, mất khoảng một phút.

Tôi gắn cờ đây là "chủ sách phải quyết", rồi đo trước khi hỏi:

```
478 file       trung vị 10.504 ký tự     max 19.382
ngắn nhất      000.txt      137
ngắn nhì       277.txt    5.971          <- gấp 43 lần chương 000
```

Không có đám chương-không-phải-truyện nào ẩn trong nguồn; **000 là ngoại lệ duy nhất**, và cái
giá của nó là một phút GPU. Nên không có gì để quyết ở quy mô sản xuất. Nếu chủ sách không muốn
nghe ghi chú ấy ở đầu sách thì xoá `000.txt` khỏi thư mục nguồn là đủ — đó là quyết định biên
tập, không phải quyết định kỹ thuật, và đường ống không nên tự đoán file nào "không đáng đọc".

## Mọi con số giờ ở trên là cho **máy rảnh**

Đo ngày 2026-09-09 trên chương 003 của lô vá: 121 segment tốn 27,0 phút, trong khi ở tốc độ
`maximum` chỉ cần 9,2 — **chậm gấp 2,9 lần**, vì máy đang mở ba Unity.exe và Rider (~9,5 GB
trên 31,3 GB) và bộ điều tiết nhường chỗ cho chúng.

Nhường như thế là đúng. Nhưng nó nghĩa là lô 2 có thể mất ~23 giờ chứ không phải 8,1, và quan
trọng hơn: **một lô chậm ba lần không phải một lô treo**. Phân biệt bằng nhịp tim và dòng
`Resource mode:` trong `runtime_events`, không bằng cảm giác. Chi tiết và cách đo lại:
[THE_MACHINE_IS_SHARED.md](THE_MACHINE_IS_SHARED.md).

## Trước mỗi lô

```bash
python scripts/before_a_batch.py
```

Nó kiểm năm thứ và **từ chối** nếu có cái nào chưa đạt: có lô đang bay, cây git chưa sạch, bản
vá còn trong hàng chờ, model giọng lệch revision đã ghim, bộ test đỏ.

Kỷ luật này ra đời từ một cái giá thật (xem mục *"Lô 1 chết một lần"* bên dưới): sửa mã giữa lô
làm `resume` bị từ chối, nên mất **toàn bộ** phần phân tích đã làm chứ không chỉ phần còn lại.
Với lô 13 giờ thì mười phút kiểm trước rẻ hơn nhiều. Nhưng một kỷ luật chỉ nằm trong tài liệu
là kỷ luật phụ thuộc trí nhớ, nên nó thành script.

## Chạy một lô: một lệnh

```bash
bash scripts/launch_batch.sh 2      # lô 2
bash scripts/launch_batch.sh 3      # lô 3
```

Nó làm đủ `before_a_batch` → `create` → ba bước gieo → `run`, đúng thứ tự dưới đây, và **đọc
dải chương từ chính bảng ở đầu tài liệu này**.

Điểm ấy quan trọng hơn nó nghe: bản đầu của script tính dải bằng `(n−1)×30`, và nó **đúng cho
lô 1 và lô 2 rồi sai từ lô 3**, vì kế hoạch chia lô **theo số từ** chứ không theo số chương —
lô 3 là 32 chương (060..091), lô 4 là 27 (092..118). Một script tự tính lại sẽ lặng lẽ phá đúng
cái chỉ thị đã dựng nên bảng này. Nếu không tìm thấy dòng cho số lô, script **từ chối** thay vì
đoán.

Nó cũng tự tìm project của lô liền trước để gieo, nên dây gieo không đứt vì gõ nhầm đường dẫn.

## Đường đi mỗi lô, không được đổi thứ tự

Nguyên văn ở [VERSIONS.md](VERSIONS.md); tóm tắt để khỏi phải mở hai file:

```
create  →  port_pronunciations  →  port_casting  →  seed_listener_acceptances  →  run
```

**Gieo từ lô liền trước**, tạo thành một dây. Đứt một mắt là mất một thứ cụ thể, và cái mất
lớn nhất là `port_pronunciations`: cách đọc một cái tên đổi thì audio đổi, mà phán quyết của
người nghe khoá theo checksum audio — nên mất cách đọc là mất luôn mọi lần nghe đã bỏ ra.

Kiểm rẻ nhất ngay sau `create`: tên thư mục project phải chứa hash của **dải ấy**. Hash phụ
thuộc dải chứ không chỉ nguồn, nên chỉ so được giữa hai lượt cùng dải. Hash đã biết:

```
000..009  02502ba320      019..027  7b4c5ae6cc
010..018  70f7c62800      000..029  768c98bb4f   (lô 1, sau khi lọc thuỷ ấn)
```

`768c98bb4f` được đo **sau** khi `patch_strip_zero_width` vào cây, nên nó đã tính cả việc bỏ
ký tự vô hình. Một lượt tạo lại dải ấy trên mã cũ hơn sẽ ra hash khác, và đó là đúng.

## Còn cái gì có thể dừng cả dây

Sau [cơ chế xuất bản khi không có ai để hỏi](SHIPPING_WITHOUT_A_LISTENER.md), không còn chỗ nào
trong đường ống **dừng lại đợi người**. Chương hỏng thì hỏng riêng chương ấy và lô vẫn đi tiếp.

Ba cửa dừng cứng đã đóng, và cửa thứ nhất vừa được xác nhận ở quy mô cả cuốn:

```
scripts/check_sources.py "D:/Novels/Tools/Text"
478 chương chia đoạn được hết — 58,258 segment
```

**Cách rà ấy mù một lớp, và lô 1 chứng minh.** Tôi tìm "cửa dừng cứng" bằng cách liệt kê mọi
câu `raise` trong đường ống và xét từng cái. Phương pháp ấy tìm ra những lần dừng **có chủ ý**
— và bỏ sót hoàn toàn những lần dừng **do tai nạn**: một `UnicodeEncodeError` từ thư viện
chuẩn, ném ở một dòng không ai viết `raise`. Đó chính là thứ giết lô 1.

Rà đúng phải hỏi ngược lại: *dữ liệu nào từ bên ngoài đi vào mà không qua chỗ nào làm sạch?*
Có ba nguồn ngoài — file nguồn, phản hồi model, và cache model — và tính tới 2026-09-08 cả ba
đều đã có một cửa dọn hoặc một phép ghim. Nhưng danh sách ấy là danh sách tôi tự nghĩ ra, nên
nó cũng có thể thiếu.

58.258 khớp đúng con số `plan_batches.py` đếm độc lập. Cú dừng vì ngoặc kép treo — thứ giết
alpha.55 sau **bốn giây** và trước đây cần tám vòng sửa-tay-chạy-lại — không còn xảy ra ở chương
nào. Hai cửa kia: cách đọc tên không giải được giờ ghi sự kiện rồi đọc nguyên văn thay vì `raise`,
và đoạn ASR không phán xử được giờ có cơ chế tự cho qua.

Hai thứ còn lại có thể làm hỏng một chương, cả hai đã ghi:

1. `"Tiếp theo."` — bản đương nhiệm chạm trần khung, ứng viên tốt hơn bị vứt vì luật giữ
   bản-đương-nhiệm. Đo được **2 ca trên 38.520 đoạn**, ngoại suy ra **khoảng bốn chương** trên
   cả cuốn. Xem [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md).
2. QA tầng chương (`_evaluate_chapter_quality`) — chỗ nối, im lặng, độ to. Máy không được phép
   tự cho qua cổng này, vì nó đo trên chính file âm thanh chứ không đo qua ASR.

## Đừng làm việc nặng trên cùng máy trong lúc lô đang chạy

Đường ống tự nhường CPU khi thấy nền bận — trong log alpha.62 là dòng:

```
Resource mode: yield_heavy — foreground CPU 60%
```

Nghe thì tử tế, nhưng nó có nghĩa là **giờ máy trong bảng trên tính cho một máy rảnh**, và
alpha.62 vừa cho con số của máy bận:

```
ước lượng trong bảng (alpha.55)        :  7,78 giây/segment
alpha.62, chỉ pha tổng hợp, máy bận    : 11,4  giây/segment
alpha.62, ĐẦU-CUỐI (4,81 giờ / 1.357)  : 12,8  giây/segment   ← con số để lập kế hoạch
```

Dòng thứ ba mới là dòng đúng, và tôi viết nhầm dòng thứ hai trước: nhịp pha tổng hợp bỏ qua
pha phân tích, mà pha ấy chiếm gần một phần ba lượt chạy. Lập kế hoạch bằng nhịp một pha là
tự hứa một thời hạn không thể giữ.

Với 12,8 giây/segment đầu-cuối: **58.258 segment ≈ 207 giờ ≈ 8,6 ngày**, không phải 128 giờ /
5,3 ngày. Lô 1 (3.727 segment) rơi vào khoảng **13 giờ**, không phải 8,1.

Cái đắt không phải bản thân số giờ mà là một bảng ước lượng sai 60% và không có gì chỉ ra vì
sao. Cột "giờ máy" trong bảng trên giữ nguyên vì nó là **đầu vào để chia lô cho cân**; nhân với
12,8/7,78 = 1,65 để ra thời gian thật.

Nguồn chiếm RAM hôm ấy: Rider (~3,4 GB), hai Unity (~2,2 GB), và chính các phép đo tôi chạy
trong lúc chờ. Với một lô 8 giờ thì vài phút không đáng kể; với 16 lô nối nhau thì nó cộng dồn
thành nhiều ngày.

Việc đọc-thuần trên project **đã lưu** thì vô hại. Thứ phải tránh là chạy bộ test, quét cả 478
file, hay bất cứ thứ gì giữ một core trong nhiều phút.

## Làm sao biết lô đang chạy hay đã chết

Đừng đoán qua log. Trong alpha.62 log im **14 phút** liền trong lúc mọi thứ hoàn toàn bình
thường, vì đường ống đang sinh candidate với `gpu_scale` bị hạ xuống 0,25. Tôi suýt đọc im lặng
thành chết — lần thứ hai trong ngày, sau khi cũng đọc "CPU phẳng" thành treo ở bộ test.

Thước đo đúng là **nhịp tim của lease**, không phải log:

```bash
python -c "import sqlite3,time; c=sqlite3.connect('file:<project>/project.sqlite3?mode=ro',uri=True);   print([time.time()-r[0] for r in c.execute('SELECT heartbeat_at FROM worker_leases')])"
```

Dưới ~180 giây là sống. `apply_all.py` dùng đúng ngưỡng ấy để từ chối ghi khi có lượt đang bay.

Kèm theo, để đọc đúng những gì thấy trong Task Manager: pool TTS chạy **ba tiến trình
`pythonw` song song, mỗi cái giữ hơn 2 GB**. Cộng với supervisor và worker chính thì lúc cao
điểm ngốn quãng 7–8 GB. Trên máy 31 GB đang mở Rider (~3,4 GB) và hai Unity (~2,2 GB), đường
ống sẽ tự chuyển sang `yield_heavy` và chạy chậm hẳn — nó không hỏng, nó nhường. Nếu muốn lô
chạy đúng số giờ trong bảng thì đóng bớt ứng dụng nặng, còn không thì cộng thêm giờ vào ước
lượng thay vì ngạc nhiên.

## Lô 1 chết một lần, và cái giá của việc sửa giữa lô

`lo01` chạy được 1 giờ 40, phân tích 1.406/3.727 đoạn, rồi dừng cứng:

```
UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83d' - surrogates not allowed
status=error   stage=unrecoverable_error   lease biến mất
```

Model phân tích nhả ra **một nửa cặp surrogate** — một emoji vỡ. `json.loads` dựng nó thành một
`str` hợp lệ trong bộ nhớ mà **không mã hoá UTF-8 được**, nên nó nằm im trong dữ liệu cho tới
lúc `sha256_text` băm bằng chứng critic thì nổ. Đã vá tại **biên nhận**, có test ghim cú nổ.

Mức độ dễ vấp: **script viết chính đoạn tài liệu này cũng chết vì đúng lỗi ấy** vài phút sau,
khi tôi gõ ký tự hỏng thẳng vào một chuỗi Python. Tệ hơn, nó mở file bằng `'w'` — cắt trắng
trước, mã hoá sau — nên `PRODUCTION_PLAN.md` bị xoá sạch và commit mất một nhịp mới phát hiện.
Khôi phục từ commit trước. Nếu nó bẫy được người vừa vá nó xong thì nó bẫy được bất kỳ ai.

**Cái giá:** sửa `analysis.py` đổi hash cài đặt, nên `resume` bị worker từ chối đúng như thiết
kế — *"Analysis/casting implementation changed after analysis started; create a clean
project"*. Mất trọn 1,7 giờ phân tích, phải tạo project sạch (`lo01b`, cùng hash dải
`768c98bb4f` nên chắc chắn cùng nguồn cùng dải).

**Bản vá đã được chứng minh trên dữ liệu thật, trong vòng hai giờ.** `lo01b` chạy tới đoạn
1.406 — đúng chỗ `lo01` chết — và log ghi:

```
Model phân tích trả về nửa cặp surrogate lạc (emoji vỡ); đã bỏ chúng đi.
```

rồi đi tiếp. Cùng nguồn, cùng dải, cùng điểm: một lượt chết, một lượt sống. Đó là loại bằng
chứng mà [bản vá trần khung](WHAT_BLOCKS_A_CHAPTER.md) vẫn chưa có — và sự khác nhau không
phải do bản vá nào tốt hơn, mà do lỗi này **tái diễn** còn lỗi kia thì không.

Tần suất đo được: **1 lần trên 1.411 đoạn phân tích**. Ngoại suy thô sang 58.258 đoạn của cả
cuốn ra khoảng **40 lần** — tức nếu không vá, cuốn sách sẽ chết khoảng bốn mươi lần, mỗi lần
mất toàn bộ phần phân tích của lô đang chạy.

**Bài học cho 15 lô còn lại:** một lỗi kiểu này giữa lô tốn **cả phần phân tích đã làm**, không
chỉ phần còn lại. Chạy bộ test đầy đủ **trước** mỗi lô rẻ hơn sửa giữa chừng.

## Khi một lô có chương hỏng: chạy lô vá, đừng chạy lại cả lô

Lô 1 hỏng 3 trong 8 chương đầu, cả ba vì lỗi đã có bản vá. Cám dỗ là dừng ngay để vá. Đừng —
có đường rẻ hơn:

| phương án | chi phí |
|---|---|
| dừng ngay, vá, chạy lại cả 30 chương | ~13 giờ, và vứt phần đã chạy |
| để chạy hết, vá, chạy lại cả 30 chương | ~22 giờ |
| **để chạy hết, vá, chạy lại CHỈ những chương hỏng** | **~9 + 4 giờ** |

Lý do phương án ba dùng được: chương đã `completed` là sản phẩm hoàn chỉnh, và việc `resume` bị
từ chối sau khi vá chỉ chặn **project ấy** — không chặn việc `create` một project mới bao đúng
dải chương hỏng rồi gieo từ chính lô vừa chạy.

Sản phẩm cuối là các file MP3 gộp từ hai project. Điều đó **không** làm hỏng tính nhất quán
giọng, vì `port_casting` và `port_pronunciations` mang nguyên dàn giọng và cách đọc sang.

Đổi lại, phải chấp nhận một điều và ghi rõ: những chương chạy lại dùng **mã mới hơn** các chương
gốc. Với những bản vá chỉ đổi *cổng chặn* (độ to, nhãn nhịp) thì audio không đổi; với bản vá đổi
*cách sinh* thì có. Ghi lô nào chạy mã nào vào VERSIONS.md, chứ đừng để phải đoán sau này.

## Sau mỗi lô

```bash
scripts/compare_runs.py <lô trước> <lô này>       # chương nào hỏng, gỡ được nhờ đâu
scripts/machine_acceptances.py <lô này> --markdown # đoạn nào chưa ai nghe, ở giây thứ mấy
scripts/audit_audiobook.py <lô này>                # kiểm tổng thể
```

Cột đáng nhìn nhất ở `compare_runs.py` là chỗ nó **tách riêng** chương gỡ được nhờ bản thu khá
lên thật với chương gỡ được nhờ máy tự cho qua. Gộp hai loại lại là cách dễ nhất để tự khen
nhầm, và tôi viết nó ra vì đã suýt làm thế.
