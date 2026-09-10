#!/usr/bin/env bash
# Chay lai nhung chuong mot lo lam hong, tung chuong mot.
#
#     bash scripts/launch_repair.sh 2      # lo va cho lo 2
#
# Thay cho viec go tay so chuong: `plan_repair_batch.py` in ra danh sach, con script nay doc
# **chinh SQLite cua lo** de khoi co khoang cach giua cai duoc in va cai duoc chay.
#
# Vi sao tung chuong mot chu khong phai mot dai: `--range` nhan mot dai lien tuc, va chuong hong
# thuong rai rac. Ba project mot chuong chay nhanh hon mot dai bao ca nhung chuong da tot - do
# tren lo 1: chay lai ca lo ~13 gio, chay lai bon chuong hong ~4.
#
# Chay TUAN TU, vi chung tranh nhau cung mot GPU. Gieo tu chinh project cua lo de giong va cach
# doc khong doi.
set -uo pipefail

BATCH="${1:?dung: launch_repair.sh <so lo, 1..16>}"
ROOT="D:/Novels/Ebook Reader/_internal"
PY="$ROOT/runtime/.venv/Scripts/python.exe"
cd "$ROOT"

TAG="$(printf 'v0.2.0-lo%02d' "$BATCH")"
[ "$BATCH" = "1" ] && TAG="v0.2.0-lo01"
OUT_TAG="${TAG}v"
OUT="D:/Novels/Audiobooks/_versions/$OUT_TAG"
PREV="$(ls -dt "D:/Novels/Audiobooks/_versions/$TAG"/*/ 2>/dev/null | head -1)"
if [ -z "$PREV" ]; then
  echo "Khong thay project cua $TAG." >&2
  exit 2
fi
PREV="${PREV%/}"

echo "=== lo va cho lo $BATCH ==="
echo "  gieo tu: $PREV"

# Chuong hong doc tu SQLite. Loc ra nhung chuong CHUA CHAY XONG: chay giua lo thi moi chuong
# chua toi luot deu doc thanh "can va", va mot danh sach nhu the la chay lai thua ca chuc chuong.
BROKEN="$(PYTHONIOENCODING=utf-8 "$PY" -c "
import sqlite3, sys
c = sqlite3.connect(r'file:$PREV/project.sqlite3?mode=ro', uri=True)
c.row_factory = sqlite3.Row
unfinished = {'pending', 'analyzing', 'synthesizing', 'verifying'}
rows = list(c.execute('SELECT title, status FROM chapters ORDER BY title'))
if any(str(r['status']) in unfinished for r in rows):
    print('CHUA_XONG', file=sys.stderr)
    sys.exit(3)
print(' '.join(str(r['title']) for r in rows if str(r['status']) != 'completed'))
" 2>&1)"
STATUS=$?
if [ "$STATUS" = "3" ]; then
  echo "  Lo $BATCH chua chay xong - doi no xong da." >&2
  exit 3
fi
# Chi tin `$BROKEN` khi ma thoat la 0. Vi co `2>&1` o tren, mot loi khac (SQLite hong, cot doi
# ten) se do traceback vao dung bien nay, va script se coi tung dong traceback la mot so chuong
# roi goi `create --range` voi chung. Kiem ma thoat truoc khi doc noi dung.
if [ "$STATUS" != "0" ]; then
  echo "  Khong doc duoc danh sach chuong hong (ma $STATUS):" >&2
  echo "$BROKEN" | sed -n '1,6p' >&2
  exit 2
fi
if [ -z "$BROKEN" ]; then
  echo "  Khong co chuong nao hong. Khong can lo va."
  exit 0
fi
echo "  chuong can chay lai: $BROKEN"

echo
echo "=== canh bao truoc khi chay lai ==="
PYTHONIOENCODING=utf-8 "$PY" scripts/plan_repair_batch.py "$PREV" --tag "$OUT_TAG" 2>&1 \
  | sed -n '/nguyên nhân khác nhau/,$p' | sed -n '1,24p'

echo
echo "=== kiem truoc lo ==="
PYTHONIOENCODING=utf-8 "$PY" scripts/before_a_batch.py || {
  echo "before_a_batch tu choi. Dung." >&2
  exit 1
}

wait_for_run() {
  local project="$1" label="$2" quiet=0
  while :; do
    sleep 30
    local state
    state="$(PYTHONIOENCODING=utf-8 "$PY" -c "
import sqlite3, time
c = sqlite3.connect(r'file:$project/project.sqlite3?mode=ro', uri=True)
c.row_factory = sqlite3.Row
b = c.execute('SELECT status, stage FROM book').fetchone()
hb = [time.time() - float(r[0] or 0) for r in c.execute('SELECT heartbeat_at FROM worker_leases')]
alive = bool(hb) and min(hb) < 180
print(f\"{b['status']}|{b['stage']}|{'alive' if alive else 'dead'}\")
" 2>/dev/null)"
    case "$state" in
      *"|alive") quiet=0 ;;
      "") quiet=$((quiet + 1)); [ "$quiet" -gt 4 ] && { echo "  $label: khong doc duoc trang thai"; return 1; } ;;
      *"|dead") echo "  $label xong: $state"; return 0 ;;
    esac
  done
}

for CH in $BROKEN; do
  echo
  echo "=== chuong $CH ==="
  TITLE="$(printf 'lo%02dv_%s' "$BATCH" "$CH")"
  PYTHONIOENCODING=utf-8 "$PY" -m ebook_reader.cli create \
    --output-root "$OUT" --source-dir "D:/Novels/Tools/Text" \
    --range "$CH..$CH" --width 3 --title "$TITLE" --profile high_quality --json > /dev/null
  # `-dt` chu khong phai `-d`: chay lo va lan thu hai se tao mot project thu hai cung tien to
  # ten, va lay cai dau tien theo thu tu alphabet nghia la lay cai CU - roi doi mai mot lo da
  # xong tu truoc.
  PROJECT="$(ls -dt "$OUT"/${TITLE}_* 2>/dev/null | head -1)"
  [ -n "$PROJECT" ] || { echo "  create that bai cho $CH"; continue; }
  echo "  project: $(basename "$PROJECT")"
  PYTHONIOENCODING=utf-8 "$PY" scripts/port_pronunciations.py       "$PREV" "$PROJECT" > /dev/null
  PYTHONIOENCODING=utf-8 "$PY" scripts/port_casting.py              "$PREV" "$PROJECT" > /dev/null
  PYTHONIOENCODING=utf-8 "$PY" scripts/seed_listener_acceptances.py "$PREV" "$PROJECT" > /dev/null
  PYTHONIOENCODING=utf-8 "$PY" -m ebook_reader.cli run "$PROJECT" --json > /dev/null
  wait_for_run "$PROJECT" "chuong $CH"
done

echo
echo "=== xong ca lo va ==="
echo "Doi chieu ket qua: python scripts/assemble_book.py"
