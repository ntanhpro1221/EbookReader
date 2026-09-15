#!/usr/bin/env bash
# Ranh gioi lo N -> N+1, tu chay, khong can ai ngoi canh.
#
#     bash scripts/boundary.sh 3 --recast 062 066 071 084 086
#     bash scripts/boundary.sh 3 --dry-run            # chi in ke hoach va kiem dau vao
#
# Thu tu:
#   0. doi lo N xong; tien trinh chet giua chung thi `run` lai, toi da hai lan
#   1. ap moi ban va trong hang cho + bo test day du (apply_all --apply tu rut hang cho)
#   2. commit, tag
#   3. lo va cho chuong hong (loNNv)          - launch_repair.sh N
#   4. duc lai giong cac chuong --recast (loNNr) - launch_repair.sh N --chapters ..., noi duoi
#   5. do lai va cham cung chuong tren cac project duc lai: 0 la bang chung cua
#      patch_wrap_prefers_a_stranger; khac 0 thi ghi ra va DI TIEP - va cham la loi chat luong
#      sua duoc bang mot lo duc lai nua, khong dang de GPU ngoi khong toi luc co nguoi nhin
#   6. khoi dong lo N+1, tag
#
# Buoc 0, 1, 2, 6 that bai la dung ca chuoi (ma thoat khac 0). Moi thu ghi vao
# runtime/boundary_NN.log; nhip 30 phut se doc no.
#
# Vi sao co file nay: ca hai lan chu sach hoi "sao lai dung?" deu roi vao khoang giua hai lo -
# lo xong luc nam gio sang va cai may ngoi khong toi khi toi thuc. Mot ranh gioi la nam lenh, va
# nam lenh khong can nguoi. Cai can nguoi la DOC ket qua, va viec ay lam sau cung duoc.
set -uo pipefail

BATCH="${1:?dung: boundary.sh <so lo> [--recast auto|062|3:084 ...] [--dry-run]}"
shift
# `--recast` nhan ba dang, va ca ba deu can:
#   062     chuong cua chinh lo nay
#   3:084   chuong cua lo KHAC - chuong 084 duc lai o ranh gioi lo 3 nhung THAT BAI, nen sach
#           dang phat ban cu cua lo 3; cua so duy nhat de chay lai no la mot ranh gioi, va
#           ranh gioi ke tiep thuoc lo 4.
#   auto    lay danh sach tu `voice_pool_pressure` cua chinh lo vua xong - danh sach ay chi
#           biet duoc SAU khi lo chay xong, nen no khong the go tay luc tha script.
#   4:097!  dau `!` = EP duc lai du da co project hoan thanh. Can vi "da hoan thanh" khong co
#           nghia "da dung": 097 va 104 hoan thanh SAU khi ba ban va ap nhung TRUOC ban va gach
#           duoi, nen ca hai mang NGƯỜI TRẢ LỜI hai giong (11 va 10 cau). Khong co `!` thi buoc
#           bo-qua-viec-da-xong, vien ra de chay lai duoc, lai giu dung cai loi can sua.
# `--skip 106`: khong dung toi chuong ay trong lan nay - 106 hong vi chu so + tieng Anh chua co
#           cach doc, chua co ban va, va moi lan chay lai ranh gioi la mot lan vá lai vo ich.
RECAST=""
RECAST_OTHER=""
RECAST_AUTO=0
FORCE=""
SKIP=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --recast)
      shift
      while [ $# -gt 0 ]; do
        case "$1" in
          auto) RECAST_AUTO=1; shift ;;
          [0-9][0-9][0-9]) RECAST="$RECAST $1"; shift ;;
          [0-9][0-9][0-9]!) RECAST="$RECAST ${1%!}"; FORCE="$FORCE ${1%!}"; shift ;;
          # `B:NNN` ma B la chinh lo nay thi la mot muc cua buoc 4, khong phai 4b - neu de o 4b, `auto`
          # cung tim ra chuong ay va no bi duc lai HAI lan.
          [0-9]*:[0-9][0-9][0-9]) if [ "${1%%:*}" = "$BATCH" ]; then RECAST="$RECAST ${1#*:}"; else RECAST_OTHER="$RECAST_OTHER $1"; fi; shift ;;
          [0-9]*:[0-9][0-9][0-9]!) X="${1%!}"; FORCE="$FORCE ${X#*:}"; if [ "${X%%:*}" = "$BATCH" ]; then RECAST="$RECAST ${X#*:}"; else RECAST_OTHER="$RECAST_OTHER $X"; fi; shift ;;
          *) break ;;
        esac
      done
      ;;
    --skip)
      shift
      while [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]{3}$ ]]; do SKIP="$SKIP $1"; shift; done
      ;;
    --dry-run) DRY=1; shift ;;
    *) echo "tham so la: $1" >&2; exit 2 ;;
  esac
done
NEXT=$((BATCH + 1))
ROOT="D:/Novels/Ebook Reader/_internal"
PY="$ROOT/runtime/.venv/Scripts/python.exe"
cd "$ROOT"
# Goc CUON SACH dang san xuat - cung mot cau tra loi voi scripts/book_paths.py (xem docstring o do).
AUDIOBOOKS_ROOT="${EBOOK_AUDIOBOOKS_ROOT:-D:/Novels/Audiobooks/book2}"
VERSIONS="$AUDIOBOOKS_ROOT/_versions"
TAG_PREFIX="${EBOOK_TAG_PREFIX:-v0.3.0}"
SOURCE_DIR="${EBOOK_SOURCE_DIR:-D:/Novels/Ebook Reader/Text_Tmp}"
PLAN="${EBOOK_PLAN:-$ROOT/docs/PRODUCTION_PLAN_book2.md}"
mkdir -p "$ROOT/runtime"
LOG="$ROOT/runtime/boundary_$(printf '%02d' "$BATCH").log"
say() { printf '%s %s\n' "$(date '+%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"; }
py() { PYTHONIOENCODING=utf-8 "$PY" "$@"; }
TAG="$(printf '%s-lo%02d' "$TAG_PREFIX" "$BATCH")"
NEXT_TAG="$(printf '%s-lo%02d' "$TAG_PREFIX" "$NEXT")"
# Dong Co-Authored-By cua commit script nay tao. Doi theo phien lam viec, nen de o MOT cho
# va ghi ra log: mot dong ghi cong sai trong mot commit khong ai xem luc tao ra thi khong ai
# sua. Ghi de bang EBOOK_COAUTHOR khi phien sau dung model khac.
COAUTHOR="${EBOOK_COAUTHOR:-Claude Fable 5.1 <noreply@anthropic.com>}"

BATCH_PROJECT="$(py scripts/seed_chain.py "$BATCH" --batch)" || { say "khong thay project lo $BATCH"; exit 2; }

# In "<so chuong chua xong>|alive/dead" cua project lo. Rong neu khong doc duoc.
state() {
  py -c "
import sqlite3, time
c = sqlite3.connect(r'file:$BATCH_PROJECT/project.sqlite3?mode=ro', uri=True)
unfinished = {'pending', 'analyzing', 'synthesizing', 'verifying'}
left = sum(1 for (s,) in c.execute('SELECT status FROM chapters') if s in unfinished)
hb = [time.time() - float(r[0] or 0) for r in c.execute('SELECT heartbeat_at FROM worker_leases')]
print(f\"{left}|{'alive' if (hb and min(hb) < 180) else 'dead'}\")
" 2>/dev/null
}
chapter_statuses() {
  py -c "
import sqlite3, collections
c = sqlite3.connect(r'file:$BATCH_PROJECT/project.sqlite3?mode=ro', uri=True)
print(dict(collections.Counter(r[0] for r in c.execute('SELECT status FROM chapters'))))" 2>/dev/null
}
pending_patches() {
  py -c 'import sys; sys.path.insert(0, "scripts/pending_patches"); import apply_all; print(" ".join(apply_all.ORDER))' 2>/dev/null
}
# Chay lai duoc. Ranh gioi lo 4 chet luc 08:45 ngay 2026-09-11 vi tien trinh Claude Code thoat
# va keo ca cay tien trinh con theo (khac TaskStop, vong ay giet ca script). Chay lai script cu
# thi buoc 3 lam lai 097/106, buoc 4 duc lai 104 lan nua, 4b tao project 007 thu hai canh cai
# dang chay do. Nen moi buoc hoi truoc: "chuong nay da co mot project HOAN THANH trong thu muc
# dich chua?" - co thi bo qua, hong thi chay lai (084 hong o lo03r la dung cai can chay lai),
# va truoc khi tao gi thi doi cho khong con `run` nao dang bay.
forced() { case " $FORCE " in *" $1 "*) return 0 ;; esac; return 1; }
skipped() { case " $SKIP " in *" $1 "*) return 0 ;; esac; return 1; }
# `$3` = "force-aware": chi buoc duc lai (4/4b) truyen no; buoc 3 khong - mot chuong da co ban
# hoan thanh thi khong bao gio can VA lai, du co `!` (do 2026-09-11: 097 bi va lai roi duc lai).
already_done() {  # $1 = thu muc phien ban (vd .../v0.2.0-lo03r), $2 = so chuong, $3 = "recast" neu la buoc duc lai
  if [ "${3:-}" = "recast" ] && forced "$2"; then return 1; fi
  py -c "
import sqlite3, sys
from pathlib import Path
for p in Path(r'$1').glob('*/project.sqlite3'):
    try:
        c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        if any(str(t) == '$2' and s == 'completed' for t, s in c.execute('SELECT title, status FROM chapters')):
            sys.exit(0)
    except sqlite3.Error:
        pass
sys.exit(1)
" 2>/dev/null
}
wait_gpu_free() {
  while :; do
    LIVE="$(py -c '
import sys; sys.path.insert(0, "scripts/pending_patches"); import apply_all
print(" ".join(p.name for p, _why in apply_all._runs_in_flight()))' 2>/dev/null)"
    [ -z "$LIVE" ] && return 0
    say "  doi GPU: dang bay $LIVE"
    sleep 60
  done
}
tag_here() {
  if git tag -l "$1" | grep -q .; then
    say "tag $1 da co o $(git rev-parse --short "$1")"
  else
    git tag "$1" && say "tag $1 -> $(git rev-parse --short HEAD)"
  fi
}

say "=== ranh gioi lo $BATCH -> $NEXT ==="
say "  project lo:    $BATCH_PROJECT"
say "  trang thai:    $(state)  $(chapter_statuses)"
say "  duc lai giong:${RECAST:- (khong)}${RECAST_AUTO:+  + tu tim (auto)}"
say "  duc lai lo khac:${RECAST_OTHER:- (khong)}"
say "  ep duc lai:    ${FORCE:- (khong)}   bo qua:${SKIP:- (khong)}"
say "  hang cho:      ${PENDING:=$(pending_patches)}"
say "  tag da co:     $(git tag -l "$TAG*" "$NEXT_TAG" | tr '\n' ' ')"
say "  gieo lo $NEXT tu: $(py scripts/seed_chain.py "$BATCH" --seed)   (hien tai; se la project cuoi cua buoc 4)"
say "  chuoi cong don: $(py scripts/seed_chain.py "$BATCH" --chain | tr ' ' '\n' | sed 's|.*/||' | tr '\n' ' ')"
say "  ghi cong:      $COAUTHOR"
if [ "$DRY" = 1 ]; then
  say "dry-run: khong lam gi."
  exit 0
fi

# ---- 0. doi lo xong; chet giua chung thi chay lai, toi da hai lan
RESTARTS=0
while :; do
  s="$(state)"
  if [ -z "$s" ]; then say "khong doc duoc trang thai lo - doi 60s"; sleep 60; continue; fi
  left="${s%%|*}"; alive="${s##*|}"
  if [ "$left" = "0" ] && [ "$alive" = "dead" ]; then break; fi
  if [ "$alive" = "dead" ]; then
    if [ "$RESTARTS" -ge 2 ]; then
      say "lo $BATCH chet lan thu ba, con $left chuong chua xong. Dung ca chuoi - can nguoi nhin."
      exit 4
    fi
    RESTARTS=$((RESTARTS + 1))
    say "lo $BATCH khong con nhip tim ma con $left chuong - run lai (lan $RESTARTS)"
    # Dong bo chuoi noi TRUOC khi run lai, khong chi o buoc 2b. Mot trong nhung ly do mot lo chet
    # giua chung LA lech chuoi noi (lo 1 cuon 2, 10:26 ngay 14-09, chet o 25/49), va khi ay `run
    # lai` khong sua duoc gi: no chet lai dung doan ay, ba lan, roi ranh gioi bo tay va doi nguoi
    # nhin. Dat lai doan lech thi lan run thu hai co viec de lam. Runtime da chet nen khong ai
    # tranh khoa DB; khong lech thi khong ghi gi. That bai thi cu run lai nhu truoc - khong dung
    # ca chuoi vi mot phep don dep.
    py scripts/resync_spoken_text.py "$BATCH_PROJECT" --apply >> "$LOG" 2>&1 \
      || say "  resync truoc khi run lai that bai - xem $LOG; van run lai."
    py -m ebook_reader.cli run "$BATCH_PROJECT" --json >> "$LOG" 2>&1
    sleep 300
    continue
  fi
  sleep 60
done
say "lo $BATCH xong: $(chapter_statuses)"
# Bang chung cua lo, ghi truoc khi dong vao gi: ban va nao ban, chuong nao hong vi sao, ai
# trung giong. Day la nhung cau nhip 30 phut se hoi, va tra loi san thi no doc thay vi chay.
{
  echo "--- machine_acceptances ---";  py scripts/machine_acceptances.py "$BATCH_PROJECT"
  echo "--- plan_repair_batch ---";    py scripts/plan_repair_batch.py "$BATCH_PROJECT"
  echo "--- voice_pool_pressure ---";  py scripts/voice_pool_pressure.py "$BATCH_PROJECT"
  echo "--- throttle_report ---";      py scripts/throttle_report.py "$BATCH_PROJECT"
} >> "$LOG" 2>&1

# `auto`: chuong nao co HAI nguoi mot giong TRONG CUNG MOT CHUONG. Doc tu chinh bao cao da ghi
# o tren, nen khong co khoang cach giua cai duoc in va cai duoc chay. Khong tim thay gi thi noi
# ra va di tiep - im lang o day se doc thanh "khong co va cham nao".
if [ "$RECAST_AUTO" = 1 ]; then
  FOUND="$(py scripts/voice_pool_pressure.py "$BATCH_PROJECT" 2>/dev/null \
    | grep -oE 'CÙNG CHƯƠNG [0-9, ]+' | grep -oE '[0-9]{3}' | sort -u | tr '\n' ' ')"
  if [ -n "$FOUND" ]; then
    say "auto: chuong co hai nguoi mot giong cung chuong:$FOUND"
    RECAST="$RECAST $FOUND"
  else
    say "auto: khong thay va cham cung chuong nao - khong duc lai gi."
  fi
fi
# Bo trung lap, giu thu tu tang dan.
RECAST="$(printf '%s\n' $RECAST | sort -u | tr '\n' ' ')"

# ---- 1. ap hang cho + bo test. Doi GPU ranh TRUOC: apply_all tu choi khi con luot chay (dung),
# va mot ranh gioi chay lai sau khi chet co the gap mot project duc lai con dang bay.
wait_gpu_free
PENDING="$(pending_patches)"
if [ -n "$PENDING" ]; then
  say "ap: $PENDING"
  py scripts/pending_patches/apply_all.py --apply >> "$LOG" 2>&1 || {
    say "apply_all that bai - xem $LOG. Dung ca chuoi."
    exit 1
  }
  SUITE="$(grep -oE '[0-9]+ passed[^\r]*' "$LOG" | tail -1)"
  say "bo test: ${SUITE:-(khong thay dong tong ket)}"
  # ---- 2. commit
  git add -A "$ROOT" >> "$LOG" 2>&1
  git commit -q -F - <<EOF_MSG
apply the queue at the batch $BATCH boundary: $PENDING

Applied unattended by scripts/boundary.sh once batch $BATCH finished
($(chapter_statuses)). The full suite ran inside apply_all --apply
(${SUITE:-see runtime/boundary log}) and the queue retired itself into
APPLIED before that run, so the tree that was tested is the tree in this
commit. Each patch's reasoning is in its own docstring under
scripts/pending_patches/.

Co-Authored-By: $COAUTHOR
EOF_MSG
  say "commit: $(git log --oneline -1)"
else
  say "hang cho rong - khong co gi de ap."
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  say "cay git chua sach - before_a_batch se tu choi. Dung."
  git status --short | head -8 | tee -a "$LOG"
  exit 1
fi

# ---- 2b. dong bo chuoi noi cua project lo.
# Mot ban va doi `spoken_symbols_to_words` / chuan hoa tieng / phien am lam MOI BAN THU DA CO cua nhung
# doan bi doi tro thanh ban thu cua mot van ban khac: `pipeline._spoken_text_and_anchors` bam lai chuoi tu
# ma hien tai, so voi checksum ghi kem ban thu, va nem `spoken-text checksum drifted` - khong phuc hoi
# duoc. Lo 1 cuon 2 chet dung nhu the luc 10:26 ngay 14-09 (doan cong thuc chuong 025) va ranh gioi chay
# lai cung chet lai. Dat lai dung nhung doan ay ve cho thu; cong kiem van nguyen (mot ban thu cua van ban
# khac KHONG duoc dung lai).
#
# Chay VO DIEU KIEN, khong chi khi vua ap ban va: mot ranh gioi chay lai sau khi chet co hang cho rong
# (apply_all da tu rut) ma project van con lech. Toan ky: khong lech thi khong ghi gi, ~40 giay cho 3.705
# doan. Chi project lo - mot lo da tag va ghep roi thi ban thu la bang chung da dong.
py scripts/resync_spoken_text.py "$BATCH_PROJECT" --apply >> "$LOG" 2>&1 || {
  say "resync chuoi noi that bai - xem $LOG. Dung ca chuoi."
  exit 1
}
say "dong bo chuoi noi: $(tail -1 "$LOG" | sed 's/^ *//')"

# ---- 3. lo va cho chuong hong
FAILED="$(py -c "
import sqlite3
c = sqlite3.connect(r'file:$BATCH_PROJECT/project.sqlite3?mode=ro', uri=True)
print(' '.join(str(t) for (t, s) in c.execute('SELECT title, status FROM chapters ORDER BY title') if s != 'completed'))")"
TODO=""
for CH in $FAILED; do
  if skipped "$CH"; then say "  $CH nam trong --skip - khong dung toi"; continue; fi
  if already_done "$VERSIONS/${TAG}v" "$CH"; then say "  $CH da co ban va hoan thanh - bo qua"; else TODO="$TODO $CH"; fi
done
SEED="$(py scripts/seed_chain.py "$BATCH" --seed)"
if [ -n "$TODO" ]; then
  tag_here "${TAG}v"
  say "lo va cho:$TODO"
  wait_gpu_free
  # shellcheck disable=SC2086
  bash scripts/launch_repair.sh "$BATCH" --chapters $TODO --seed-from "$SEED" --as-repair >> "$LOG" 2>&1 || say "launch_repair (chuong hong) thoat khac 0 - xem $LOG; di tiep."
  SEED="$(py scripts/seed_chain.py --newest "$VERSIONS/${TAG}v" 2>/dev/null || echo "$SEED")"
elif [ -n "$FAILED" ]; then
  say "moi chuong hong da co ban va hoan thanh."
else
  say "khong co chuong hong."
fi

# ---- 4. duc lai giong, noi duoi
TODO=""
for CH in $RECAST; do
  if skipped "$CH"; then say "  $CH nam trong --skip - khong dung toi"; continue; fi
  if already_done "$VERSIONS/${TAG}r" "$CH" recast; then say "  $CH da duc lai hoan thanh - bo qua"; else TODO="$TODO $CH"; fi
done
if [ -n "$TODO" ]; then
  tag_here "${TAG}r"
  say "duc lai giong:$TODO  (gieo tu $(basename "$SEED"))"
  wait_gpu_free
  # shellcheck disable=SC2086
  bash scripts/launch_repair.sh "$BATCH" --chapters $TODO --seed-from "$SEED" >> "$LOG" 2>&1 || say "launch_repair (duc lai) thoat khac 0 - xem $LOG; di tiep."
  SEED="$(py scripts/seed_chain.py --newest "$VERSIONS/${TAG}r" 2>/dev/null || echo "$SEED")"
fi
if [ -n "$RECAST" ]; then
  # ---- 5. bang chung: va cham cung chuong tren tung project duc lai
  for P in $(py scripts/seed_chain.py "$BATCH" --repairs); do
    case "$P" in *"/${TAG}r/"*) ;; *) continue ;; esac
    REPORT="$(py scripts/voice_pool_pressure.py "$P" 2>/dev/null)"
    HURT="$(printf '%s\n' "$REPORT" | grep -oE '^[0-9]+/[0-9]+ va ch' | cut -d/ -f1)"
    if [ -z "$HURT" ] && printf '%s' "$REPORT" | grep -q "Không có giọng nào bị hai nhân vật dùng chung"; then HURT=0; fi
    say "  $(basename "$P"): ${HURT:-?} va cham cung chuong"
    # Ma ay co xuat hien lai khong, va no di duong nao - cau dung de hoi sau mot lo va.
    py scripts/prove_a_patch.py "$BATCH_PROJECT" "$P" >> "$LOG" 2>&1
  done
fi

# ---- 4b. duc lai chuong cua lo KHAC (dang 3:084). Sau buoc 4 nen chuoi gieo cua lo nay da
# xong; moi chuong o day di qua launch_repair cua lo cua NO, va sach lay ban moi nhat.
# Gom theo lo: mot lan `launch_repair.sh` cho moi lo, khong phai mot lan cho moi chuong -
# moi lan goi keo theo before_a_batch, plan_repair_batch va backfill.
#
# `--seed-from` tro toi project MOI NHAT cua chuoi lo nay: mot chuong cu doc lai de sua giong
# phai mang cach cast moi nhat, khong phai cach cast cua lo no thuoc ve. Gieo chuong 007 tu lo 1
# la lay lai dung bo pin da sinh ra loi.
if [ -n "$RECAST_OTHER" ]; then
  for OTHER_BATCH in $(printf '%s\n' $RECAST_OTHER | cut -d: -f1 | sort -un); do
    OTHER_TAG="$(printf '%s-lo%02d' "$TAG_PREFIX" "$OTHER_BATCH")"
    CHS=""
    for CH in $(printf '%s\n' $RECAST_OTHER | grep "^${OTHER_BATCH}:" | cut -d: -f2 | sort -u); do
      if skipped "$CH"; then say "  lo $OTHER_BATCH chuong $CH nam trong --skip - khong dung toi"; continue; fi
      if already_done "$VERSIONS/${OTHER_TAG}r" "$CH" recast; then say "  lo $OTHER_BATCH chuong $CH da duc lai hoan thanh - bo qua"; else CHS="$CHS $CH"; fi
    done
    [ -n "$CHS" ] || continue
    # SEED la project vua xong o buoc truoc (ke ca lo khac): giong vua cap di tiep, khong cap lai.
    say "duc lai lo $OTHER_BATCH chuong:$CHS  (gieo tu $(basename "$SEED"))"
    wait_gpu_free
    # shellcheck disable=SC2086
    bash scripts/launch_repair.sh "$OTHER_BATCH" --chapters $CHS --seed-from "$SEED" >> "$LOG" 2>&1 \
      || say "launch_repair lo $OTHER_BATCH thoat khac 0 - xem $LOG; di tiep."
    SEED="$(py scripts/seed_chain.py --newest "$VERSIONS/${OTHER_TAG}r" 2>/dev/null || echo "$SEED")"
  done
fi

# ---- 6. lo ke tiep
if py scripts/seed_chain.py "$NEXT" --batch >/dev/null 2>&1; then
  say "lo $NEXT da co project - khong khoi dong lai: $(py scripts/seed_chain.py "$NEXT" --batch)"
else
  tag_here "$NEXT_TAG"
  wait_gpu_free
  say "khoi dong lo $NEXT (gieo tu $(basename "$SEED") - cuoi chuoi, ke ca cac lan duc lai o buoc 4b)"
  bash scripts/launch_batch.sh "$NEXT" --seed-from "$SEED" >> "$LOG" 2>&1 || { say "launch_batch $NEXT that bai - xem $LOG"; exit 1; }
  say "lo $NEXT dang chay: $(py scripts/seed_chain.py "$NEXT" --batch)"
fi

# ---- 6b. giu cach doc ghim cho nhung doan DA LEN SACH - khong GPU, nen chay canh lo N+1 vua
# khoi dong la vo hai. Do 2026-09-11: 348/716 doan duoc sua trong sach doc ten theo chu viet vi
# ban doc-ghim thua CHI bai chinh ta neo ten. Script de cu lai ban doc-ghim (cung duong voi vong
# sua sau patch_keep_the_locked_reading) roi ghep lai chuong bang duoi cua _process_chapter
# (084 tren ban sao: 10/10 doan, 38 giay, chi ffmpeg). `--book` doc manifest.json cua lan ghep
# truoc: cac project vua va / duc lai o buoc 3-4b chay bang ma moi nen da tu giu cach doc ghim.
# Truoc khi ban va vao cay (buoc 1) script tu tu choi (thoat 2) - khong sao, di tiep.
if py scripts/keep_the_locked_reading.py --book --apply >> "$LOG" 2>&1; then
  say "da giu cach doc ghim cho cac doan da len sach (chi tiet trong $LOG)"
else
  say "keep_the_locked_reading thoat khac 0 - xem $LOG; di tiep."
fi

# ---- 7. ghep sach: moi chuong `completed` moi nhat len sach, ke ca chuong vua va / duc lai.
# Chi doc cac project, nen chay canh lo N+1 dang bay la vo hai.
# --apply, khong phai luot thu.  mac dinh CHI IN roi thoat 0, nen ban dau cua
# buoc nay ghi "da ghep sach" vao log ma khong chep gi - do 23:24 ngay 2026-09-10: sach van 60
# chuong trong khi da co 92. Mot dong log noi thanh cong cho mot luot thu la te hon khong log.
if py scripts/assemble_book.py --apply >> "$LOG" 2>&1; then
  say "da ghep sach vao $AUDIOBOOKS_ROOT/_book"
else
  say "assemble_book thoat khac 0 - xem $LOG"
fi
exit 0
