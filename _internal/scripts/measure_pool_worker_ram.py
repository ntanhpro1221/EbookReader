"""Peak resident size of each pool child, sampled while a batch is actually working.

PERCEPTUAL_WORKER_RAM_GB = 1.75 is what sizes the perceptual pool, and the pool is what
pushed alpha.47 to 1.9 GB free and into yield_heavy. A single snapshot is not enough to
call the constant wrong: children read 0.01 GB while importing and 2.2 GB once loaded, so
whether a sample means anything depends entirely on when it was taken. This tracks the
*peak* per pid over a window instead.
"""
import json, sys, time, collections
import psutil

deadline = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 900)
out = sys.argv[2]
peak = collections.defaultdict(float)
born = {}
while time.time() < deadline:
    for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'memory_info']):
        try:
            cl = ' '.join(p.info['cmdline'] or [])
            if '--multiprocessing-fork' not in cl:
                continue
            rss = p.info['memory_info'].rss / 2**30
            if rss > peak[p.info['pid']]:
                peak[p.info['pid']] = rss
            born.setdefault(p.info['pid'], p.info['create_time'])
        except Exception:
            continue
    time.sleep(3)

rows = sorted(((pid, v, born.get(pid, 0)) for pid, v in peak.items()), key=lambda r: -r[1])
loaded = [v for _, v, _ in rows if v > 1.0]      # exclude children still importing
json.dump({'children': len(rows), 'loaded': len(loaded), 'peaks': [round(v, 3) for v in loaded]},
          open(out, 'w'), indent=2)
print(f'{len(rows)} tien trinh con, {len(loaded)} da nap xong')
if loaded:
    loaded.sort()
    mid = loaded[len(loaded)//2]
    print(f'  dinh: nho nhat {min(loaded):.2f} GB, trung vi {mid:.2f} GB, lon nhat {max(loaded):.2f} GB')
    print(f'  hang so 1.75 GB -> thuc te cao hon {100*(mid-1.75)/1.75:.0f}%')
