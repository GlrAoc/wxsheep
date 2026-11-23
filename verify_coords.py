"""非破坏性坐标校验：比对「图像像素」与「屏幕实际像素」是否一致。

不产生任何点击，仅读取屏幕颜色。若两者差异很小，说明
屏幕坐标 = 窗口原点 + 图像坐标 的映射成立，自动点击才会准确。
"""
from __future__ import annotations

import cv2
import numpy as np
import mss

import sheeptool.vision as V
from sheeptool import capture as cap
from sheeptool import solver as S

cap.enable_dpi_awareness()
img, origin, hwnd = cap.grab()
board = V.find_board(img)
cards = V.detect_cards(img, board)
ntypes = V.assign_types(cards)
plan = S.plan(cards, {}, 7)

print(f"窗口原点(屏幕) = {origin}  图像尺寸 = {img.shape[1]}x{img.shape[0]}")
print(f"棋盘 = {board}  卡牌 = {len(cards)} 张  类别 = {ntypes}\n")

pts = [(cards[s.card_index].cx, cards[s.card_index].cy) for s in plan.steps]
print(f"{'序号':<4}{'图像坐标':<14}{'屏幕坐标':<14}{'图像BGR':<18}{'屏幕BGR':<18}{'Δ':<6}")
with mss.mss() as sct:
    for n, (ix, iy) in enumerate(pts, 1):
        sx, sy = origin[0] + ix, origin[1] + iy
        shot = np.array(sct.grab({"left": sx - 3, "top": sy - 3, "width": 7, "height": 7}))
        scr = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
        # 用 7x7 中位数抑制抗锯齿噪声
        s_med = np.median(scr.reshape(-1, 3), axis=0)
        i_patch = img[max(0, iy - 3):iy + 4, max(0, ix - 3):ix + 4]
        i_med = np.median(i_patch.reshape(-1, 3), axis=0)
        delta = float(np.abs(s_med - i_med).mean())
        flag = "OK" if delta < 18 else "偏差"
        print(f"{n:<4}({ix},{iy})       ({sx},{sy})       "
              f"{i_med.astype(int).tolist()!s:<18}{s_med.astype(int).tolist()!s:<18}{delta:<6.1f}{flag}")

print("\n说明: Δ<18 视为映射一致。若全部偏差，多为窗口被其它窗口遮挡或已最小化。")
