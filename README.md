# 羊了个羊：星球 · 本地全解工具

两条独立的技术路线，同一套求解器思想：

| 路线 | 数据来源 | 状态 |
|---|---|---|
| **主线路 A：调试通道** | 通过 CDP 直接读游戏对象的真实牌面（`nowLevelBlockObj`），离线求解后走组件内部接口点击 | **已实战验证**，见下方战绩 |
| **备选线 B：屏幕视觉** | 截图 → 牌区定位 → 图标聚类 → 遮挡判定 → 7 槽求解 | 教学关可全清；密集主关受"无前瞻"限制 |

A 线不碰任何网络协议、不伪造计分请求，只在客户端侧读状态 + 点击（与 2022 年那批
`/easygame2021` 抓包项目完全不同——那条路 2022-09-21 已被腾讯加签废止）。

## 仓库结构

本仓库只含文档、视觉备选方案与工具脚本。**可运行的一键脚本在独立仓库**：

- 核心脚本 → [GlrAoc/sheep-solver](https://github.com/GlrAoc/sheep-solver)
- 调试代理 → [evi0s/WMPFDebugger](https://github.com/evi0s/WMPFDebugger)（第三方，GPL-2.0，需另装并打补丁）

克隆到 `dbg/sheep-solver/` 与 `dbg/WMPFDebugger/` 后，目录结构即与本 README 描述一致。

## 快速开始（A 线，PC 微信）

### 第 1 步 · 取代码（仅首次）

```bat
git clone https://github.com/GlrAoc/wxsheep
cd wxsheep
setup.cmd
```

`setup.cmd` 会把两个依赖拉到 `dbg\` 下——核心脚本 `sheep-solver` 与调试代理 `WMPFDebugger`——并自动给代理打上日志补丁。等价的手动命令：

```bat
git clone https://github.com/GlrAoc/sheep-solver   dbg\sheep-solver
git clone https://github.com/evi0s/WMPFDebugger    dbg\WMPFDebugger
```

### 第 2 步 · 装代理依赖（仅首次）

```bat
cd dbg\WMPFDebugger
yarn install
```

frida 若拿不到预编译包会退化成源码编译并失败，处理办法见 [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) 第 3.3 节。

### 第 3 步 · 通关

```
双击  dbg\sheep-solver\oneclick.cmd
```

就这一条。它会自己：确保调试代理在跑 → 等 hook 挂上 → 等关卡出现 → 读牌 →
4 路并行求解 → 独立复算判 WIN → 注入 → 逐步点击 → 清完自动接下一关。

### 铁律：先起脚本，后开窗口

`frida --auto-detect` 挂 hook 要 **20~25 秒**（端口监听只要 3 秒，别被骗）。
hook 只对**挂上之后**才加载的小程序页面生效。所以顺序必须是：

1. 双击 `oneclick.cmd`（或 `oneclick.cmd --start-proxy`）
2. 等它打印 `[proxy] hook ready after Ns, frida target pid=...`
3. 再打开 / 重开游戏窗口、进关卡

反过来（先开窗口再跑脚本）一定会卡在 `cannot read the game yet`，不是坏了，是时机不对。

## 目录

```
WXweb/
├─ dbg/
│  ├─ WMPFDebugger/         调试代理（frida 注入 RadiumWMPF），独立 git 仓库
│  └─ sheep-solver/         求解器 + oneclick 编排器，独立 git 仓库
├─ docs/
│  ├─ RUNBOOK.md            操作手册 / 状态判读 / 故障排查表
│  ├─ ENVIRONMENT.md        版本清单、校验值、从零重建步骤
│  ├─ MOBILE-PLAN.md        手机端路线评估（下一步）
│  └─ patches/              代理侧补丁（重装后一键还原）
├─ sheeptool/               B 线：屏幕视觉（capture/vision/solver/render）
├─ sheep_run.py             B 线入口
└─ tools/ verify_coords.py  坐标校验
```

## 实战战绩（A 线）

| 关卡 | 牌数 | 结果 |
|---|---|---|
| 80001（教学） | 18 | 18 步，verify WIN |
| 90024 | 243 | 手动洗牌后 243 步全清（洗牌前 7 格硬约束证明无解） |
| 102876 | 879 | 879 步 / 3 分 20 秒，结算「11599 玩家通关」 |
| 103045 | 516 | 516 步 / 134 秒，结算「21050 玩家通关」 |
| 换号后 80001+160024 | 18+183 | 全清，结算「22237 只羊」 |

牌面复现零失配（18/243 均 `identical`），方案均纯点击零道具。

## 文档

- 操作与排障：**`docs/RUNBOOK.md`**
- 环境与重建：**`docs/ENVIRONMENT.md`**
- 手机端计划：**`docs/MOBILE-PLAN.md`**

## 风险

- 违反游戏用户协议，存在战绩清零 / 封号可能，风险自负。
- A 线强依赖 WMPF 版本（当前 26134）；微信升级后需重新核对 `--auto-detect` 偏移。
