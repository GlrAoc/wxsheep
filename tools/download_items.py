"""下载全部 item/image 资源（疑似牌面图案本体）。

依据 resources 清单：paths{序号:[路径,类型]} / uuids / versions{import|native:[序号,哈希]}
URL = {bundle}/resources/native/{uuid前2位}/{文件名}.{哈希}.png
"""
import json
import os
import ssl
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HOST = "https://cat-match-static.easygame2021.com/catMatch/sheep_wx/remote"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "items")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0"}
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
HEX = "0123456789abcdef"
VALS = {ord(c): i for i, c in enumerate(B64)}
lock = threading.Lock()
saved = [0]


def get(url, timeout=12):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                    timeout=timeout, context=CTX) as r:
            return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", 0), b""


def decode_uuid(u):
    if len(u) != 22:
        return u.replace("-", "")
    out = [u[:2]]
    for i in range(2, 22, 2):
        lhs, rhs = VALS[ord(u[i])], VALS[ord(u[i + 1])]
        out.append(HEX[lhs >> 2])
        out.append(HEX[((lhs & 3) << 2) | (rhs >> 4)])
        out.append(HEX[rhs & 0xF])
    return "".join(out)


def dashed(u):
    return f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"


def hash_map(cfg, key):
    arr = cfg.get("versions", {}).get(key) or []
    out = {}
    for i in range(0, len(arr) - 1, 2):
        try:
            idx = int(arr[i])
        except (TypeError, ValueError):
            continue
        if isinstance(arr[i + 1], str):
            out[idx] = arr[i + 1]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    st, body = get(HOST + "/resources/config.f057c.json")
    cfg = json.loads(body)
    paths, uuids = cfg["paths"], cfg["uuids"]
    nat, imp = hash_map(cfg, "native"), hash_map(cfg, "import")

    jobs = []
    for k, v in paths.items():
        name = v[0] if isinstance(v, list) and v else ""
        if not name.startswith("item/image/") and not name.startswith("item/image-big/"):
            continue
        i = int(k)
        if i >= len(uuids):
            continue
        jobs.append((name, i, decode_uuid(uuids[i])))
    print(f"待下载 {len(jobs)} 个 item 图")

    def one(job):
        name, i, uid = job
        fn = os.path.join(OUT, name.replace("/", "_") + ".png")
        if os.path.exists(fn) and os.path.getsize(fn) > 500:
            return True
        for table, sub, ext in ((nat, "native", "png"),):
            h = table.get(i)
            if not h:
                continue
            for fname in (dashed(uid), uid[:9]):
                st_, b_ = get(f"{HOST}/resources/{sub}/{uid[:2]}/{fname}.{h}.{ext}")
                if st_ == 200 and len(b_) > 500:
                    with lock:
                        open(fn, "wb").write(b_)
                        saved[0] += 1
                    return True
        return False

    ok = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(one, jobs):
            ok += 1 if r else 0
    print(f"成功 {ok} / {len(jobs)}，本次新存 {saved[0]}")


if __name__ == "__main__":
    main()
