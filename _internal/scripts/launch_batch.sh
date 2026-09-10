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

BATCH="${1:?dung: launch_batch.sh <so lo, 2..16>}"
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

# Project cua lo lien truoc: cai moi nhat trong thu muc phien ban cua no.
PREV_TAG="$(printf 'v0.2.0-lo%02d' $((BATCH - 1)))"
[ "$BATCH" = "2" ] && PREV_TAG="v0.2.0-lo01"
PREV="$(ls -dt "D:/Novels/Audiobooks/_versions/$PREV_TAG"/*/ 2>/dev/null | head -1)"
if [ -z "$PREV" ]; then
  echo "Khong thay project cua lo truoc trong $PREV_TAG - day gieo se dut. Dung." >&2
  exit 1
fi
PREV="${PREV%/}"

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

PROJECT="$(ls -d "$OUT"/${TITLE}_* 2>/dev/null | head -1)"
[ -n "$PROJECT" ] || { echo "create that bai" >&2; exit 1; }
echo "project: $PROJECT"


# So cong don: `mention_count` bi ghi de moi lo, nen `port_casting` xep hang "ai giu giong khi
# trung" theo so cua rieng lo truoc - do 2026-09-10: SAMAEL 10 -> 99 -> 19 trong khi thuc te da
# noi 128 cau. Dung lai so tu ca chuoi lo da xong, ghi vao PREV, truoc khi gieo.
CHAIN=""
for T in $(ls -d "D:/Novels/Audiobooks/_versions"/v0.2.0-lo[0-9][0-9]/ 2>/dev/null | sort); do
  T="${T%/}"
  case "$T" in *v) continue ;; esac
  P="$(ls -dt "$T"/*/ 2>/dev/null | head -1)"; P="${P%/}"
  [ -n "$P" ] || continue
  CHAIN="$CHAIN $P"
  [ "$P" = "$PREV" ] && break
done
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
