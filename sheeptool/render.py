"""渲染层：把检测结果与推荐序列画到图上（中文用 PIL 绘制）。"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .solver import Plan
from .vision import Card

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _bgr(hexcolor: str) -> tuple[int, int, int]:
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return b, g, r


GREEN = _bgr("#22C55E")
CYAN = _bgr("#22D3EE")
GREY = _bgr("#94A3B8")
AMBER = _bgr("#F59E0B")
PANEL = _bgr("#0F172A")


def render(img: np.ndarray, cards: list[Card], plan: Plan, ntypes: int,
           slot_limit: int = 7, title: str = "羊了个羊 · 决策建议") -> np.ndarray:
    vis = img.copy()
    vis = cv2.addWeighted(img, 0.62, np.zeros_like(img), 0.0, 18.0)

    order = {s.card_index: n + 1 for n, s in enumerate(plan.steps)}

    for i, c in enumerate(cards):
        if i in order:
            cv2.rectangle(vis, (c.x - 2, c.y - 2), (c.x + c.w + 2, c.y + c.h + 2), GREEN, 2)
        elif c.blocked:
            cv2.rectangle(vis, (c.x, c.y), (c.x + c.w, c.y + c.h), GREY, 1)
        elif c.ttype < 0:
            cv2.rectangle(vis, (c.x, c.y), (c.x + c.w, c.y + c.h), AMBER, 2)
        else:
            cv2.rectangle(vis, (c.x, c.y), (c.x + c.w, c.y + c.h), CYAN, 1)

    pil = Image.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
    dr = ImageDraw.Draw(pil)
    f_num = _font(19)
    f_tag = _font(13)
    f_ttl = _font(17)
    f_small = _font(14)

    for i, c in enumerate(cards):
        if i not in order:
            continue
        n = order[i]
        cx, cy = c.x + c.w - 7, c.y + 5
        r = 11
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(34, 197, 94), outline=(255, 255, 255), width=2)
        txt = str(n)
        w = dr.textlength(txt, font=f_num)
        dr.text((cx - w / 2, cy - 12), txt, font=f_num, fill=(255, 255, 255))

    # 左上信息面板
    lines = [
        title,
        f"牌面 {len(cards)} 张 · 识别 {ntypes} 类 · 槽位 {slot_limit}",
        f"建议连续执行 {len(plan.steps)} 步（绿框 + 序号）",
        "青框=可点  橙框=图标未识别  灰框=被遮挡",
    ]
    pw = int(max(dr.textlength(t, font=f_small if i else f_ttl) for i, t in enumerate(lines))) + 24
    ph = 18 * len(lines) + 34
    dr.rounded_rectangle([10, 10, 10 + pw, 10 + ph], radius=8, fill=(15, 23, 42),
                         outline=(71, 85, 105), width=1)
    for i, t in enumerate(lines):
        f = f_ttl if i == 0 else f_small
        dr.text((22, 18 + i * 18), t, font=f, fill=(226, 232, 240) if i == 0 else (148, 163, 184))

    # 底部结论条
    tail = plan.note
    tw = dr.textlength(tail, font=f_small)
    dr.rounded_rectangle([10, pil.height - 44, 10 + tw + 24, pil.height - 10],
                         radius=8, fill=(15, 23, 42), outline=(34, 197, 94), width=1)
    dr.text((22, pil.height - 38), tail, font=f_small, fill=(134, 239, 172))

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def render_step_list(plan: Plan, cards: list[Card]) -> str:
    out = []
    for n, s in enumerate(plan.steps, 1):
        c = cards[s.card_index]
        out.append(f"  {n}. 截图坐标({c.cx},{c.cy}) 类型#{s.ttype} — {s.reason}")
    return "\n".join(out)
