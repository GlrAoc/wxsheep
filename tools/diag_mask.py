"""诊断 _face_mask：逐个候选判据打印连通域统计，找出为何 0 张。"""
from __future__ import annotations

import sys

import cv2
import numpy as np

sys.path.insert(0, r"E:/Ai project file/WXweb")

from sheeptool import vision  # noqa: E402

img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else "out/live_now.png", cv2.IMREAD_COLOR)
board = vision.find_board(img)
gx, gy, gw, gh = board
ref_w = gw * 0.095
print(f"board={board} ref_w={ref_w:.1f} 卡宽预期 {ref_w*0.35:.0f}~{ref_w*1.45:.0f}px")

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
op = np.ones((2, 2), np.uint8)
cream = cv2.inRange(hsv, np.array([22, 18, 100]), np.array([36, 95, 255]))
grayish = cv2.inRange(hsv, np.array([0, 0, 95]), np.array([60, 45, 175]))
cands = [("cream|gray", cv2.morphologyEx(cv2.bitwise_or(cream, grayish), cv2.MORPH_OPEN, op))]
diff = vision._bg_diff(img)
for band in (60, 80, 100, 120, 140, 160, 180, 200):
    m = (diff > band).astype(np.uint8) * 255
    cands.append((f"bgdiff>{band}", cv2.morphologyEx(m, cv2.MORPH_OPEN, op)))

for name, m in cands:
    n, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    good = huge = mid = 0
    sizes = []
    for i in range(1, n):
        w, h, a = st[i][2], st[i][3], st[i][4]
        sizes.append((w, h, a))
        if a >= ref_w * ref_w * 2.6:
            huge += 1
        elif (ref_w * 0.35 <= w <= ref_w * 1.5
              and ref_w * 0.35 <= h <= ref_w * 1.75
              and a >= ref_w * ref_w * 0.08):
            good += 1
        else:
            mid += 1
    score = good - 12 * huge
    sizes.sort(key=lambda t: -t[2])
    top = " ".join(f"{w}x{h}a{a}" for w, h, a in sizes[:6])
    print(f"{name:14s} n={n-1:3d} good={good:2d} huge={huge:2d} other={mid:2d} "
          f"score={score:5d} | {top}")

# 实际选中
sel = vision._face_mask(img, ref_w)
selname = next((nm for nm, m in cands if np.array_equal(m, sel)), "???")
print(f"\n实际选用 = {selname}")

# 保存所有候选图
for nm, m in cands:
    cv2.imwrite(f"out/mask_{nm.replace('|', '_').replace('>', 'gt')}.png", m)
print("候选掩膜已保存到 out/mask_*.png")
