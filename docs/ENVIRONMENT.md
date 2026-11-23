# ENVIRONMENT · 版本清单与从零重建

> 目标：换机器、重装系统、或微信升级后，能照着这份文档回到一个**已知可用**的状态。
> 所有 sha256 都是 2026-11-24 在本机实测值。

---

## 1. 固定版本

| 组件 | 版本 / 值 | 校验 |
|---|---|---|
| Windows | 10/11 x64 | — |
| PC 微信（Weixin 4.x） | RadiumWMPF **26134** | 日志 `[frida] script loaded, WMPF version: 26134` |
| Node.js | **22.22.2** | `E:\...\node\versions\22.22.2-6\node.exe` |
| Yarn | 1.22.22 | — |
| frida（npm 侧） | 17.18.0 | 见下方 binding 校验 |
| frida 预编译包 | `frida-v17.18.0-napi-v8-win32-x64.tar.gz` | `sha256=db67a1d9cd2f6b24df699406fadd6022571ad7c00e6c4782f634039da7c0302c`，`size=49479730` |
| 解压后的 binding | `node_modules/frida/build/frida_binding.node` | `sha256=7f94e98aee0f6527e8f1fdcf1ee0c7d296a591d7c8dd0ee16bbb07b8bfeeb443`，`size=132846592` |
| 关键前提 | frida binding 必须是 **napi-v8** 预编译包 | `node-v8` 那个名字不存在，会退化成源码编译并失败 |

> 为什么必须手动放 binding：国内直连 GitHub Releases 会超时，`yarn install` 到 frida
> 这一步会退化成本地编译，而本地编译在没装 MSVC 的机器上必失败。

---

## 2. 目录约定

```
E:\Ai project file\WXweb\
├─ dbg\WMPFDebugger\     git clone（本次已提交本地改动，tag: pc-v1.0）
├─ dbg\sheep-solver\     git clone（本次已提交 oneclick，tag: pc-v1.0）
├─ dbg\frida-v17.18.0-napi-v8-win32-x64.tar.gz   预编译包（不进 git）
└─ docs\patches\        代理侧补丁
```

两个子仓库各自独立，父目录是否被 git 管理都不影响它们。

---

## 3. 从零重建（约 15 分钟）

### 3.1 两个仓库

```bat
cd /d "E:\Ai project file\WXweb\dbg"
git clone <WMPFDebugger 上游地址> WMPFDebugger
git clone <sheep-solver 上游地址> sheep-solver
```

### 3.2 打代理补丁（必须）

```bat
cd /d "E:\Ai project file\WXweb\dbg\WMPFDebugger"
git apply "E:\Ai project file\WXweb\docs\patches\0001-wmpfdebugger-logger-file-log.patch"
```

补丁做一件事：让代理按 `MINIAPP_PROXY_LOG` 环境变量**自己**写日志文件。
没有它，`oneclick` 看不到 `frida` 注入到了哪个 pid、hook 何时就绪，
只能盲猜并反复重启代理（历史故障，见 RUNBOOK 第 4 节）。

### 3.3 依赖（走国内镜像）

```bat
cd /d "E:\Ai project file\WXweb\dbg\WMPFDebugger"
powershell -NoProfile -Command "(Get-Content yarn.lock) -replace 'registry.yarnpkg.com','registry.npmmirror.com' | Set-Content yarn.lock"
yarn install
```

`yarn.lock` 里有 80+ 条地址写死 `registry.yarnpkg.com`，不改源会卡到超时。

### 3.4 放 frida binding

```bat
cd /d "E:\Ai project file\WXweb\dbg\WMPFDebugger"
tar -xzf ..\frida-v17.18.0-napi-v8-win32-x64.tar.gz -C node_modules\frida\
```

解压后必须存在 `node_modules\frida\build\frida_binding.node`（约 132 MB）。
校验：`sha256` 应为 `7f94e98a…bfeeb443`（见第 1 节完整值）。

### 3.5 自检

```bat
cd /d "E:\Ai project file\WXweb\dbg\sheep-solver"
doctor.cmd
```

全 PASS 再往下走。

### 3.6 首次运行

```bat
oneclick.cmd --start-proxy     :: 拉起代理，等 hook ready
:: 看到 hook ready 之后，再打开游戏窗口
oneclick.cmd                   :: 开始全解
```

---

## 4. 依赖的来源与坑

| 坑 | 现象 | 处置 |
|---|---|---|
| `registry.yarnpkg.com` 卡住 | `yarn install` 5 分钟无输出 | 改 `registry.npmmirror.com` |
| frida 无预编译包 | 开始源码编译，然后失败 | 手动下载 `napi-v8-win32-x64` 包解压（GitHub 慢可用 gh-proxy.com 镜像） |
| `python` 命中商店占位符 | 命令行弹出微软商店 | 用绝对路径 `E:\...\binaries\python\versions\3.13.12\python.exe` |
| `.cmd` 里写中文 | 一堆"不是内部或外部命令"的碎片 | 纯 ASCII + CRLF（`chcp 936` 下的经典崩法） |
| `taskkill /PID` 在 Git Bash 里 | 被当成路径 `/PID` | 用 PowerShell 或 `taskkill //PID` |

---

## 5. 代理侧改动清单（相对上游）

| 文件 | 改动 | 补丁 |
|---|---|---|
| `src/logger.ts` | 支持 `MINIAPP_PROXY_LOG`，代理自己写日志；首行记 pid/时间，退出记 exit code | `docs/patches/0001-...patch` |
| `yarn.lock` | registry 指向 npmmirror | 不入补丁，按 3.3 现改 |

上游代码**没有**被其他方式修改：`fin_wmpfProcess` 的选进程逻辑保持原样
（实测 `--auto-detect` 在换账号场景下选 pid 是准的，问题从来不在它）。

---

## 6. 已知限制

1. 强依赖 WMPF 版本。微信升级后 `--auto-detect` 若不再输出 `detected hook offsets`，
   需要跟进上游或手填偏移表。
2. 只支持"干净局面"接入：场上必须有牌、手牌与托盘为空。残局不接。
3. 求解器不建模道具（移出/撤回/洗牌）。遇到 7 格硬约束无解局，靠游戏内手动洗牌。
4. 单实例假设：不要同时跑两个 `oneclick`，两个进程会抢同一个 CDP 通道。
