#!/usr/bin/env node
/**
 * CDP 探测：枚举 target、评估表达式
 *
 *   node mobile/cdp_probe.js [ws://127.0.0.1:9222/devtools/browser] [expression]
 *
 * 不带 expression 时只列 target。
 */
const WS = process.argv[2] || 'ws://127.0.0.1:9222/devtools/browser';
const EXPR = process.argv[3] || null;

const ws = new WebSocket(WS);
let seq = 0;
const pending = new Map();

function send(method, params) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params: params || {} }));
  return new Promise((resolve) => pending.set(id, resolve));
}

ws.addEventListener('message', (ev) => {
  let m;
  try { m = JSON.parse(ev.data); } catch { return; }
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m);
    pending.delete(m.id);
  }
});

ws.addEventListener('open', async () => {
  try {
    const t = await send('Target.getTargets');
    const list = (t.result && t.result.targetInfos) || [];
    console.log(`[targets] ${list.length}`);
    for (const ti of list) {
      console.log(`  ${ti.type.padEnd(8)} ${ti.targetId.slice(0, 12)}  ${String(ti.title || '').slice(0, 60)}`);
      console.log(`           ${String(ti.url || '').slice(0, 110)}`);
    }
    if (EXPR) {
      const page = list.find((x) => x.type === 'page' || x.type === 'other' || x.type === 'webview');
      if (!page) { console.log('[eval] no target'); ws.close(); return; }
      const at = await send('Target.attachToTarget', { targetId: page.targetId, flatten: true });
      const sid = at.result && at.result.sessionId;
      const id2 = ++seq;
      ws.send(JSON.stringify({
        id: id2, sessionId: sid,
        method: 'Runtime.evaluate',
        params: { expression: EXPR, returnByValue: true, awaitPromise: true }
      }));
      const r = await new Promise((res) => pending.set(id2, res));
      console.log('[eval]', JSON.stringify(r.result || r.error, null, 1).slice(0, 2000));
    }
  } catch (e) {
    console.log('[error]', e.message);
  }
  ws.close();
});

ws.addEventListener('error', () => { console.log('[error] ws connect failed'); process.exit(1); });
setTimeout(() => { console.log('[timeout]'); process.exit(1); }, 12000);
