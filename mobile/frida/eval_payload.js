// frida 通用 JS 执行器 v2（手机微信 appbrand 进程）
//
// 用法：
//   adb shell "su -c '/data/local/tmp/fi -p <pid> -s /data/local/tmp/eval_payload.js'"
//
// 关键改进（v2）：
//   1. 防重入 —— evalIn 内部触发的 Function::Call 不再递归求值（原版会 access violation）
//   2. 输出目录可配 —— 小游戏沙箱在外部存储，PC/root 可直接读
//   3. 异常隔离 —— 单个 context 崩溃不影响其它 context
//
// ABI 要点（务必保留）：
//   Function::Call(this=Function*, Local<Context> ctx, Local<Value> recv, int argc, Local<Value>* argv)
//     → x0=this, x1=ctx, x2=recv, x3=argc, x4=argv
//   Script::Run(this=Script*, Local<Context> ctx)  → x0=this, x1=ctx
//   Script::Compile 是 static → x0=ctx, x1=source, x2=origin

const PAYLOAD = '/data/data/com.tencent.mm/files/frida_payload.txt';
const MAX_CTX = 20;

const mod = Process.getModuleByName('libmmv8.so');
function sym(n) { try { return mod.findExportByName(n); } catch (e) { return null; } }

const S = {
  compile: sym('_ZN2v86Script7CompileENS_5LocalINS_7ContextEEENS1_INS_6StringEEEPNS_12ScriptOriginE'),
  run:     sym('_ZN2v86Script3RunENS_5LocalINS_7ContextEEE'),
  newStr:  sym('_ZN2v86String11NewFromUtf8EPNS_7IsolateEPKcNS_13NewStringTypeEi'),
  getIso:  sym('_ZN2v87Isolate10GetCurrentEv'),
  fcall:   sym('_ZN2v88Function4CallENS_5LocalINS_7ContextEEENS1_INS_5ValueEEEiPS5_')
};
const missing = Object.keys(S).filter(function (k) { return !S[k]; });
if (missing.length) {
  console.log('[fatal] missing symbols: ' + missing.join(','));
}

const fNewStr = new NativeFunction(S.newStr, 'pointer', ['pointer', 'pointer', 'int', 'int']);
const fCompile = new NativeFunction(S.compile, 'pointer', ['pointer', 'pointer', 'pointer']);
const fRun = new NativeFunction(S.run, 'pointer', ['pointer', 'pointer']);
const fGetIso = new NativeFunction(S.getIso, 'pointer', []);

let CODE = '';
try {
  CODE = File.readAllText(PAYLOAD);
  console.log('[payload] ' + CODE.length + ' bytes');
} catch (e) {
  console.log('[fatal] cannot read payload: ' + e.message);
}

let BUSY = false;   // 防重入：求值过程中触发的 Function::Call 直接跳过

function evalIn(ctx, code) {
  const iso = fGetIso();
  const s = fNewStr(iso, Memory.allocUtf8String(code), 0, -1);
  if (s.isNull()) return 'STR_NULL';
  const sc = fCompile(ctx, s, ptr(0));
  if (sc.isNull()) return 'COMPILE_NULL';
  const r = fRun(sc, ctx);   // null = 异常抛出
  return r.isNull() ? 'RUN_NULL' : 'OK';
}

const seen = {};
let n = 0;

Interceptor.attach(S.fcall, {
  onEnter: function (a) {
    if (BUSY) return;
    if (!CODE) return;
    const ctx = a[1];
    if (ctx.isNull()) return;
    const key = ctx.toString();
    if (seen[key]) return;
    if (n >= MAX_CTX) return;
    seen[key] = 1;
    n++;
    const idx = n;
    BUSY = true;
    let res;
    try {
      // 注入 CTX_IDX，让 payload 知道自己属于哪个 context
      const code = 'var __CTX_IDX__ = ' + idx + ';\n' + CODE;
      res = evalIn(ctx, code);
    } catch (e) {
      res = 'EXC ' + e.message;
    }
    BUSY = false;
    console.log('[ctx ' + idx + '] ' + key + ' -> ' + res);
  }
});

console.log('[hook] armed v2, ' + MAX_CTX + ' ctx max');
