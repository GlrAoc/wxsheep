"""按资源清单精确拼出 URL，尝试下载 item/image/* 的图标原图。

清单结构：paths{序号:[路径,类型]} / uuids[序号→压缩uuid] / versions{import|native:[序号,哈希,...]}
URL 形如 {bundle}/{import|native}/{uuid前2位}/{文件名}.{哈希}.{json|png}
"""
import json
import ssl
import sys
import urllib.request

HOST = "https://cat-match-static.easygame2021.com"
BUNDLE = HOST + "/catMatch/sheep_wx/remote"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
HEX = "0123456789abcdef"
VALS = {ord(c): i for i, c in enumerate(B64)}


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


def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", 0), b""


def load_manifest():
    st, body = get(BUNDLE + "/resources/config.f057c.json")
    if st != 200:
        sys.exit(f"清单获取失败 {st}")
    return json.loads(body)


def hash_map(cfg, key):
    """versions[key] 是 [序号,哈希,序号,哈希,...] 的扁平数组。"""
    arr = cfg.get("versions", {}).get(key) or []
    out = {}
    for i in range(0, len(arr) - 1, 2):
        try:
            idx = int(arr[i])
        except (TypeError, ValueError):
            continue                      # 该位置是 pack 名等非序号，跳过
        val = arr[i + 1]
        if isinstance(val, str):
            out[idx] = val
    return out


def main():
    cfg = load_manifest()
    paths, uuids = cfg["paths"], cfg["uuids"]
    imp, nat = hash_map(cfg, "import"), hash_map(cfg, "native")

    targets = [(k, v[0]) for k, v in paths.items() if v[0].startswith("item/image/")]
    print(f"item/image/* 共 {len(targets)} 个；native哈希 {len(nat)}，import哈希 {len(imp)}\n")

    ok = 0
    for k, name in targets[:8]:
        i = int(k)
        if i >= len(uuids):
            continue
        uid = decode_uuid(uuids[i])
        tried = []
        # png 走 native，json 走 import；文件名可能是 32 位全 uuid 或前 9 位短名
        for table, sub, ext in ((nat, "native", "png"), (imp, "import", "json")):
            h = table.get(i)
            if not h:
                continue
            for fname in (uid, uid[:9], f"{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}"):
                url = f"{BUNDLE}/resources/{sub}/{uid[:2]}/{fname}.{h}.{ext}"
                st, body = get(url, timeout=10)
                tried.append((st, len(body), url))
                if st == 200:
                    print(f"[OK] {name:22s} {sub:6s} {len(body):7d}B  {url.replace(BUNDLE,'')}")
                    if body[:4] == b"\x89PNG":
                        out = f"out/assets/{name.replace('/','_')}.png"
                        import os
                        os.makedirs("out/assets", exist_ok=True)
                        open(out, "wb").write(body)
                        print(f"     → 已保存 {out}")
                    ok += 1
                    break
        if not any(t[0] == 200 for t in tried):
            print(f"[--] {name:22s} 全部失败，最后一次 {tried[-1][0] if tried else 'n/a'}")
    print(f"\n成功 {ok} / {min(8, len(targets))}")


if __name__ == "__main__":
    main()
