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
| 求解 45 秒仍无解（`best left=51~96`） | 7 格硬约束 + 该局排布确实无解 | 自 v1.3 起会弹窗让你选道具，不再直接 `exit 2`。弹窗会先给出容量诊断：需要 N 格 / 客户端 7 格 |
| 弹窗没出现，控制台停在 `0=移出道具 1=洗牌 2=默认 3=退出` | PowerShell 不可用（PATH 被精简 / 执行策略限制） | 直接输入数字回车即可，功能等价。排查弹窗：`powershell -NoProfile -STA -ExecutionPolicy Bypass -File choose.ps1 -MsgFile <utf8>` |
| 选了「移出道具」但提示解不出 | 移出只补 3 格（手牌 7 → 暂存 3 格），两次移出才到 13 格 | 弹窗第 1 项现在会**直接把移出算进整盘方案**，并按 1→2→3 次逐级加码；解不出就说明这盘不止差 3 格 |
| 选了「洗牌」但牌面没变 | v1.2 及更早用反射搜 `*shuffle*` 方法，命中的全是渲染层 `_resetAssembler`/`_resetFrame`，属于假洗牌 | **v1.3 已修**：改调 `chessboard.updateBlockArea()`。修后实测 261 张里 241~248 张换色。若仍不变，脚本会 `exit 3` 并提示手动洗 |
| 洗牌明明生效了，还是 `exit 2` | 洗牌只重排花色、不改层叠结构与牌数，容量不够时洗多少次都无解 | 看弹窗诊断里的「需要 N 格」。N>7 就必须先用移出（手牌前 3 张挪到暂存区，手牌 -3） |
| 弹窗诊断写「需要 11 格，客户端只有 7 格」 | 261 张那局：`plan_stats` 显示第 158 步点击前手牌 11 张（12 格 2.2s 可解）；换一副花色后仍是 11 | 7+3=10，差 1 格。**1/2/3 次移出全部搜过**：6 进程并行、合计约 30 亿节点、每路 240s，`bestLeft` 只在 37~83 之间，没有方案 → 这盘在原地无解，最省事是重开这一关 |
| 求解器跑满预算仍 NO WIN，如何判断是「无解」还是「没搜到」 | `NO WIN ... budget hit (unknown)` 一律按"没证明"处理 | 只有从某个前缀出发把子树穷尽（节点数停止增长、进程正常退出）才算证明。容量算术是更强的判据：`handNeed > 7 + 3×移出次数` 直接无解 |
| 移出道具的真实语义被误解 | 暂存区的牌**可以点回手牌**（每格只有顶牌可点），凑满 3 张照样消；新牌插在"同色最后一张之后" | 见 `bot.js` / `verify_plan3.js` / `dfs_park.js`。别再把暂存区当成"永久移走" |
| `diagnoseHandNeed` 报「即使放宽到 12 格也没有解」 | 牌面数据异常（读取残缺 / 中途切关） | 关掉游戏窗口重开，重新进关卡后再跑 |
| 道具按钮点下去弹「看广告/分享」、或图标是视频号 | `userData.prop_*` 已经是 0（免费次数也用完） | 要无限道具就跑 `mod_props.cmd`，别去分享 |
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
oneclick.cmd --park 2            允许求解器规划 2 次「移出」（默认 1）
oneclick.cmd --allow-props       预先授权道具方案，不再弹窗确认
oneclick.cmd --no-park           完全不规划道具，只做纯点击
```

退出码：`0` 至少清完一关；`1` 通道/前置不满足；`2` 某关无解；`3` 执行异常中止（未盲点）。

---

## 5.1 无限道具（移出 / 撤回 / 洗牌）

```bat
dbg\sheep-solver\mod_props.cmd            :: 装上，之后三个道具随便点
dbg\sheep-solver\mod_props.cmd --status   :: 看当前状态
dbg\sheep-solver\mod_props.cmd --off      :: 还原（计数、按钮外观、点击回调）
```

装上后手牌上限、暂存区、洗牌次数都不再是瓶颈：按钮恒显 `9999`，点一次扣 `1`
会立刻补回，且**这三个动作在本关都是本地执行，不走服务端**。

**机制（读的是运行中的客户端，不是推演）**：

| 关卡 | 实现 | 位置 |
|---|---|---|
| 免费次数闸门 | `checkPropUseLimit(t)` 返回 `true` = 拦下；读 `sheepMark.propRemove/Cancel/RandomCount` 与 `getGamePropUseLimit` | `gameUiLayer` / `new-game-ui` 原型 |
| 拥有数量 | `userData.prop_remove / prop_cancel / prop_random`，`< 1` 就走 `showPropPop`（看广告/分享） | `gameUiLayer.removeEndFunc / cancelEndFunc / randomEndFunc` |
| 按钮外观 | `game-ui-item-btn.setData(owned, used, limit)`：`used>=limit` → 遮罩+视频图标；`owned>=1` → 显示数字 | 同上 3 个按钮 |

补丁因此做三件事：原型上的 `checkPropUseLimit` 恒返回 `false`、`userData.prop_*` 钉在
`9999`、每 1 秒看门狗补一次并 `setGameLayerUiData()` 重画。三个按钮的 `callBack`
再包一层，点击前后各补一次，所以「点得比看门狗快」也不会漏。

实际操作对应关系：

- 移出 → `crushArea.moveOutBlock()`（手牌非空才有效，手牌 2 张就移 2 张）
- 撤回 → `crushArea.cancelOneStep()`
- 洗牌 → `chessboard.updateBlockArea()`（位置不变、花色重排，见 4 节）

> 副作用：`userData` 由 `saveUserData()` 写回本地存档，`9999` 是持久的；服务端若在进关时
> 下发库存会覆盖回去，看门狗 1 秒内再补，只影响当次会话。`--off` 还原成装上前的值。
> 验证日期 2026-11-26：三个按钮各点一次都生效，计数保持 9999（`--status` 的 `inv` 三项）。

脚本侧也可直接调，完全不碰库存：`__sheepInf.remove()` / `.cancel()` / `.shuffle()`。

### 5.2 无解弹窗里的三个「无限」选项

`oneclick.cmd` 判定这盘解不出时会弹窗，现在除了原来 4 项，多了 3 项（值 3/4/5，退出挪到 6）：

| 选项 | 动作 |
|---|---|
| 无限移出 · 开 mod | 注入 mod → 把「移出」次数上界从 3 次放到 6 次逐级重算；还不行就顺势洗一次牌换花色再解 |
| 无限撤回 · 开 mod | 注入 mod（游戏里点错可一直回退）→ 换一组种子重解（撤回本身不改变可解性） |
| 无限洗牌 · 开 mod | 注入 mod → 自动连洗最多 12 轮，每轮洗完重新读牌求解 |

弹窗高度现在按"正文实测高度 + 按钮数"算（`TextRenderer.MeasureText`），7 项时约 613px，
以前固定 168px 的正文区会把最后两行压在按钮下面。

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
