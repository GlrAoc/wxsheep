"""羊了个羊：星球 —— 客户端视觉辅助工具（命令行入口）。

用法:
    python sheep_run.py --image 截图.png                # 离线分析一张截图
    python sheep_run.py --live                          # 截取当前游戏窗口并分析
    python sheep_run.py --live --auto --steps 6         # 自动点击（默认逐帧复核）

安全约定:
    默认只输出建议、不点击。--auto 才启用鼠标注入，且每一帧重新识别后再决策。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

from sheeptool import vision
from sheeptool import solver as solver_mod
from sheeptool import render


def analyze_image(img, slot_limit: int, verbose: bool = True, registry=None):
    board = vision.find_board(img)
    cards = vision.detect_cards(img, board)
    reg = registry or vision.TypeRegistry()
    ntypes = reg.assign(cards)
    slots, slot_unknown = vision.read_slots(img, board, reg)
    plan = solver_mod.plan(cards, slots, slot_limit=slot_limit)

    if verbose:
        clickable = sum(1 for c in cards if not c.blocked)
        print(f"棋盘区域      : {board}")
        print(f"可见卡牌      : {len(cards)} 张（可点击 {clickable} 张）")
        print(f"图标类别      : {ntypes} 类")
        cnt: dict[int, int] = {}
        for c in cards:
            cnt[c.ttype] = cnt.get(c.ttype, 0) + 1
        print("类别分布      : " + ", ".join(f"#{k}×{v}" for k, v in sorted(cnt.items())))
        print(f"槽位已占用    : {slots or '空'}" + (f"（另有 {slot_unknown} 张未识别）" if slot_unknown else ""))
        print()
        if plan.steps:
            print(f"推荐序列（{len(plan.steps)} 步）:")
            print(render.render_step_list(plan, cards))
        else:
            print("推荐序列      : 无")
        print(f"说明          : {plan.note}")
        print()
    return board, cards, ntypes, slots, slot_unknown, plan


def _out_path(user: str | None, tag: str) -> Path:
    if user:
        return Path(user)
    d = Path("out")
    d.mkdir(exist_ok=True)
    return d / f"advise_{tag}.png"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="羊了个羊视觉辅助")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="离线分析指定截图")
    src.add_argument("--live", action="store_true", help="截取当前游戏窗口")
    ap.add_argument("--auto", action="store_true", help="自动执行点击（仅 --live 有效）")
    ap.add_argument("--steps", type=int, default=6, help="自动模式最大步数")
    ap.add_argument("--slot-limit", type=int, default=7)
    ap.add_argument("--out", help="标注图输出路径")
    ap.add_argument("--json", action="store_true", help="额外输出 JSON 摘要")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.image:
        img = cv2.imread(args.image, cv2.IMREAD_COLOR)
        if img is None:
            print(f"无法读取图片: {args.image}", file=sys.stderr)
            return 2
        board, cards, ntypes, slots, slot_unknown, plan = analyze_image(
            img, args.slot_limit, not args.quiet)
        vis = render.render(img, cards, plan, ntypes, args.slot_limit)
        out = _out_path(args.out, "offline")
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), vis)
        print(f"标注图已保存  : {out.resolve()}")
        if args.json:
            print(json.dumps({
                "cards": len(cards),
                "types": ntypes,
                "slots": slots,
                "steps": [{"idx": s.card_index, "type": s.ttype} for s in plan.steps],
            }, ensure_ascii=False, indent=2))
        return 0

    # ---- 实时模式 ----
    from sheeptool import capture as cap

    img, origin, hwnd = cap.grab()
    board, cards, ntypes, slots, slot_unknown, plan = analyze_image(
        img, args.slot_limit, not args.quiet)
    vis = render.render(img, cards, plan, ntypes, args.slot_limit)
    out = _out_path(args.out, "live")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), vis)
    print(f"标注图已保存  : {out.resolve()}")

    if not args.auto:
        print("提示          : 未启用 --auto，本次未执行任何点击。")
        return 0

    if slot_unknown:
        print(f"中止          : 槽位有 {slot_unknown} 张无法识别，自动模式可能误判余量。",
              file=sys.stderr)
        return 3

    cap.focus(hwnd)
    import time as _t

    # 全程复用同一注册表：类型编号必须跨帧稳定，否则槽位记账会失真
    reg = vision.TypeRegistry()

    def stable_read(tries: int = 4, interval: float = 0.16):
        """连抓数帧，两次读数一致才采信——点击后卡牌有飞入动画，过渡帧会多读。"""
        prev = None
        snap = None
        for _ in range(tries):
            img_, origin_, hwnd_ = cap.grab()
            board_ = vision.find_board(img_)
            cards_ = vision.detect_cards(img_, board_)
            reg.assign(cards_)
            seen_, unk_ = vision.read_slots(img_, board_, reg)
            snap = (img_, origin_, hwnd_, board_, cards_, seen_, unk_)
            if seen_ == prev:
                break
            prev = seen_
            _t.sleep(interval)
        return snap

    done = 0
    max_slots = args.slot_limit
    while done < args.steps:
        try:
            img, origin, hwnd, board, cards, slots_now, slot_unk = stable_read()
        except Exception as exc:
            print(f"停止：识别失败（{exc}），可能已通关或弹出结算/复活窗口。", file=sys.stderr)
            break

        if not cards:
            print(f"停止：场上已无可识别卡牌（已点击 {done} 次）。")
            break
        if slot_unk:
            print(f"停止：槽位有 {slot_unk} 张无法识别，转人工。", file=sys.stderr)
            break
        if sum(slots_now.values()) >= max_slots:
            print(f"停止：槽位已满 {sum(slots_now.values())}/{max_slots}，转人工。",
                  file=sys.stderr)
            break

        plan = solver_mod.plan(cards, slots_now, slot_limit=args.slot_limit)
        if not plan.steps:
            print(f"停止：无可行步骤。场上 {len(cards)} 张，槽位 {slots_now or '空'}。")
            break

        s = plan.steps[0]
        c = cards[s.card_index]
        px, py = c.cx, c.cy
        sx, sy = origin[0] + px, origin[1] + py
        done += 1
        print(f"[{done}] 点 ({sx},{sy}) 类型#{s.ttype} 槽位 {slots_now or '空'}→"
              f"{s.slots_after or '空'} — {s.reason}")
        cap.click(sx, sy, settle=0.38)

    print(f"完成          : 共执行 {done} 次点击。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
