"""下载全部主题卡牌图，建立本地模板库。

URL 规则（由 cacheList.json 反推）：
  https://cat-match-static.easygame2021.com/catMatch/res/block/images/v2/theme{N}/block_{M}.png
每个主题 16 张左右，M 从 1 起，遇 404 即止。
"""
import os
import ssl
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://cat-match-static.easygame2021.com/catMatch/res/block/images/v2"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "blocks")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0"}
lock = threading.Lock()
done = 0
saved = 0


def get(url, timeout=10):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                    timeout=timeout, context=CTX) as r:
            return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", 0), b""


def one(theme):
    """下载单个主题，返回 (theme, 张数)。"""
    global done, saved
    n_ok = 0
    for m in range(1, 25):
        path = os.path.join(OUT, f"theme{theme}_block{m}.png")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            n_ok = m
            continue
        st, body = get(f"{BASE}/theme{theme}/block_{m}.png")
        if st != 200 or len(body) < 500:
            break
        with lock:
            open(path, "wb").write(body)
            saved += 1
        n_ok = m
    with lock:
        done += 1
        if done % 20 == 0:
            print(f"  进度 {done}/289 主题，已存 {saved} 张", flush=True)
    return theme, n_ok


def main():
    os.makedirs(OUT, exist_ok=True)
    themes = list(range(1, 290))
    print(f"目标：{len(themes)} 个主题，输出到 {OUT}")
    total = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for theme, n in ex.map(one, themes):
            total += n
    print(f"完成：{len(themes)} 主题，共 {total} 张牌图，本次新存 {saved} 张")


if __name__ == "__main__":
    main()
