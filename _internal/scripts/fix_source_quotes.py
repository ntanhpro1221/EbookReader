r"""Vá 8 dấu ngoặc kép treo trong nguồn, sau khi `check_sources.py` đã chỉ đúng dòng.

    python scripts/fix_source_quotes.py            # thử trên bản sao, không đụng nguồn
    python scripts/fix_source_quotes.py --apply    # ghi thật

Không tham số thì nó chép cả thư mục nguồn sang scratchpad, vá bản sao, rồi chạy chính bộ
chia đoạn lên toàn bộ để chứng minh bản vá đủ. Đo 2026-09-07: 478/478 chương chia được,
58.260 segment, so với 470/478 và 57.115 trước khi vá.

Tám chỗ dưới đây **không phải máy đoán ra** - `check_sources.py` khoanh vùng, còn chọn dấu
ngoặc thuộc về đâu thì phải đọc đoạn văn. Đáng chú ý là 019.txt: dòng lẻ đầu tiên trong
chương ấy là 309, mở đầu một lời thề sáu dòng đóng đúng ở 319; lỗi thật nằm ở 339, một câu
thoại mất dấu mở.

CẢNH BÁO: `stop_book_on_source_change: true`. Sửa nguồn khi đang có lượt chạy sẽ làm nó dừng.
Chỉ chạy `--apply` khi máy rảnh.
"""
import sys, pathlib, shutil, re

SRC = pathlib.Path(r'D:\Novels\Tools\Text')
SCRATCH = pathlib.Path(r'C:\Users\NGDtuanh\AppData\Local\Temp\claude'
                       r'\D--Novels-Ebook-Reader\eba3e3d6-08dd-4ad9-8ba0-dc9003c54c4a'
                       r'\scratchpad\quotefix_test')

# (file, dong 1-based, kieu, moc)
#   'prefix'  -> them " o dau dong
#   'suffix'  -> them " o cuoi dong
#   'after'   -> chen " ngay sau chuoi moc (lan xuat hien dau tien)
FIXES = [
    ('019.txt', 339, 'prefix', None),
    ('216.txt', 261, 'suffix', None),
    ('287.txt', 291, 'after', 'Sự Tồn Tại,'),
    ('375.txt',  35, 'after', 'Có lẽ á?'),
    ('397.txt', 173, 'suffix', None),
    ('405.txt', 109, 'suffix', None),
    ('430.txt', 171, 'suffix', None),
    ('452.txt', 129, 'suffix', None),
]


def patch_line(line: str, kind: str, anchor: str | None) -> str:
    stripped = line.rstrip('\n\r')
    nl = line[len(stripped):]
    if kind == 'prefix':
        return '"' + stripped + nl
    if kind == 'suffix':
        return stripped + '"' + nl
    if kind == 'after':
        idx = stripped.find(anchor)
        if idx < 0:
            raise SystemExit(f'khong tim thay moc {anchor!r}')
        cut = idx + len(anchor)
        rest = stripped[cut:]
        # chuoi bi mat dau ngoac thuong de lai hai dau cach - go bot mot cai
        if rest.startswith('  '):
            rest = rest[1:]
        return stripped[:cut] + '"' + rest + nl
    raise SystemExit(f'kieu la: {kind}')


def run(target: pathlib.Path) -> None:
    for name, lineno, kind, anchor in FIXES:
        path = target / name
        lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
        before = lines[lineno - 1]
        lines[lineno - 1] = patch_line(before, kind, anchor)
        path.write_text(''.join(lines), encoding='utf-8')
        print(f'  {name} dong {lineno}: {before.strip()[:60]}...')
        print(f'      -> {lines[lineno - 1].strip()[:60]}...')


apply = '--apply' in sys.argv
if apply:
    print('GHI THAT vao', SRC)
    run(SRC)
    target = SRC
else:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    for f in SRC.glob('*.txt'):
        shutil.copy2(f, SCRATCH / f.name)
    print('THU NGHIEM tren ban sao', SCRATCH)
    run(SCRATCH)
    target = SCRATCH

sys.path.insert(0, r'D:\Novels\Ebook Reader\_internal')
from ebook_reader.text_processing import segment_chapter_text

files = sorted(target.glob('*.txt'))
bad, segs = [], 0
for i, f in enumerate(files, start=1):
    try:
        segs += len(segment_chapter_text(i, f.read_text(encoding='utf-8')))
    except Exception as exc:
        bad.append((f.name, str(exc)[:90]))
print()
print(f'{len(files)} chuong: {len(files) - len(bad)} chia duoc, {len(bad)} chan, {segs:,} segment')
for n, m in bad:
    print(f'   {n}: {m}')
