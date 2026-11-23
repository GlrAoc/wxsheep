"""求解层：7 槽约束下的增量推荐。

只对「当前可点击」的卡做决策，不预测被遮挡的隐藏卡。
每执行一步后重新截图，隐藏卡自然转为可见——因此无需全局完美重建。
"""
from __future__ import annotations

from dataclasses import dataclass

from .vision import Card, coverage

SLOT_LIMIT = 7


@dataclass
class Step:
    card_index: int
    ttype: int
    reason: str
    slots_after: dict[int, int]


@dataclass
class Plan:
    steps: list[Step]
    slots_initial: dict[int, int]
    leftover: dict[int, int]
    unknown_clickable: list[int]
    note: str

    @property
    def ok(self) -> bool:
        return bool(self.steps)


def plan(
    cards: list[Card],
    slots_initial: dict[int, int] | None = None,
    slot_limit: int = SLOT_LIMIT,
) -> Plan:
    """生成可连续执行的点击序列。

    优先级：
      1. 槽内已有 2 张且场上有同种 → 立即消掉，回收槽位
      2. 槽内已有 1 张且场上有 ≥2 张同种 → 凑成三消
      3. 场上有 ≥3 张同种且槽位够用 → 开新一组
      4. 都不满足 → 停止（继续点只会堵槽）
    """
    slots: dict[int, int] = dict(slots_initial or {})
    cov = coverage(cards)          # 每张亮卡压住多少暗卡，用于估算点击收益
    pool: dict[int, list[int]] = {}
    unknown: list[int] = []
    for i, c in enumerate(cards):
        if c.blocked or c.ttype < 0:
            if c.ttype < 0 and not c.blocked:
                unknown.append(i)
            continue
        pool.setdefault(c.ttype, []).append(i)

    for ids in pool.values():
        ids.sort(key=lambda i: (cards[i].y, cards[i].x))

    steps: list[Step] = []
    used: set[int] = set()

    def take(t: int) -> int | None:
        for i in pool.get(t, []):
            if i not in used:
                used.add(i)
                return i
        return None

    def click(i: int, t: int, reason: str) -> None:
        slots[t] = slots.get(t, 0) + 1
        if slots[t] >= 3:
            del slots[t]
        steps.append(Step(i, t, reason, dict(slots)))

    guard = 0
    while guard < 64:
        guard += 1
        progressed = False

        # 1) 槽内 2 张，场上补 1
        for t, cnt in list(slots.items()):
            if cnt == 2:
                i = take(t)
                if i is not None:
                    click(i, t, "补齐槽内第 3 张，立即消除")
                    progressed = True
                    break
        if progressed:
            continue

        # 2) 槽内 1 张，场上补 2（先确认两张都在，避免空取）
        for t, cnt in list(slots.items()):
            if cnt != 1:
                continue
            free = [i for i in pool.get(t, []) if i not in used]
            if len(free) < 2:
                continue
            a, b = take(t), take(t)
            if a is None or b is None:
                continue
            click(a, t, "凑三消（第 1 张）")
            click(b, t, "凑三消（第 2 张）")
            progressed = True
            break
        if progressed:
            continue

        # 3) 场上现有 ≥3 张同种，开新组
        #    这类操作当场就能消掉，不会留下半成品，因此不受「待凑种类数」限制。
        best_t, best_n = -1, 0
        for t, ids in pool.items():
            free = [i for i in ids if i not in used]
            if len(free) >= 3 and len(free) > best_n:
                best_t, best_n = t, len(free)
        if best_t >= 0:
            need_new = 3 - slots.get(best_t, 0)
            if sum(slots.values()) + need_new <= slot_limit:
                for k in range(need_new):
                    i = take(best_t)
                    if i is None:
                        break
                    click(i, best_t, f"场上同种 {best_n} 张，直接凑三消")
                progressed = True
                continue

        # 4) 已无成组可能，只能主动牺牲一张换取信息。
        #    这里必须严守「每次牺牲都让局面更接近可解，而不是更接近爆槽」：
        #    连续三次实战失败都是因为槽位里同时挂了 3 组半成品（各 2 张），
        #    最后既补不上又腾不出，因此牺牲规则要按剩余余量分档。
        occupied = sum(slots.values())
        if occupied >= slot_limit - 1:
            # 只剩 0~1 格时牺牲必然引爆，不做任何操作，交回人工。
            break

        # 4a) 优先牺牲「槽内已有类型」——不增加待凑种类，且本身在向三消前进
        best_i, best_t, best_cov = None, -1, -1
        for t, ids in pool.items():
            if t not in slots:
                continue
            free = [i for i in ids if i not in used]
            if not free:
                continue
            i = max(free, key=lambda k: cov.get(k, 0))
            if cov.get(i, 0) > best_cov:
                best_i, best_t, best_cov = i, t, cov.get(i, 0)
        if best_i is not None and occupied + 1 <= slot_limit - 1:
            take(best_t)
            click(best_i, best_t,
                  f"无三消可凑，加深槽内已有类型（解放 {best_cov} 张下层牌）")
            progressed = True
            continue

        # 4b) 必须开新类型时：挑「压住最多下层牌」的那张点击。
        #     看不见下层是什么，但可以最大化「下一步露出可消牌」的概率。
        if occupied + 1 <= slot_limit - 2:
            cand2 = []
            for t, ids in pool.items():
                if t in slots:
                    continue
                free = [i for i in ids if i not in used]
                if free:
                    i = max(free, key=lambda k: cov.get(k, 0))
                    cand2.append((cov.get(i, 0), i, t))
            if cand2:
                cand2.sort(reverse=True)
                c, i, t = cand2[0]
                take(t)
                click(i, t, f"必须开新类型，选解放下层最多的一张（{c} 张）")
                progressed = True
                continue

        if not progressed:
            break

    leftover_cards = sum(len([i for i in ids if i not in used]) for ids in pool.values())
    if steps:
        note = f"可连续执行 {len(steps)} 步；执行后需重新截图继续。"
    elif unknown:
        note = "当前可点击的卡图标未能识别，建议先点任意一张刷新画面。"
    else:
        note = "场上无可凑三消组合，需等待下层卡露出。"

    return Plan(steps, dict(slots_initial or {}), dict(slots), unknown, note)
