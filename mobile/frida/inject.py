# -*- coding: utf-8 -*-
"""
frida 注入器（PC 侧调试用；手机端自持见 mobile/android/）

用法：
    adb forward tcp:27042 tcp:27042
    python mobile/frida/inject.py <pid> [脚本] [等待秒数]

相比 frida-inject：
  - 能实时收取 console.log
  - 生命周期可控（可 detach 而不杀进程）
  - 支持重复注入不残留 agent
"""
import sys
import time
import os

import frida

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT = os.path.join(HERE, 'eval_payload.js')


def on_message(msg, data):
    if msg.get('type') == 'log':
        print('[log] ' + str(msg.get('payload')))
    elif msg.get('type') == 'error':
        print('[err] ' + str(msg.get('description')))
        st = msg.get('stack') or ''
        if st:
            print('[stack] ' + st.split('\n')[0])
    else:
        print('[msg] ' + str(msg))


def main():
    if len(sys.argv) < 2:
        print('usage: inject.py <pid> [script] [wait_sec]')
        return 1
    pid = int(sys.argv[1])
    script_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SCRIPT
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0

    with open(script_path, 'r', encoding='utf-8') as f:
        src = f.read()

    mgr = frida.get_device_manager()
    dev = mgr.add_remote_device('127.0.0.1:27042')
    session = dev.attach(pid)
    script = session.create_script(src)
    script.on('message', on_message)
    print('[inj] loading into pid=%d' % pid)
    script.load()
    print('[inj] loaded, waiting %.0fs' % wait)
    time.sleep(wait)
    try:
        session.detach()
    except Exception:
        pass
    print('[inj] done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
