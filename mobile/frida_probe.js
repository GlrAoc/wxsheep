#!/usr/bin/env node
/**
 * frida 探测：确认 appbrand 进程可注入、libmmv8.so 可见、V8 符号可解析
 *
 *   NODE_PATH=<WMPFDebugger>/node_modules node mobile/frida_probe.js [port]
 */
const frida = require('frida');

const PORT = process.argv[2] || '27042';

(async () => {
  const dev = await frida.getRemoteDevice(`127.0.0.1:${PORT}`);
  console.log('[device]', dev.name || dev.id);

  const procs = await dev.enumerateProcesses();
  const hit = procs.filter((p) => /appbrand/.test(p.name));
  console.log('[appbrand]', hit.map((p) => `${p.pid}:${p.name}`).join(', ') || '(none)');
  if (!hit.length) { console.log('[abort] 没有 appbrand 进程，请先进入小游戏'); return; }

  const target = hit[0];
  const session = await dev.attach(target.pid);
  console.log('[attach]', target.pid, target.name);

  const script = await session.createScript(`
    rpc.exports = {
      info() {
        const out = { modules: [], symbols: {} };
        try {
          const m = Process.getModuleByName('libmmv8.so');
          out.modules.push({ name: m.name, base: m.base.toString(), size: m.size });
        } catch (e) {
          out.err = 'libmmv8 not found: ' + e.message;
          return out;
        }
        const m = Process.getModuleByName('libmmv8.so');
        const wanted = [
          '_ZN2v86Script7CompileENS_5LocalINS_7ContextEEENS1_INS_6StringEEEPNS_12ScriptOriginE',
          '_ZN2v88Function4CallENS_5LocalINS_7ContextEEENS1_INS_5ValueEEEiPS5_',
          '_ZN2v87Isolate10GetCurrentEv',
          '_ZN2v86String11NewFromUtf8EPNS_7IsolateEPKcNS0_13NewStringTypeEi',
          '_ZN2v86Script3RunENS_5LocalINS_7ContextEEE'
        ];
        for (const w of wanted) {
          try {
            const p = m.findExportByName(w);
            out.symbols[w.slice(0, 34)] = p ? p.toString() : null;
          } catch (e) {
            out.symbols[w.slice(0, 34)] = 'ERR ' + e.message;
          }
        }
        return out;
      }
    };
  `);

  await script.load();
  const r = await script.exports.info();
  console.log('[libmmv8]', JSON.stringify(r.modules));
  console.log('[symbols]');
  for (const [k, v] of Object.entries(r.symbols || {})) {
    console.log('  ', v ? 'OK ' : 'MISS', k);
  }
  if (r.err) console.log('[err]', r.err);

  await session.detach();
  console.log('[done]');
})().catch((e) => { console.error('[fatal]', e.message); process.exit(1); });
