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
# Chay TUAN TU, vi chung tranh nhau cung mot GPU. Chuong dau gieo tu project moi nhat cua lo
# (lo, hoac lo va / duc lai truoc do), moi chuong sau gieo tu chuong VUA XONG - noi duoi. Vi sao:
# khi hai nguoi trung giong, port_casting bo ghim nguoi thua va registry cap giong moi; gieo moi
# chuong doc lap tu lo la cap lai doc lap moi lan, va cung nguoi ay co the nhan hai giong o hai
# chuong. Noi duoi thi giong cap o chuong dau di theo sang chuong sau, va lo ke tiep gieo tu
# chuong cuoi (seed_chain.py) nen di tiep nua.
set -uo pipefail

BATCH="${1:?dung: launch_repair.sh <so lo, 1..16> [--chapters 062 066 ...]}"
shift
# Che do chi dinh chuong: cho nhung chuong `completed` nhung phai DUC LAI GIONG - lo 3 co nam
# chuong hai nhan vat trung giong cung chuong (062, 066, 071, 084, 086), va luat "chi chuong
# failed" ben duoi dung cho moi truong hop khac nen khong noi no ra.
EXPLICIT=""
SEED_FROM=""
AS_REPAIR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --chapters)
      shift
      while [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]{3}$ ]]; do EXPLICIT="$EXPLICIT $1"; shift; done
      ;;
    # Gieo tu MOT project chi dinh thay vi tu project moi nhat cua lo nay.
    #
    # Vi sao can: mot chuong cu duoc doc lai de sua GIONG - vi du 21 chuong co mot nguoi hai
    # giong do lop tach danh tinh (do 2026-09-11) - phai mang cach cast MOI NHAT, khong phai
    # cach cast cua lo no thuoc ve. Chuong 007 thuoc lo 1; gieo tu lo 1 la lay lai dung bo pin
    # da sinh ra loi. Project moi nhat mang pin dut khoat cho moi nhan vat, va do la thu can.
    --seed-from) shift; SEED_FROM="${1:?--seed-from can duong dan project}"; shift ;;
    # Chi dinh chuong nhung van la LO VA (thu muc `v`, tieu de `loNNv_`): boundary.sh dung no de
    # chay lai chi nhung chuong hong CHUA co ban va hoan thanh. Khong co co nay thi `--chapters`
    # luon la duc lai giong (`r`), va hai loai project se lan ten.
    --as-repair) AS_REPAIR=1; shift ;;
    *) echo "tham so la: $1" >&2; exit 2 ;;
  esac
done
EXPLICIT="${EXPLICIT# }"
ROOT="D:/Novels/Ebook Reader/_internal"
PY="$ROOT/runtime/.venv/Scripts/python.exe"
cd "$ROOT"

TAG="$(printf 'v0.2.0-lo%02d' "$BATCH")"
[ "$BATCH" = "1" ] && TAG="v0.2.0-lo01"
# Lo va thuong la `...v`; luot duc lai giong la `...r` de hai loai project khong lan ten.
if [ -n "$EXPLICIT" ] && [ "$AS_REPAIR" != 1 ]; then OUT_TAG="${TAG}r"; else OUT_TAG="${TAG}v"; fi
OUT="D:/Novels/Audiobooks/_versions/$OUT_TAG"
# Hai project khac nhau: BATCH_PROJECT la project LO - doc danh sach chuong hong tu no; PREV la
# project GIEO - moi nhat tren ca ba thu muc lo / lo+v / lo+r theo book.created_at, khong theo
# mtime (seed_chain.py noi vi sao). Lan dau hai cai la mot.
BATCH_PROJECT="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py "$BATCH" --batch)" || {
  echo "Khong thay project cua $TAG." >&2
  exit 2
}
if [ -n "$SEED_FROM" ]; then
  [ -f "$SEED_FROM/project.sqlite3" ] || { echo "--seed-from khong phai project: $SEED_FROM" >&2; exit 2; }
  PREV="$SEED_FROM"
else
  PREV="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py "$BATCH" --seed)" || exit 2
fi

echo "=== lo va cho lo $BATCH ==="
echo "  project lo: $BATCH_PROJECT"
echo "  gieo tu:    $PREV"

# Chuong hong doc tu SQLite. Loc ra nhung chuong CHUA CHAY XONG: chay giua lo thi moi chuong
# chua toi luot deu doc thanh "can va", va mot danh sach nhu the la chay lai thua ca chuc chuong.
BROKEN="$(PYTHONIOENCODING=utf-8 "$PY" -c "
import sqlite3, sys
c = sqlite3.connect(r'file:$BATCH_PROJECT/project.sqlite3?mode=ro', uri=True)
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
if [ -n "$EXPLICIT" ]; then
  BROKEN="$EXPLICIT"
  echo "  che do chi dinh: duc lai giong cho $BROKEN"
fi
if [ -z "$BROKEN" ]; then
  echo "  Khong co chuong nao hong. Khong can lo va."
  exit 0
fi
echo "  chuong can chay lai: $BROKEN"

echo
echo "=== canh bao truoc khi chay lai ==="
PYTHONIOENCODING=utf-8 "$PY" scripts/plan_repair_batch.py "$BATCH_PROJECT" --tag "$OUT_TAG" 2>&1 \
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


# So cong don: `mention_count` bi ghi de moi lo, nen `port_casting` xep hang "ai giu giong khi
# trung" theo so cua rieng lo truoc - do 2026-09-10: SAMAEL 10 -> 99 -> 19 trong khi thuc te da
# noi 128 cau. Dung lai so tu ca chuoi lo da xong, ghi vao PREV, truoc khi gieo.
# Chuoi: project lo cua moi lo truoc, roi lo nay va cac project va / duc lai cua no theo thu tu
# tao. backfill dem moi chuong mot lan (project sau thang) nen khong cong chong.
CHAIN="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py "$BATCH" --chain)"
# `backfill_exposure` ghi so vao project CUOI chuoi, va `port_casting` doc so tu project GIEO.
# Gieo tu noi khac (--seed-from) thi hai cai ay phai la mot: noi PREV vao cuoi chuoi.
# PREV phai la phan tu CUOI: backfill ghi so vao chain[-1]. "Them neu thieu" khong du - khi PREV
# la mot project duc lai cua lo TRUOC (lo 5 gieo tu lo03r_091) thi no da nam GIUA chuoi, so ghi
# vao lo04r_104b, va port_casting doc tu lo03r_091 chi thay ban chep cu 21 ten (do 17:40
# 2026-09-11: KANG=None, NGƯỜI TRẢ LỜI=320 thay vi 955). Bo no ra roi noi lai vao cuoi.
CHAIN="$(printf '%s\n' $CHAIN | grep -vxF "$PREV" | tr '\n' ' ') $PREV"
echo
echo "=== so cong don qua chuoi lo ==="
# shellcheck disable=SC2086
PYTHONIOENCODING=utf-8 "$PY" scripts/backfill_exposure.py $CHAIN || {
  echo "backfill that bai - gieo se lui ve mention_count cua rieng lo truoc." >&2
}

for CH in $BROKEN; do
  echo
  echo "=== chuong $CH ==="
  if [ -n "$EXPLICIT" ] && [ "$AS_REPAIR" != 1 ]; then SUFFIX=r; else SUFFIX=v; fi
  TITLE="$(printf 'lo%02d%s_%s' "$BATCH" "$SUFFIX" "$CH")"
  # Ten project la noi dung-dia-chi theo (tieu de, nguon): cung chuong, cung tieu de -> cung thu
  # muc. Lan thu HAI cho mot chuong (084 hong o lo03r; 106; 007 bi dung do) vi the mo lai project
  # cu thay vi tao moi, roi `run` tu choi resume vi hash ma da doi sau ban va, va ca chuoi ghi
  # "xong" ma khong lam gi - do sang 2026-09-11, 106 va 007 "xong" trong hai phut. Them mot chu
  # cai vao tieu de cho toi khi chua co project nao mang no: lo04v_106 -> lo04v_106b -> ...c.
  ATTEMPT=""
  for LETTER in "" b c d e f g h; do
    if ls -d "$OUT"/"${TITLE}${LETTER}"_* >/dev/null 2>&1; then continue; fi
    ATTEMPT="$LETTER"; break
  done
  [ -n "$ATTEMPT" ] && echo "  chuong $CH da co project truoc - tieu de lan nay: ${TITLE}${ATTEMPT}"
  TITLE="${TITLE}${ATTEMPT}"
  PYTHONIOENCODING=utf-8 "$PY" -m ebook_reader.cli create \
    --output-root "$OUT" --source-dir "D:/Novels/Tools/Text" \
    --range "$CH..$CH" --width 3 --title "$TITLE" --profile high_quality --json > /dev/null
  # Moi nhat theo book.created_at (seed_chain.py), khong theo ten hay mtime: chay lo va lan
  # thu hai tao project thu hai cung tien to, lay cai dau theo alphabet la lay cai CU; con
  # mtime thu muc thi doi moi lan ai do mo DB.
  PROJECT="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py --newest "$OUT")" || { echo "  create that bai cho $CH"; continue; }
  echo "  project: $(basename "$PROJECT")"
  PYTHONIOENCODING=utf-8 "$PY" scripts/port_pronunciations.py       "$PREV" "$PROJECT" > /dev/null
  PYTHONIOENCODING=utf-8 "$PY" scripts/port_casting.py              "$PREV" "$PROJECT" > /dev/null
  PYTHONIOENCODING=utf-8 "$PY" scripts/seed_listener_acceptances.py "$PREV" "$PROJECT" > /dev/null
  # `run` tra JSON; `ok: false` (vi du resume bi tu choi vi hash ma doi) tung bi do vao /dev/null
  # va vong doi ben duoi thay lease chet + chuong khong "chua xong" nen coi la xong. Noi ra.
  RUN_OUT="$(PYTHONIOENCODING=utf-8 "$PY" -m ebook_reader.cli run "$PROJECT" --json 2>&1)"
  if ! printf '%s' "$RUN_OUT" | grep -q '"ok": true'; then
    echo "  run KHONG khoi dong duoc cho chuong $CH:"
    printf '%s\n' "$RUN_OUT" | grep -oE '"error": "[^"]{0,200}' | head -2
    continue
  fi
  wait_for_run "$PROJECT" "chuong $CH"
  # Noi duoi: chuong ke tiep gieo tu project vua xong, de giong vua cap di tiep.
  PREV="$PROJECT"
done

echo
echo "=== xong ca lo va ==="
echo "Doi chieu ket qua: python scripts/assemble_book.py"
