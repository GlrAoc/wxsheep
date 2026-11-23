"""解包微信小程序 .wxapkg。

格式（均大端序）：
  [0]        0xBE 魔数
  [1:5]      info1（未知用途）
  [5:9]      indexInfoLength
  [9:13]     bodyInfoLength
  [13]       0xED 结束标记
  [14:]      index 区（indexInfoLength 字节）
               uint32 fileCount
               每项: uint32 nameLen, name(nameLen), uint32 offset, uint32 size
  [14+indexInfoLength:]  body 区，文件内容按 offset 相对 body 起点取值
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


def unpack(path: Path, outdir: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data or data[0] != 0xBE:
        raise ValueError(f"{path.name}: 魔数不是 0xBE，可能不是标准 wxapkg")

    index_len = struct.unpack(">I", data[5:9])[0]
    body_len = struct.unpack(">I", data[9:13])[0]

    index_start = 14
    body_start = index_start + index_len
    if body_start + body_len > len(data):
        raise ValueError(f"{path.name}: 头部声明的长度超出文件大小")

    n = struct.unpack(">I", data[index_start:index_start + 4])[0]
    p = index_start + 4
    entries = []
    for _ in range(n):
        name_len = struct.unpack(">I", data[p:p + 4])[0]
        p += 4
        name = data[p:p + name_len].decode("utf-8", errors="replace")
        p += name_len
        off, size = struct.unpack(">II", data[p:p + 8])
        p += 8
        entries.append((name, off, size))

    written = 0
    skipped = 0
    for name, off, size in entries:
        rel = name.lstrip("/")
        target = outdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        chunk = data[body_start + off: body_start + off + size]
        if not chunk:
            skipped += 1
            continue
        target.write_bytes(chunk)
        written += 1
    return written, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="wxapkg 文件或目录")
    ap.add_argument("-o", "--out", default="unpacked", help="输出目录")
    args = ap.parse_args()

    src = Path(args.src)
    files = [src] if src.is_file() else sorted(src.glob("*.wxapkg"))
    total_w = total_s = 0
    for f in files:
        out = Path(args.out) / f.stem[2:] if f.stem.startswith("__") else Path(args.out) / f.stem
        try:
            w, s = unpack(f, out)
            print(f"{f.name:55s} -> {w:5d} 文件, 跳过 {s}")
            total_w += w
            total_s += s
        except Exception as exc:
            print(f"{f.name:55s} 失败: {exc}")
    print(f"\n合计写出 {total_w} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
