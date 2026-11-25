# RUNBOOK · 羊了个羊：星球 一键全解

> 一页式操作手册。所有内容都是在真机上踩过、修过的，不是推演。

---

## 0. 首次使用（只做一次）

```bat
git clone https://github.com/GlrAoc/wxsheep
cd wxsheep
setup.cmd                        :: 拉取 sheep-solver 与 WMPFDebugger，并自动打补丁
cd dbg\WMPFDebugger && yarn install
```

`setup.cmd` 幂等，重复执行只做检查不做破坏。frida 依赖的坑见 [ENVIRONMENT.md](ENVIRONMENT.md) 第 3.3 节。

---

## 1. 正常流程（90% 的情况）

```
1) 双击  dbg\sheep-solver\oneclick.cmd
2) 盯着黑窗口，等这一行出现：
     [proxy] hook ready after 25s, frida target pid=1632
3) 这时才去微信里打开（或重开）「羊了个羊：星球」，进关卡
4) 脚本自动接管：读牌 → 求解 → 复算 → 点击 → 下一关
5) 出现 === challenge finished === 就是这轮打完了
```

**唯一的铁律：先起脚本，后开窗口。** 顺序错了就会卡在
`[wait] cannot read the game yet`，重跑多少次都没用。

---

## 2. 为什么是这个顺序（机制）

| 事实 | 数值 | 证据 |
|---|---|---|
| 代理端口 62000 开始监听 | ~3 秒 | 日志 `[server] proxy server running` |
| frida `--auto-detect` 扫模块算偏移 | **20~25 秒** | `[frida] auto-detecting` → `[frida] script loaded` 的时间差 |
| hook 生效范围 | 只对**挂上之后**加载的小程序页面 | 同一窗口在 hook 前/后加载，`miniappConnected` 一真一假 |

端口监听 ≠ 就绪。2026-11-24 02:03 那次失败就是窗口（02:04:14）和
`script loaded`（02:04:14）撞在同一秒，页面抢在 hook 前面加载了。

---

## 3. 状态判读（`oneclick.cmd --diagnose`）

```
port 62000: LISTENING pid 22184          ← 代理在跑
frida attach: pid 1632 alive=true miniappConnected=false
  hookReadyAt=02:08:18  proxyStartedAt=02:07:53
newest WeChatAppEx start: 02:04:14       ← 最新游戏窗口进程的创建时刻
game object readable: no
```

判读表：

| 组合 | 结论 | 处置 |
|---|---|---|
| `hookReadyAt` 有值，`小程序起于` **晚于** `hookReadyAt+5s`，`miniappConnected=true` | 一切正常 | 进关卡即可 |
| `miniappConnected=false`，`小程序起于` **早于** `hookReadyAt` | 窗口比 hook 早开 | 关窗重开一次，**别重启代理** |
| `miniappConnected=false`，`小程序起于` **晚于** `hookReadyAt+5s` | 真挂错进程了 | 脚本会自动重启代理，重启后再等 hook ready |
| `hookReadyAt=NOT YET` | auto-detect 还在跑 | 等，别开窗口 |
| `frida attach` 显示 `已死亡` | 微信换号/重启，旧进程没了 | 脚本会自动重启代理 |
| `port 62000: closed` | 代理没跑 | `oneclick.cmd --start-proxy` |

---

## 4. 故障排查表（全部真实发生过）

| 现象 | 根因 | 处置 |
|---|---|---|
| `'Debugger"' 不是内部或外部命令`、`'iting'`、`'window'`、`'first'` 等碎片报错 | `.cmd` 里混进了中文注释（UTF-8），文件开头有 `chcp 936`，cmd.exe 按字节偏移定位下一行时错位，把后面几行拆碎执行 | `.cmd` 只写纯 ASCII + CRLF。改完必须归一化换行 |
| `Cannot find module ...\sheep-solver\src\index.ts` | 上一条导致 `cd /d ...\WMPFDebugger` 没执行成功，`npx` 在错目录找入口 | 同上 |
| `[proxy] attached pid 1632 ... 小程序已连=false` 反复刷 | 窗口抢在 hook 前加载 | 关窗重开（不是重启代理） |
| `[wait] cannot read the game yet (注入目标=未知(无日志))` | 代理不是本脚本启动的，或日志文件缺失 | 用 `oneclick.cmd` 重启代理；或在 `proxy.cmd` 里确保设置了 `MINIAPP_PROXY_LOG` |
| 日志文件恒 0 字节 | `detached` 子进程的 stdout 句柄在 Windows 上落不到父进程打开的文件 | 已改为代理自己 `createWriteStream`（见 `docs/patches/`） |
| `phase=drift` exit 3（教学关点完就报） | 通关瞬间游戏自动切下一关，状态签名对不上 | 已修：点击数达到方案步数即视为清关 |
| 求解 45 秒仍无解（`best left=51~96`） | 7 格硬约束 + 该局排布确实无解 | 游戏内手动洗牌，重跑脚本。243 张那局洗牌后 1 秒出解 |
| 换号后连不上 | 微信重启导致 WMPF 浏览器进程换 pid | 脚本检测到注入目标已死会自动重启代理；重启后要等 hook ready 再开窗口 |

---

## 5. 常用命令

```bat
oneclick.cmd                     清关，一直清到这轮结束
oneclick.cmd --dry               只求解、不点击（安全预览）
oneclick.cmd --diagnose          打印现场状态后退出
oneclick.cmd --start-proxy       只拉代理（含等 hook ready），不开游戏
oneclick.cmd --stop-proxy        关掉代理
oneclick.cmd --seeds 6           更多并行求解路数（默认 4）
oneclick.cmd --solve-sec 90      每路求解预算（默认 45 秒）
oneclick.cmd --wait-sec 120      120 秒内没进关卡就退出（默认无限等）
oneclick.cmd --tick 120          点击间隔毫秒（默认 150）
```

退出码：`0` 至少清完一关；`1` 通道/前置不满足；`2` 某关无解；`3` 执行异常中止（未盲点）。

---

## 6. 维护动作

| 场景 | 动作 |
|---|---|
| 微信升级（WMPF 版本号变化） | 日志里 `[frida] auto-detecting` 后若无 `detected hook offsets`，说明偏移失效，需要更新 WMPFDebugger 或手工填偏移表 |
| 日志太多 | `dbg\sheep-solver\logs\` 直接删；只有 `proxy.pid` 会被脚本读，删了也能重建 |
| 想彻底停干净 | `oneclick.cmd --stop-proxy`，再确认 62000 没有 LISTENING |
| 换机器 / 重装 | 按 `docs/ENVIRONMENT.md` 走，代理补丁在 `docs/patches/` |

---

## 7. 不要做的事

- 不要"先把游戏窗口开着，再慢慢跑脚本"——顺序反了就一定失败。
- 不要用 `windowsHide` 之外的终端窗口去 `Ctrl+C` 代理；代理是 detached 的，`--stop-proxy` 才干净。
- 不要在有牌在盘上时中断执行再重跑——编排器只接受"手牌和托盘都为空"的干净局面，残局请重新进关。
