"""逐候选打印连通域与筛选结果，定位漏检原因。"""
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
roi = np.zeros(img.shape[:2], np.uint8)
roi[gy + int(gh * 0.12): gy + int(gh * 0.72),
    gx + int(gw * 0.03): gx + int(gw * 0.97)] = 255
print(f"board={board} ref_w={ref_w:.1f} roi y{gy+int(gh*0.12)}~{gy+int(gh*0.72)} "
      f"x{gx+int(gw*0.03)}~{gx+int(gw*0.97)}")

for name, m in vision._mask_candidates(img):
    mm = cv2.bitwise_and(m, roi)
    allc = vision._comps(mm)
    picked, sc = vision._pick_cards(mm, ref_w)
    print(f"\n[{name}] comps={len(allc)} picked={len(picked)} score={sc}")
    print("  全部: " + " ".join(f"({x},{y}){w}x{h}" for x, y, w, h, a in allc[:20]))
    print("  入选: " + " ".join(f"({x},{y}){w}x{h}" for x, y, w, h, a in picked))
    cv2.imwrite(f"out/m_{name}.png", mm)
