"""卡牌模板库：用游戏自带的 block 图精确识别牌面图案。

为什么必须做这件事
------------------
之前靠「逐帧聚类」判断两张牌是否同图案，问题有二：
1. 编号无跨帧含义，槽位记账会失真；
2. 被上层压住的暗卡只露一部分，聚类极不稳定（实测同类 NCC 只有 0.79）。
而游戏把每张牌的美术资源放在公开 CDN 上（theme{N}/block_{M}.png），
拿到真图做模板，识别就从「猜」变成「查表」，暗卡也能对上。
"""
from __future__ import annotations

import glob
import os

import cv2
import numpy as np

SIZE = 32


def _load_one(path: str) -> tuple[str, np.ndarray, np.ndarray] | None:
    """读入一张模板，返回 (名称, 32x32灰度, 32x32 alpha)。"""
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.ndim == 3 and im.shape[2] == 4:
        bgr = im[:, :, :3].astype(np.float32)
        a = im[:, :, 3].astype(np.float32) / 255.0
    else:
        bgr = im.astype(np.float32)
        a = np.ones(im.shape[:2], np.float32)
    # 裁掉全透明边，让图标占满画面，便于与卡面图标区对齐
    ys, xs = np.where(a > 0.15)
    if len(ys) > 20:
        y1, y2 = ys.min(), ys.max() + 1
        x1, x2 = xs.min(), xs.max() + 1
        bgr, a = bgr[y1:y2, x1:x2], a[y1:y2, x1:x2]
    small_a = cv2.resize(a, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    # 底色先填中性值，匹配时再按卡面亮度整体平移，故用 128 作中性
    rgb = np.dstack([bgr, a * 255]).astype(np.float32)
    small = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(small[:, :, :3].astype(np.uint8), cv2.COLOR_BGR2GRAY)
    return os.path.splitext(os.path.basename(path))[0], g.astype(np.float32), small[:, :, 3] / 255.0


class TemplateLibrary:
    """全部主题的卡牌模板集合，支持一次比对取最优。"""

    def __init__(self, folder: str | None = None):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        folder = folder or os.path.join(here, "assets", "blocks")
        files = sorted(glob.glob(os.path.join(folder, "*.png")))
        names, gs, ms = [], [], []
        for f in files:
            r = _load_one(f)
            if r is None:
                continue
            n, g, m = r
            names.append(n)
            gs.append(g.ravel())
            ms.append(m.ravel())
        self.names = names
        self.G = np.asarray(gs, np.float32) if gs else np.zeros((0, SIZE * SIZE), np.float32)
        self.M = np.asarray(ms, np.float32) if ms else np.zeros_like(self.G)
        # 预中心化：模板像素减去自身均值（仅在不透明区上计算）
        cnt = np.maximum(self.M.sum(1, keepdims=True), 1e-3)
        mean = (self.G * self.M).sum(1, keepdims=True) / cnt
        self.Gc = (self.G - mean) * self.M
        self.norm = np.sqrt((self.Gc ** 2).sum(1, keepdims=True)) + 1e-6
        self.Gn = self.Gc / self.norm              # 单位向量，比对时直接点积
        self.ready = len(names) > 0

    # ---------- 卡面取样 ----------
    @staticmethod
    def card_patch(img: np.ndarray, card, inset: float = 0.10) -> np.ndarray | None:
        """取卡面内部区域并归一化为 SIZE×SIZE 灰度。"""
        ix, iy = int(card.w * inset), int(card.h * inset)
        sub = img[card.y + iy:card.y + card.h - iy, card.x + ix:card.x + card.w - ix]
        if sub.size == 0:
            return None
        g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32)
        return g.ravel()

    def match(self, g: np.ndarray, topk: int = 5) -> list[tuple[str, float]]:
        """对一个卡面灰度向量，返回最可能的模板名与相似度。"""
        if not self.ready:
            return []
        gm = g.mean()
        gc = g - gm
        gn = np.sqrt((gc ** 2).sum()) + 1e-6
        # 用模板掩膜加权后点积（近似 masked NCC）
        score = (self.Gn @ (gc / gn)) 
        idx = np.argsort(-score)[:topk]
        return [(self.names[i], float(score[i])) for i in idx]

    def match_card(self, img: np.ndarray, card) -> tuple[str, float]:
        p = self.card_patch(img, card)
        if p is None:
            return "", 0.0
        r = self.match(p, topk=1)
        return r[0] if r else ("", 0.0)
