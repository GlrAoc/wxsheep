#!/usr/bin/env python
"""判断一张手机截图里的牌面能不能被视觉读出来。

    python mobile/analyze_shot.py mobile/shots/shot-xxx.png

复用 sheeptool 的视觉管线（find_board / detect_cards / assign_types），
输出：
  - 图像尺寸、棋盘区域
  - 检出牌数、亮牌/暗牌数
  - 花色聚类数
  - 标注图（默认写回同目录 -anno.png）

这是"手机端视觉路线"的可行性闸门：如果暗牌（被压住的牌）也能稳定检出，
结构重建就有基础；如果暗牌大面积漏检，就只能靠闭环增量识别。
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sheeptool import vision  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    if not src.exists():
        print(f"[FAIL] 文件不存在: {src}")
        return 1

    img = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print(f"[FAIL] 无法解码图片: {src}")
        return 1

    h, w = img.shape[:2]
    print(f"图像: {w}x{h}  ({src.name})")

    cards, board, ntypes = vision.analyze(img)
    gx, gy, gw, gh = board
    print(f"棋盘区域: x={gx} y={gy} w={gw} h={gh}")
    print(f"检出牌数: {len(cards)}  亮牌: {sum(1 for c in cards if c.bright)}  "
          f"暗牌: {sum(1 for c in cards if not c.bright)}")
    print(f"花色聚类: {ntypes}  未判定类型: {sum(1 for c in cards if c.ttype < 0)}")

    if cards:
        side = sorted({c.w for c in cards})
        print(f"牌宽取值: {side[:6]}{' ...' if len(side) > 6 else ''}")
        ratio = (gw / gh) if gh else 0
        print(f"棋盘宽高比: {ratio:.2f}")

    cov = vision.coverage(cards)
    fully = sum(1 for c in cards if cov.get(id(c), 0) >= 3)
    print(f"覆盖度>=3 的牌: {fully} / {len(cards)}")

    # 标注图：亮牌绿框、暗牌灰框，便于人眼核对
    out = src.with_name(src.stem + "-anno.png")
    vis = img.copy()
    for c in cards:
        color = (0, 200, 0) if c.bright else (140, 140, 140)
        cv2.rectangle(vis, (c.x, c.y), (c.x + c.w, c.y + c.h), color, 2)
        if c.ttype >= 0:
            cv2.putText(vis, str(c.ttype), (c.x + 2, c.y + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    cv2.rectangle(vis, (gx, gy), (gx + gw, gy + gh), (0, 200, 255), 2)
    cv2.imencode(".png", vis)[1].tofile(str(out))
    print(f"标注图: {out}")

    # 结论
    print()
    if len(cards) == 0:
        print("[结论] 一张牌都没检出 —— 牌区定位失败，先确认截图里是关卡画面而不是大厅/结算页。")
        return 3
    dark = sum(1 for c in cards if not c.bright)
    if dark == 0 and len(cards) > 20:
        print("[结论] 全部被判为亮牌，说明'暗牌'没被区分出来 —— 手机端视觉方案需要重调阈值。")
        return 3
    print("[结论] 牌面可读，可以继续做结构重建 / 闭环识别。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
