"""探测微信进程是否开放了 Chromium DevTools 协议端口（只读，不改游戏状态）。"""
import json, re, socket, subprocess, urllib.request

def pids_by_name():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, errors="ignore").stdout
    rows = {}
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and re.search(r"wechat|weixin|radium|wxplayer|xweb", parts[0], re.I):
            try:
                rows.setdefault(parts[0], []).append(int(parts[1]))
            except ValueError:
                pass
    return rows

def listening_ports(pids):
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="ignore").stdout
    ports = set()
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 5 and f[3] == "LISTENING" and f[0].startswith("TCP"):
            try:
                pid = int(f[4])
            except ValueError:
                continue
            if pid in pids:
                addr = f[1]
                ports.add(int(addr.rsplit(":", 1)[1]))
    return sorted(ports)

def probe(port):
    for path in ("/json/version", "/json/list"):
        for host in ("127.0.0.1",):
            try:
                with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=0.7) as r:
                    body = r.read(4000).decode("utf-8", "replace")
                if "webSocketDebuggerUrl" in body or "Browser" in body or body.strip().startswith(("[", "{")):
                    return path, body
            except Exception:
                pass
    return None, None

def main():
    groups = pids_by_name()
    if not groups:
        print("未找到微信相关进程")
        return
    all_pids = set()
    for name, ps in groups.items():
        print(f"{name}: {ps}")
        all_pids.update(ps)
    ports = listening_ports(all_pids)
    print(f"\n微信进程监听端口 ({len(ports)}): {ports}\n")
    hits = []
    for p in ports:
        path, body = probe(p)
        if body:
            print(f"[HIT] {p}{path}")
            print("   ", body[:600].replace("\n", " "))
            hits.append(p)
    if not hits:
        print("没有端口响应 DevTools 协议 → 当前微信未开启调试端口。")

if __name__ == "__main__":
    main()
