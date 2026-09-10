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

BATCH="${1:?dung: boundary.sh <so lo vua chay> [--recast 062 066 ...] [--dry-run]}"
shift
RECAST=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --recast)
      shift
      while [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]{3}$ ]]; do RECAST="$RECAST $1"; shift; done
      ;;
    --dry-run) DRY=1; shift ;;
    *) echo "tham so la: $1" >&2; exit 2 ;;
  esac
done
NEXT=$((BATCH + 1))
ROOT="D:/Novels/Ebook Reader/_internal"
PY="$ROOT/runtime/.venv/Scripts/python.exe"
cd "$ROOT"
mkdir -p "$ROOT/runtime"
LOG="$ROOT/runtime/boundary_$(printf '%02d' "$BATCH").log"
say() { printf '%s %s\n' "$(date '+%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"; }
py() { PYTHONIOENCODING=utf-8 "$PY" "$@"; }
TAG="$(printf 'v0.2.0-lo%02d' "$BATCH")"
NEXT_TAG="$(printf 'v0.2.0-lo%02d' "$NEXT")"
# Dong Co-Authored-By cua commit script nay tao. Doi theo phien lam viec, nen de o MOT cho
# va ghi ra log: mot dong ghi cong sai trong mot commit khong ai xem luc tao ra thi khong ai
# sua. Ghi de bang EBOOK_COAUTHOR khi phien sau dung model khac.
COAUTHOR="${EBOOK_COAUTHOR:-Claude Opus 5 <noreply@anthropic.com>}"

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
say "  duc lai giong:${RECAST:- (khong)}"
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

# ---- 1. ap hang cho + bo test
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

# ---- 3. lo va cho chuong hong
FAILED="$(py -c "
import sqlite3
c = sqlite3.connect(r'file:$BATCH_PROJECT/project.sqlite3?mode=ro', uri=True)
print(' '.join(str(t) for (t, s) in c.execute('SELECT title, status FROM chapters ORDER BY title') if s != 'completed'))")"
if [ -n "$FAILED" ]; then
  tag_here "${TAG}v"
  say "lo va cho: $FAILED"
  bash scripts/launch_repair.sh "$BATCH" >> "$LOG" 2>&1 || say "launch_repair (chuong hong) thoat khac 0 - xem $LOG; di tiep."
else
  say "khong co chuong hong."
fi

# ---- 4. duc lai giong, noi duoi
if [ -n "$RECAST" ]; then
  tag_here "${TAG}r"
  say "duc lai giong:$RECAST"
  # shellcheck disable=SC2086
  bash scripts/launch_repair.sh "$BATCH" --chapters $RECAST >> "$LOG" 2>&1 || say "launch_repair (duc lai) thoat khac 0 - xem $LOG; di tiep."
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

# ---- 6. lo ke tiep
tag_here "$NEXT_TAG"
say "khoi dong lo $NEXT (gieo tu $(py scripts/seed_chain.py "$BATCH" --seed | sed 's|.*/||'))"
bash scripts/launch_batch.sh "$NEXT" >> "$LOG" 2>&1 || { say "launch_batch $NEXT that bai - xem $LOG"; exit 1; }
say "lo $NEXT dang chay: $(py scripts/seed_chain.py "$NEXT" --batch)"

# ---- 7. ghep sach: moi chuong `completed` moi nhat len sach, ke ca chuong vua va / duc lai.
# Chi doc cac project, nen chay canh lo N+1 dang bay la vo hai.
# --apply, khong phai luot thu.  mac dinh CHI IN roi thoat 0, nen ban dau cua
# buoc nay ghi "da ghep sach" vao log ma khong chep gi - do 23:24 ngay 2026-09-10: sach van 60
# chuong trong khi da co 92. Mot dong log noi thanh cong cho mot luot thu la te hon khong log.
if py scripts/assemble_book.py --apply >> "$LOG" 2>&1; then
  say "da ghep sach vao D:/Novels/Audiobooks/_book"
else
  say "assemble_book thoat khac 0 - xem $LOG"
fi
exit 0
