"""探测游戏静态资源：能否把 item/image/* 的图标原图下载下来。

用途：如果这些是卡牌图标，就能建立精确模板库，从而识别被遮挡的暗牌，
实现全信息求解。本脚本只做 GET 读取，不改动任何游戏状态。
"""
import json
import urllib.request

HOST = "https://cat-match-static.easygame2021.com"
BASE = HOST + "/catMatch/sheep_wx/remote"
CTX = None
try:
    import ssl
    CTX = ssl.create_default_context()
    CTX.check_hostname = False
    CTX.verify_mode = ssl.CERT_NONE
except Exception:
    pass

BASE64_KEYS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
HEX = "0123456789abcdef"
VALS = {ord(c): i for i, c in enumerate(BASE64_KEYS)}


def decode_uuid(u: str) -> str:
    """还原 Cocos Creator 压缩 uuid：2 位十六进制 + 20 位 base64 → 32 位 uuid。"""
    if len(u) != 22:
        return u
    out = [u[:2]]
    for i in range(2, 22, 2):
        lhs = VALS[ord(u[i])]
        rhs = VALS[ord(u[i + 1])]
        out.append(HEX[lhs >> 2])
        out.append(HEX[((lhs & 3) << 2) | (rhs >> 4)])
        out.append(HEX[rhs & 0xF])
    return "".join(out)


def dashed(u: str) -> str:
    return f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"


def fetch(url: str, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", 0), str(e).encode()[:80]


def main():
    st, body = fetch(BASE + "/resources/config.f057c.json")
    print(f"resources/config.f057c.json  HTTP={st} size={len(body)}")
    cfg = json.loads(body)
    paths = cfg.get("paths") or {}
    uuids = cfg.get("uuids") or []
    print(f"paths 条目 {len(paths)}  uuids {len(uuids)}")

    # paths 的 key 是序号字符串，指向 uuids 下标
    items = []
    for k, v in paths.items():
        name = v[0] if isinstance(v, list) and v else None
        if name and name.startswith("item/image/"):
            try:
                idx = int(k)
            except ValueError:
                continue
            if idx < len(uuids):
                items.append((name, uuids[idx]))
    print(f"item/image/* 条目 {len(items)} 个，示例：")
    for name, u in items[:6]:
        print(f"   {name:24s} uuid={u} → {dashed(decode_uuid(u))}")

    if not items:
        return

    print("\n试探下载 URL 形式：")
    name, cu = items[0]
    full = decode_uuid(cu)
    du = dashed(full)
    cands = [
        f"{BASE}/resources/native/{full[:2]}/{full[2:]}.png",
        f"{BASE}/resources/native/{full[:2]}/{du}.png",
        f"{BASE}/resources/import/{full[:2]}/{du}.json",
        f"{BASE}/resources/native/{cu[:2]}/{cu[2:]}.png",
    ]
    for url in cands:
        st, body = fetch(url)
        kind = ""
        if body[:4] == b"\x89PNG":
            kind = " PNG!"
        elif body[:1] in (b"{", b"["):
            kind = " JSON"
        print(f"  HTTP={st:3d} len={len(body):7d}{kind:6s} {url.replace(BASE, '')}")


if __name__ == "__main__":
    main()
