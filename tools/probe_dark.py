"""验证：被遮挡的暗卡上的图标能否被提取并归类。"""
import cv2, numpy as np
import sheeptool.vision as V

img = cv2.imread('out/state_2251.png')
board = V.find_board(img)
cards = V.detect_cards(img, board)
print(f"board={board}  检出 {len(cards)} 张卡")

bright = [c for c in cards if c.bright]
dark   = [c for c in cards if not c.bright]
print(f"亮卡 {len(bright)}  暗卡 {len(dark)}")

def stat(group, tag):
    ok = sum(1 for c in group if c.icon_gray is not None)
    print(f"{tag}: {ok}/{len(group)} 提取到图标 "
          f"({100*ok/max(1,len(group)):.0f}%)")
    return ok

stat(bright, "亮卡")
stat(dark, "暗卡")

# 用亮卡建原型，看暗卡能否匹配
reg = V.TypeRegistry()
n = reg.assign(bright)
print(f"\n亮卡聚类得 {n} 类")
matched = 0
for c in dark:
    if c.icon_gray is None:
        continue
    best, bt = -1, -1
    for i, p in enumerate(reg.protos):
        v = V._ncc(c.icon_gray, p['gray'])
        if v > best:
            best, bt = v, i
    if best >= 0.70:
        matched += 1
print(f"暗卡中可匹配到已有类型(ncc>=0.70): {matched}/{len(dark)}")

# 看看暗卡亮度分布，判断是否需要单独处理
print("\n暗卡亮度与尺寸样本:")
for c in dark[:12]:
    print(f"  vmed={c.score:5.1f} rect=({c.x},{c.y},{c.w},{c.h}) icon={'Y' if c.icon_gray is not None else 'N'}")
