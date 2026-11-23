"""对每个候选掩膜跑完整检测，比较最终卡牌数与几何合理性。"""
from __future__ import annotations

import sys

import cv2
import numpy as np

sys.path.insert(0, r"E:/Ai project file/WXweb")
from sheeptool import vision  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else "out/live_now.png"
img = cv2.imread(src, cv2.IMREAD_COLOR)
board = vision.find_board(img)
gx, gy, gw, gh = board
ref_w = gw * 0.095
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
op = np.ones((2, 2), np.uint8)

cands = {}
cream = cv2.inRange(hsv, np.array([22, 18, 100]), np.array([36, 95, 255]))
grayish = cv2.inRange(hsv, np.array([0, 0, 95]), np.array([60, 45, 175]))
cands["cream|gray"] = cv2.morphologyEx(cv2.bitwise_or(cream, grayish), cv2.MORPH_OPEN, op)
diff = vision._bg_diff(img)
for band in (50, 60, 70, 80, 90, 100, 120, 140, 160, 180, 200):
    cands[f"bg>{band}"] = cv2.morphologyEx((diff > band).astype(np.uint8) * 255,
                                           cv2.MORPH_OPEN, op)

roi = np.zeros_like(next(iter(cands.values())))
roi[gy + int(gh * 0.12): gy + int(gh * 0.72),
    gx + int(gw * 0.03): gx + int(gw * 0.97)] = 255

print(f"board={board} ref_w={ref_w:.1f}")
print(f"{'name':12s} {'comps':>5s} {'w x h (面积) 前12':s}")
for name, m in cands.items():
    mm = cv2.bitwise_and(m, roi)
    n, _, st, _ = cv2.connectedComponentsWithStats(mm, connectivity=8)
    keep = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (ref_w * 0.35 <= w <= ref_w * 1.45):
            continue
        if not (ref_w * 0.35 <= h <= ref_w * 1.75):
            continue
        if a < ref_w * ref_w * 0.08:
            continue
        keep.append((int(x), int(y), int(w), int(h), int(a)))
    keep.sort(key=lambda t: (t[1], t[0]))
    ws = [k[2] for k in keep]
    hs = [k[3] for k in keep]
    spread = f" w中位{int(np.median(ws))} h中位{int(np.median(hs))}" if keep else ""
    print(f"{name:12s} {len(keep):5d}{spread}  " +
          " ".join(f"({x},{y}){w}x{h}" for x, y, w, h, a in keep[:12]))
