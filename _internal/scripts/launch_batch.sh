#!/usr/bin/env bash
# Khoi dong mot lo bat ky cua docs/PRODUCTION_PLAN.md.
#
#     bash launch_batch.sh 2      # lo 2, dai chuong doc TU KE HOACH
#     bash launch_batch.sh 3
#
# Thay cho launch_lo02.sh: 15 lo con lai chi khac nhau vai con so, va chep tay chung 15 lan la
# 15 co hoi go nham.
#
# **Dai chuong doc tu bang trong PRODUCTION_PLAN.md, khong tinh bang phep nhan.** Ban dau cua
# script nay lay FIRST=(n-1)*30 vi lo 1 va lo 2 deu la 30 chuong. Sai tu lo 3: ke hoach chia lo
# **theo so tu**, khong theo so chuong, nen lo 3 la 060..091 (32 chuong) va lo 4 la 092..118
# (27). Do la chinh chi thi cua chu sach - "lo phai theo so tu chu sao lai theo chuong?" - va
# mot script tu tinh lai dai chuong se lang le pha no.
#
# **Gieo tu lo lien truoc**, khong phai tu alpha nao. Do 2026-09-09: alpha.62 mang 17 nhan vat
# co ten, lo01b mang 22. Nam nhan vat ay xuat hien lan dau trong chuong 000..029; gieo tu
# alpha.62 thi lo sau se duc giong lai cho ho tu dau, va cung mot nguoi se noi bang hai giong o
# hai lo - mot loi IM LANG, khong cong nao bat duoc vi moi lo tu no deu nhat quan.
set -euo pipefail

BATCH="${1:?dung: launch_batch.sh <so lo, 2..16> [--seed-from <project>]}"
shift || true
SEED_FROM=""
while [ $# -gt 0 ]; do
  case "$1" in
    # Gieo tu project chi dinh - boundary.sh truyen project CUOI chuoi sau khi da duc lai giong
    # cac chuong cua lo khac o buoc 4b; `seed_chain.py N --seed` chi nhin thu muc cua lo N nen
    # khong thay chung.
    --seed-from) shift; SEED_FROM="${1:?--seed-from can duong dan project}"; shift ;;
    *) echo "tham so la: $1" >&2; exit 2 ;;
  esac
done
ROOT="D:/Novels/Ebook Reader/_internal"
PY="$ROOT/runtime/.venv/Scripts/python.exe"
PLAN="$ROOT/docs/PRODUCTION_PLAN.md"
cd "$ROOT"

# Dong bang co dang:  | 3 | 060..091 | 32 | 3.675 | 7,9 |
RANGE="$(grep -oE "^\| *$BATCH \| *[0-9]{3}\.\.[0-9]{3} *\|" "$PLAN" | grep -oE '[0-9]{3}\.\.[0-9]{3}' | head -1 || true)"
if [ -z "$RANGE" ]; then
  echo "Khong tim thay dai chuong cho lo $BATCH trong $PLAN." >&2
  echo "Bang lo nam o muc dau tai lieu; dung tu bia ra dai chuong." >&2
  exit 2
fi
FIRST="${RANGE%%..*}"
LAST="${RANGE##*..}"
TAG="$(printf 'v0.2.0-lo%02d' "$BATCH")"
TITLE="$(printf 'lo%02d' "$BATCH")"
OUT="D:/Novels/Audiobooks/_versions/$TAG"

# Project gieo: cai CUOI chuoi cua lo truoc - lo, roi cac project va / duc lai giong cua no theo
# thu tu tao (book.created_at, khong phai mtime). Tu lo 3 project duc lai cap giong MOI cho nguoi
# thua khi trung giong; gieo tu lo thay vi tu cai cuoi la cap lai lan nua, doc lap, va mot nguoi
# co the mang hai giong o hai lo. seed_chain.py giu mot cau tra loi cho ca ba script.
if [ -n "$SEED_FROM" ]; then
  [ -f "$SEED_FROM/project.sqlite3" ] || { echo "--seed-from khong phai project: $SEED_FROM" >&2; exit 2; }
  PREV="$SEED_FROM"
else
  PREV="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py $((BATCH - 1)) --seed)" || {
    echo "Khong thay project nao cua lo $((BATCH - 1)) - day gieo se dut. Dung." >&2
    exit 1
  }
fi

echo "=== lo $BATCH: chuong $RANGE (doc tu PRODUCTION_PLAN.md) ==="
echo "  gieo tu: $PREV"
echo

echo "=== 0. kiem truoc lo ==="
"$PY" scripts/before_a_batch.py || { echo "before_a_batch tu choi. Dung." >&2; exit 1; }

echo
echo "=== 1. create ==="
"$PY" -m ebook_reader.cli create \
  --output-root "$OUT" --source-dir "D:/Novels/Tools/Text" \
  --range "$RANGE" --width 3 --title "$TITLE" --profile high_quality --json

# Moi nhat theo book.created_at: chay lai lo se tao project thu hai cung tien to ten, va `ls -d`
# lay cai dau theo alphabet - tuc cai CU.
PROJECT="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py "$BATCH" --batch)" || { echo "create that bai" >&2; exit 1; }
echo "project: $PROJECT"


# So cong don: `mention_count` bi ghi de moi lo, nen `port_casting` xep hang "ai giu giong khi
# trung" theo so cua rieng lo truoc - do 2026-09-10: SAMAEL 10 -> 99 -> 19 trong khi thuc te da
# noi 128 cau. Dung lai so tu ca chuoi lo da xong, ghi vao PREV, truoc khi gieo.
# Chuoi: project lo cua moi lo truoc, roi lo lien truoc va cac project va / duc lai cua no theo
# thu tu tao. backfill dem moi chuong mot lan (project sau thang) nen khong cong chong.
CHAIN="$(PYTHONIOENCODING=utf-8 "$PY" scripts/seed_chain.py $((BATCH - 1)) --chain)"
# So phai nam o project GIEO (port_casting doc tu do); gieo tu noi khac thi noi no vao cuoi.
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

echo
echo "=== 2. gieo, dung thu tu ==="
"$PY" scripts/port_pronunciations.py       "$PREV" "$PROJECT"
"$PY" scripts/port_casting.py              "$PREV" "$PROJECT"
"$PY" scripts/seed_listener_acceptances.py "$PREV" "$PROJECT"

echo
echo "=== 3. run ==="
"$PY" -m ebook_reader.cli run "$PROJECT" --json
echo
echo "Da khoi dong. Theo doi bang:"
echo "  python scripts/throttle_report.py \"$PROJECT\""
echo "Khi xong: python scripts/plan_repair_batch.py \"$PROJECT\""
