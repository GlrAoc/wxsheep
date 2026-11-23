#!/usr/bin/env node
/**
 * 手机端探测：确认 adb 通路、拿到设备信息、抓一张当前屏幕。
 *
 *   node adb_probe.js            抓图 + 打印设备信息
 *   node adb_probe.js --no-shot  只看设备信息
 *
 * 抓到的图存到 mobile/shots/shot-YYYYmmdd-HHMMSS.png，
 * 接着用 analyze_shot.py 判断"牌面能不能被视觉读出来"。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const DIR = __dirname;
const SHOT_DIR = path.join(DIR, 'shots');
const ADB_CANDIDATES = [
  process.env.ADB || '',
  'C:\\platform-tools\\adb.exe',
  'adb'
];

function findAdb() {
  for (const c of ADB_CANDIDATES) {
    if (!c) continue;
    if (c === 'adb') {
      const r = spawnSync('where', ['adb'], { encoding: 'utf8' });
      if (r.status === 0) return 'adb';
      continue;
    }
    if (fs.existsSync(c)) return c;
  }
  return null;
}

function run(adb, args, opts = {}) {
  const r = spawnSync(adb, args, { encoding: opts.binary ? 'buffer' : 'utf8', timeout: opts.timeout || 30000, maxBuffer: 64 * 1024 * 1024 });
  if (r.error) return { code: -1, out: String(r.error.message), err: true };
  return { code: r.status === null ? -1 : r.status, out: r.stdout, errMsg: (r.stderr || '').toString().trim() };
}

const adb = findAdb();
if (!adb) {
  console.error('[FAIL] 找不到 adb。请安装 platform-tools，或设置环境变量 ADB 指向 adb.exe');
  process.exit(1);
}
console.log('[ok] adb = ' + adb);

const dev = run(adb, ['devices', '-l']);
const lines = String(dev.out).split(/\r?\n/).filter((l) => l && !/^List of devices/.test(l));
if (!lines.length) {
  console.error('[FAIL] 没有已连接设备。检查：数据线/USB 调试开关/"允许 USB 调试"授权弹窗');
  process.exit(1);
}
console.log('[ok] 设备：');
for (const l of lines) console.log('     ' + l);

const serial = lines[0].split(/\s+/)[0];
const S = (args) => run(adb, ['-s', serial, 'shell', ...args]);

console.log('\n=== 设备信息 ===');
const info = {
  '型号': S(['getprop', 'ro.product.model']).out,
  '系统': S(['getprop', 'ro.build.version.release']).out,
  'SDK': S(['getprop', 'ro.build.version.sdk']).out,
  '分辨率(wm size)': S(['wm', 'size']).out,
  '密度(wm density)': S(['wm', 'density']).out,
  '前台窗口': S(['dumpsys', 'window']).out
};
for (const [k, v] of Object.entries(info)) {
  if (k === '前台窗口') {
    const m = String(v).match(/mCurrentFocus=([^\n]+)/);
    console.log(`  ${k}: ${m ? m[1].trim() : '(未取到)'}`);
  } else {
    console.log(`  ${k}: ${String(v).trim()}`);
  }
}

if (process.argv.includes('--no-shot')) process.exit(0);

if (!fs.existsSync(SHOT_DIR)) fs.mkdirSync(SHOT_DIR, { recursive: true });
const ts = new Date();
const pad = (n) => String(n).padStart(2, '0');
const name = `shot-${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-` +
  `${pad(ts.getHours())}${pad(ts.getMinutes())}${pad(ts.getSeconds())}.png`;
const out = path.join(SHOT_DIR, name);

const shot = run(adb, ['-s', serial, 'exec-out', 'screencap', '-p'], { binary: true, timeout: 60000 });
if (shot.code !== 0 || !shot.out || shot.out.length < 1000) {
  console.error('[FAIL] 截图失败：' + (shot.errMsg || shot.code));
  process.exit(1);
}
fs.writeFileSync(out, shot.out);
console.log(`\n[ok] 截图：${out}（${(shot.out.length / 1024).toFixed(0)} KB）`);
console.log('\n下一步：用视觉管线判断这张图能不能读牌');
console.log('  cd /d "E:\\Ai project file\\WXweb"');
console.log('  python mobile\\analyze_shot.py "' + out + '"');
