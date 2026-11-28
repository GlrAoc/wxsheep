# MOBILE SOLUTIONS · 手机端一键全消的两条实现路径

> **状态：ARCHIVED（2026-11-26 16:16 停止推进，仅作技术存档）**
> 用户在核心能力验证通过后决定不再继续手机端。设备与 PC 环境已清理干净。
> 本文保留完整实测数据，供日后重启时免于重复试错。

## 【实测结论 · 2026-11-26 定稿】

本节取代下方所有推演。两步实测把方案 A 证伪、方案 B 验证到"可执行任意 JS"。

### 方案 A（免 root / CDP）→ **不可行**

| 步骤 | 结果 | 结论 |
|---|---|---|
| `nslookup debugxweb.qq.com` | NXDOMAIN | 官方开关域名已被腾讯回收 |
| 但 `/proc/net/unix` | 出现 `@webview_devtools_remote_18562` | 指令仍被本地拦截执行，**调试确实已打开** |
| `adb forward` + `/json/version` | `Chrome/156.0.8078.79`、`V8 15.6.75.27` | 主进程 CDP 真实可用 |
| `/json` 枚举 | 仅微信搜索页，无小游戏 | 主进程看不到 appbrand |
| 进游戏后 `ss -xlp` | appbrand **无任何 devtools socket** | `19590` 是 WebView 组件残留（`NOT_HELD`） |

**根因**：小游戏不用 WebView 渲染。`/proc/<pid>/maps` 显示 appbrand 加载的是：

```
libmmv8.so        27,443,200 B   ← 微信自研 V8 宿主（J2V8）
libmmj2v8.so                     ← JNI 桥
libwebviewchromium_*.so          ← 仅服务 web-view 组件
```

没有 Chromium renderer，就没有 `webview_devtools_remote`，也就没有 CDP。
**「手机微信 CDP 可调试小游戏」这一假设不成立，方案 A 到此为止。**

### 方案 B（root / frida）→ **已验证可行**

| 步骤 | 结果 |
|---|---|
| frida-server 17.18.0 部署 | `LISTEN 0.0.0.0:27042`，`su -c` 启动 |
| `frida-inject -p <appbrand1>` | `[ok] injected pid=... arch=arm64` |
| `libmmv8.so` 符号 | **未 strip**，完整保留 Itanium ABI |
| `Script::Compile` / `Script::Run` / `String::NewFromUtf8` / `Isolate::GetCurrent` / `Function::Call` | 5 个符号全部解析到真实地址 |
| V8 上下文枚举 | 6 个 ctx，1 号无 `wx`，2~6 号均可调 `wx` |
| 执行 `wx.showToast({title:"F-OK"})` | **手机屏幕出现 toast（截图取证）** |

**三个必须记住的 ABI 细节**（踩过坑，均已修正）：

1. **成员函数带隐式 `this`**：`Function::Call` 是成员函数，x0 是 `Function*`，
   `Local<Context>` 在 **x1**；`Script::Run` 同理，`this=Script*` 在 x0。
   （`Script::Compile` 是 static，无 this，x0 就是 context。）
2. **`Function::Call` 的 argc 在 x3**：误取 x2 会得到 `recv` 指针，表现为
   `argc=2018304016` 这类异常大整数——这是参数错位的信号。
3. **一个进程多个 context**：首个命中的 ctx 未必是游戏逻辑层（无 `wx`），
   必须枚举遍历。判据：`wx.showToast` 调用后 `Script::Run` 返回 `null` = 该 ctx 无 `wx`。

### 当前能力边界（实测）

| 能力 | 状态 | 证据 |
|---|---|---|
| 在游戏 V8 上下文执行任意 JS | **可用** | 截图 `F-OK` toast |
| 调用 `wx.*` API | **可用** | `wx=1`，showToast 成功 |
| 读 `GameGlobal` 全局键 | **可用** | 不同 ctx 分别返回 `n=15` 与 `n=51` |
| 引擎侧读回返回值（`Value::ToString`） | 不可用 | 符号未导出 |
| `wx.getFileSystemManager().writeFileSync` | **失败** | toast 显示 `REL:Error: writeFile` |

**关于 context 数量**：一个 appbrand 进程内存在多个 V8 context，`GameGlobal`
的键数不同（15 vs 51），说明逻辑层与框架层分离。**必须按内容特征挑选**，
不能取第一个成功的。

**数据回传通道评估**：

| 通道 | 容量 | 状态 |
|---|---|---|
| `wx.showToast` | ~30 字符 | 已验证可用 |
| `wx.showModal` | 长文本（可滚动） | 可用，需截图 OCR |
| `wx.setClipboardData` | 长文本 | 待验证（配合 root 读剪贴板） |
| 文件系统 | 无限 | **当前不可用**（writeFile 报错） |
| `wx.request` 到 PC | 无限 | 受域名白名单限制，正式版不可用 |

**结论**：读牌数据（516 张 ≈ 30 KB）的传回需解决通道问题。优先级：
① 排查 writeFile 失败原因（路径/初始化时机）；② 剪贴板；③ 分段 toast。
这三条任一打通即可闭环，不影响已证明的执行能力。

### 修正后的路线

```
读牌：JS 遍历 GameGlobal 找到 cardNode/blockData 数组
   ↓  复用 board.json 结构
求解：dfs_nopark / verify_plan3 原样不动
   ↓
执行：JS 内直接调 touchStart()/touchEnd()  ← 与 PC 完全一致，零坐标零延迟
```

方案 B 不是"退而求其次"，而是**比方案 A 更强的形态**：不需要 CDP 的求值通道，
直接在 V8 里跑代码；也不需要 adb tap，直接调对象方法。

---

# 以下为 2026-11-26 之前的推演记录（保留备考）

> 结论先行：手机端**不需要重做视觉识别**。微信 XWeb 内核存在一条官方调试通道，
> 打通后拿到的 CDP 与 PC 端 WMPFDebugger 是同一套协议，PC 的
> `inject.js` / `bot.js` / `apply_plan.js` 可近乎原样复用。
> 两个方案的区别不在"能不能读牌"，而在**如何取得 JS 执行上下文**。

---

## 0. 本次实测环境（证据）

| 项 | 值 | 获取方式 |
|---|---|---|
| 微信版本 | 8.0.80（versionCode 3220，targetSdk 34） | `dumpsys package com.tencent.mm` |
| 系统 | Android 14 / SDK 34，1240×2772 @ density 560 | 同 PC 端探测记录 |
| 设备 | RMX3700（真我 GT Neo5 SE），序列号 `d284ed5f` | `adb devices -l` |
| root | **可用**，`su -c id` → `uid=0(root) ... context=u:r:ksu:s0` | KernelSU Ultra + SUSFS |
| 小程序宿主进程 | `com.tencent.mm:appbrand1` | `ps -A` |
| 渲染进程 | `com.tencent.mm:xweb_privileged_process_0`<br>`com.tencent.mm:xweb_sandboxed_process_0:...pinus.sdk.process.SandboxedProcessService` | `ps -A` |
| devtools socket | **当前不存在**（`/proc/net/unix` 无匹配，root 下亦无） | 未开启调试开关 |
| 小游戏缓存 | `/data/data/com.tencent.mm/files/liteapp/403904c3…/wxalite*`<br>`/data/data/com.tencent.mm/MicroMsg/appbrand/{pkg,pagesidx}` | root 可读 |
| 每进程 profile | `/data/data/com.tencent.mm/app_webview_com_tencent_mm_appbrand{0..3}` | 证明走标准 WebView 内核机制 |

**关键推论**：`app_webview_com_tencent_mm_appbrand*` 这几个目录是 Chromium 内核的
标准 profile 目录命名。既然内核是 Chromium 系，其 DevTools 通道就走
`localabstract:webview_devtools_remote_<pid>` 这套标准 IPC —— 与 PC 端
「frida 打桩骗出 CDP」是同一终点，只是**开启手段不同**。

---

## 1. 方案 A · 免 root（官方调试开关 + CDP）

### 1.1 核心机制

微信 XWeb 支持一个**访问即生效**的内核调试开关，无需 root、无需改包：

```
微信内打开 → http://debugxweb.qq.com/?inspector=true
        ↓  （跳转到微信首页 = 已生效，无面板、无提示）
彻底结束微信进程 → 重启 → 进入小游戏
        ↓
/proc/net/unix 出现 @webview_devtools_remote_<pid>
        ↓  adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>
http://127.0.0.1:9222/json  →  webSocketDebuggerUrl
        ↓
CDP 直连（Chromium 标准协议，支持 Runtime.evaluate）
        ↓
复用 PC：bot.js / apply_plan.js / dfs_nopark.js
```

### 1.2 为什么这条路径优于视觉识别

| | 视觉重建 | CDP 直连 |
|---|---|---|
| 读牌来源 | 像素推断遮挡关系 | 直接读 `cardDataObj` / `cardNode` 数组 |
| 516 张关准确率 | 60~85%（暗牌漏检） | 100%（与 PC 同源） |
| 求解器 | 需补前瞻/信念分布 | **完全不用改** |
| 执行方式 | 坐标 tap，需每步校验 | `touchStart/touchEnd` 对象方法，零坐标 |
| 单局耗时 | 8~15 分钟 | **8~20 秒** |

PC 端之所以能 879 张秒清，靠的就是 `bot.js:492` 直接调组件方法：

```js
try { comp.touchStart(STUB); } catch (e) { }
try { comp.touchEnd(STUB); } catch (e) { }
```

这条调用链与"设备是 PC 还是手机"无关 —— 只要能在 JS 上下文里拿到组件引用，
就能照抄。

### 1.3 复用改造成本

`inject.js` 的 WebSocket 地址本来就是命令行参数：

```bash
node inject.js <script.js> ws://127.0.0.1:62000   # PC
node inject.js <script.js> ws://127.0.0.1:9222/devtools/page/<ID>   # 手机
```

需要新增的只有一个 `mobile/cdp_bridge.js`（约 80 行）：

1. `adb shell cat /proc/net/unix | grep devtools_remote` → 取 pid
2. `adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>`
3. `GET /json` 列出 target，按 `title`/`url` 命中羊了个羊
4. 输出 `ws://127.0.0.1:9222/devtools/page/<id>`，写进 `CDP_WS` 环境变量

`oneclick.js` 已经读 `process.env.CDP_WS`（第 97 行），**无需改一行编排代码**：

```js
const CDP = Object.assign({}, process.env, {
  CDP_WS: process.env.CDP_WS || 'ws://127.0.0.1:62000'
});
```

### 1.4 与 PC 的两处协议差异（已知且可控）

| 差异 | PC（WMPF 代理） | 手机（原生 CDP） | 处理 |
|---|---|---|---|
| 求值方式 | 只支持 `Debugger.evaluateOnCallFrame`<br>（需先 pause） | 支持 `Runtime.evaluate` | 手机侧更简单，可保留 pause 写法保持兼容 |
| target 发现 | 固定 62000 单连接 | 需 `/json` 枚举 + pid 匹配 | 由 `cdp_bridge.js` 承担 |
| 页面重载后 | 连接保持 | page id 变化，需重连 | 监听 `/json` 轮询，id 变化即重建 |

### 1.5 降级路径 A2（开关失效时）

若某版本微信移除了 `debugxweb` 开关，或实测发现**该开关只对 H5 不覆盖小游戏**，
则退回视觉方案：

- 读牌：`analyze_shot.py`（已有）+ 遮挡图重建（待写）
- 执行：`adb shell input tap`，或 scrcpy control socket（延迟从 ~300ms 降到 ~40ms）
- 必须先补「暗卡信念分布 + 信息增益」，否则 500+ 张关胜率不足

工程量：从 1~2 天变成 5~8 天，且精度不可控。**这是兜底，不是首选。**

### 1.6 方案 A 的风险

1. **开关覆盖面未知**（最大不确定项）：官方文档语境是"H5 网页调试"，
   小游戏是否同享未验证。判定方法见 §3 的 30 秒验证。
2. **开关可能被移除**：属非公开接口，随版本收紧。
3. **需 USB 连接**：`adb` 依赖数据线；无线调试（`adb tcpip 5555`）可解，但首次仍需线。
4. **微信重启要求**：开关必须"彻底结束进程"后重启才生效，只退桌面无效。

---

## 2. 方案 B · root（frida 强开 + 输入注入）

### 2.1 核心机制

不依赖官方开关，直接用 root 权限在 XWeb 进程内把 CDP 打开：

```
frida-server（KernelSU 授予 root）
        ↓  attach  com.tencent.mm:appbrand1
hook WebView.setWebContentsDebuggingEnabled / XWeb 等价入口 → 强制 true
        ↓
socket 出现（与方案 A 同一终点，但不受官方开关左右）
        ↓
CDP 直连 + root 级输入注入
```

### 2.2 root 的三项独有能力

| 能力 | 实现 | 收益 |
|---|---|---|
| **强开 CDP** | frida hook `setWebContentsDebuggingEnabled`，或直接调用 XWeb 内部 API | 不依赖 `debugxweb` 开关，微信升级仍可用 |
| **输入注入** | `echo ... > /dev/input/eventX`（`sendevent`）或 `input` 走 root | 点击延迟 < 10ms，无系统层排队 |
| **离线复现** | 读 `files/liteapp/.../wxalite*` 缓存包，解 wxapkg | 可离线分析牌面算法、无需每次进游戏 |

其中「输入注入」在 CDP 已通的前提下是**冗余的** —— 因为走 `touchStart/touchEnd`
根本不产生触摸事件。它只在 A2 视觉降级路径下有价值。

root 的真正独有价值是**第一项**：不依赖官方开关。

### 2.3 更激进的 B+ 变体：改包注入

root 可写 `files/liteapp/.../wxalite*/` 与 `MicroMsg/appbrand/pkg/`：

```
解 wxapkg → 在游戏入口插一行 __autoSolve() → 重打包 → 回写 → 重启小程序
```

风险显著高于其他路径：小游戏包有 md5 完整性校验，改后可能被判定为
"包损坏"并强制重新下载；且不同版本包结构会变。**不推荐作为主线**，
仅在 frida 注入被反调试拦死时考虑。

### 2.4 方案 B 的风险

1. **反调试**：微信主进程有 frida 特征检测（端口 27042、`frida` 字符串、
   `/proc/self/maps` 里的 `frida-agent`）。需 frida-server 改名 + 非默认端口 +
   `SUSFS` 隐藏挂载。用户设备已有 SUSFS，这是有利条件，但不等于零风险。
2. **注入点漂移**：XWeb 是闭源 SDK，`setWebContentsDebuggingEnabled` 的符号
   随版本变化，需要每次升级重新定位。
3. **稳定性**：frida 常驻 appbrand 进程可能引起小程序崩溃/白屏，影响正常使用。
4. **不可分发性**：root 方案只对本人设备有效，无法给他人用（PC 版可分发）。

---

## 3. 30 秒验证（决定 A 是否成立）

> 这是整个手机端投入产出的**唯一分水岭**。不通则 A 退化为 A2，直接跳到 §4 的决策。

步骤（全部只读，不改任何文件）：

1. 用户在手机微信里给自己发一条消息，内容：
   `http://debugxweb.qq.com/?inspector=true`，然后点开它。
   → 跳转到微信首页 = 已生效（无面板属正常）。
2. 彻底结束微信：`adb shell am force-stop com.tencent.mm`
3. 重新打开微信 → 进入羊了个羊 → 停在关卡画面。
4. 电脑执行：

```powershell
adb shell cat /proc/net/unix | Select-String "devtools_remote"
```

| 输出 | 判定 | 下一步 |
|---|---|---|
| `@webview_devtools_remote_<pid>`，且 pid = appbrand 进程 | **A 成立** | 写 `cdp_bridge.js`，1~2 天打通全流程 |
| 只有 H5 页面的 socket，无 appbrand pid | 开关不覆盖小游戏 | 转 B（root 强开） |
| 无任何 devtools socket | 开关在当前版本已失效 | 转 B 或 A2 |

---

## 4. 对比矩阵

| 维度 | A · 免 root（开关+CDP） | B · root（frida 强开） |
|---|---|---|
| 读牌精度 | 100%（同 PC） | 100%（同 PC） |
| 执行速度 | 8~20 秒 / 局 | 8~20 秒 / 局 |
| 工程量 | **小（1~2 天）** | 中（3~5 天） |
| 前置条件 | USB 调试 + 手机点一次链接 | root + frida-server + SUSFS 隐藏 |
| 抗微信升级 | 弱（开关可能移除） | 中（注入点需重定位） |
| 检测风险 | **低**（用的是官方通道，无注入） | 中（frida 特征、maps 扫描） |
| 可分发给他人 | **可以**（只需照做两步） | 不可以（依赖 root） |
| 对日常使用影响 | 无 | frida 常驻可能致小程序崩溃 |
| 兜底能力 | 弱（失效即需视觉） | 强（可改包、可离线分析） |

---

## 5. 决策建议

**先做 §3 的 30 秒验证，再决定投入。** 逻辑链：

```
30 秒验证
├─ 通过 → 走 A。工程量 1~2 天，无检测风险，可分发。
│         这是唯一"高性价比且干净"的路径。
└─ 不通过
   ├─ 只是想要"自己手机上能自动清关" → 走 B（root 已具备，3~5 天）
   └─ 想要"给别人也能用" → 走 A2（视觉，5~8 天，精度不可控）
```

**明确不推荐的组合**：在 A 已验证可行的前提下仍去做 A2 视觉重建 ——
那是把一个 1 天的问题做成 8 天的问题，并且把 100% 精度换成 70%。

**明确的判断依据**：PC 端已经把「读牌 + 求解 + 执行」三件事全部做完并验证，
手机端唯一缺的是**进入 JS 上下文的那把钥匙**。所有工作量都应该压在找钥匙上，
而不是重新造一台车。

---

## 6. 分阶段实施（A 成立时的路线）

| 阶段 | 内容 | 完成判据 | 预估 |
|---|---|---|---|
| M0 | 30 秒验证：socket 是否存在 | `/proc/net/unix` 出现 appbrand 的 devtools_remote | 30 秒 |
| M1 | `cdp_bridge.js`：自动发现 + forward + 输出 ws 地址 | `node mobile/cdp_bridge.js` 打印可用 ws，`/json/version` 返回 `Android-Package: com.tencent.mm` | 半天 |
| M2 | 读牌验证：`probe` 拿 `document.gameContext` | 输出 `{init:true, blocks:516, levelKey:…}`，与手机画面牌数一致 | 半天 |
| M3 | 求解复用：`dfs_nopark` 吃手机 board | `verify_plan3` 返回 WIN | 半天 |
| M4 | 执行复用：`bot.js` 注入 + `apply_plan` | 手机端跑完一关，结算页「挑战成功」 | 半天 |
| M5 | 封装 `mobile/oneclick.cmd` | 双击即全自动，含 doctor 自检 | 半天 |

---

## 7. 合规声明

与 PC 版一致：本工具通过非公开协议读取游戏本地状态并模拟操作，
违反用户协议，存在账号风险。仅限自有设备与技术研究使用。
