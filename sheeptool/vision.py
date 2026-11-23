"""视觉层：定位棋盘、检测卡牌、提取图标、聚类同类、推导遮挡关系。"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

ICON_SIZE = 40          # 图标彩色归一化边长（供颜色直方图使用）
ICON_CMP = 24           # 灰度比对边长：比 40 更能吸收重采样差异
NCC_SAME = 0.80         # 判定"同类"的归一化互相关阈值


@dataclass
class Card:
    x: int
    y: int
    w: int
    h: int
    bright: bool                 # True=前景亮卡（未被遮挡）
    score: float = 0.0
    icon: np.ndarray | None = None      # 40x40 BGR
    icon_gray: np.ndarray | None = None  # 40x40 灰度
    ttype: int = -1               # 同类编号，-1 表示未能判定
    blocked: bool = False
    block_by: list[int] = field(default_factory=list)

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    @property
    def center(self) -> tuple[int, int]:
        return self.cx, self.cy

    def area(self) -> int:
        return self.w * self.h

    def iou_like(self, other: "Card") -> float:
        """交集面积占自身面积的比例（用于判定被覆盖程度）。"""
        x1, y1 = max(self.x, other.x), max(self.y, other.y)
        x2 = min(self.x + self.w, other.x + other.w)
        y2 = min(self.y + self.h, other.y + other.h)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        return (x2 - x1) * (y2 - y1) / max(1, self.area())


def find_board(img: np.ndarray) -> tuple[int, int, int, int]:
    """定位游戏棋盘区域。

    不能用「草地颜色」硬定位：同一关会换场景主题（草地→水面→雪地），
    背景一换草地检测就整体失效。因此草地只作为快速路径，
    失败时回退到固定几何——面板始终占据窗口右侧。
    """
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 草地 RGB(192,240,128) -> HSV(43,119,240) 偏黄绿
    grass = cv2.inRange(hsv, np.array([33, 60, 150]), np.array([58, 255, 255]))
    grass = cv2.morphologyEx(grass, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(grass, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c = max(cnts, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        if w * h >= 0.15 * H * W:
            return x, y, w, h

    # 回退：按窗口比例取右侧游戏面板
    x = int(W * 0.500)
    y = int(H * 0.055)
    return x, y, W - x - 1, int(H * 0.945)


def _bg_diff(img: np.ndarray) -> np.ndarray:
    """每个像素与「画面主色」的色差。

    不能靠固定色相判断卡面：同一关会更换主题（草地→水面→雪地），
    卡面配色随之整体改变（奶油色 RGB(240,240,192) → 水下橙黄 RGB(254,225,84)），
    任何写死的 H/S 区间都只在一种主题下成立。
    改为以画面里占比最高的几种颜色作为背景，与背景差异大的就是前景（卡牌）。
    """
    h, w = img.shape[:2]
    # 整窗截图才需要切掉左侧广告栏；已是局部裁剪时用全图，否则背景估计会偏
    panel = img[:, int(w * 0.5):] if w > 600 else img
    q = (panel.astype(np.uint16) // 16 * 16).astype(np.uint8)
    colors, counts = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-counts)[:3]
    diff = None
    for k in order:
        cur = np.linalg.norm(img.astype(np.int16) - colors[k].astype(np.int16), axis=2)
        diff = cur if diff is None else np.minimum(diff, cur)
    return diff


def _mask_candidates(img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """生成若干「前景＝卡面」候选掩膜，交给上层按卡牌尺寸一致性裁决。

    判据为什么是「低饱和 + 亮」
    ---------------------------
    实测本作两套主题的像素：
      - 草地主题：背景 BGR(139,254,195) → S_cv=115；木条 S_cv=147；
        卡面奶油 BGR(205,255,245) → S_cv=50, V=255。
      - 即卡面永远是「去饱和的亮色」，场景/道具永远是高饱和色。
    先前用固定 H 区间（22~36）判卡面，而奶油与灰带的 H_cv 恰好≈36，
    落在区间边界上，同一张卡被切成上下两片（实测碎片 39x20 + 38x40），
    卡牌数直接掉到 0。改判饱和度就与色相无关了。

    为什么只取「亮面」
    ------------------
    一组相邻卡是错位堆叠的：上层卡正常着色（S≈50,V=255），下层卡被压暗
    （V≈150），两者边缘紧贴，任何连通域算法都会把它们并成一块（实测 39x61），
    于是图标提取同时抓到上下两张卡的图案，类型判定随之出错。
    而「被压暗＝不可点击」本就成立，因此直接以亮面为卡牌、暗面不计入可点击集合，
    既拿到准确的点击目标，也拿到干净的图标。

    水下主题的卡面偏橙黄（RGB(254,225,84) → S_cv=170，属高饱和），
    「低饱和」在那里不成立，因此再补一组背景差分候选。两组都由
    调用方用同一客观标准（检出卡牌是否等大）挑，不需要预先知道主题。
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    op = np.ones((2, 2), np.uint8)

    def _clean(m: np.ndarray) -> np.ndarray:
        # 只做开运算去毛刺，绝不做竖向闭运算：相邻卡之间靠一条 1~2px 深绿描边
        # （V≈32）分隔，闭运算会跨过这条描边把「上暗卡 + 下亮卡」粘成一块
        # （实测 39x40 的卡被并成 39x61），图标提取随之抓到两张卡的图案。
        return cv2.morphologyEx(m, cv2.MORPH_OPEN, op)

    out: list[tuple[str, np.ndarray]] = []
    # 亮面优先：稀疏关只该取到亮卡，暗卡是多余信息
    for v_min, s_max in ((195, 70), (170, 80), (150, 70)):
        m = cv2.inRange(hsv, np.array([0, 0, v_min]), np.array([180, s_max, 255]))
        out.append((f"V{v_min}S{s_max}", _clean(m)))
    # 后备：卡面本身高饱和的主题（水下橙黄卡）
    for s_min in (120, 90):
        m = cv2.inRange(hsv, np.array([0, s_min, 110]), np.array([180, 255, 255]))
        out.append((f"hiS{s_min}", _clean(m)))
    diff = _bg_diff(img)
    for band in (90, 110, 130):
        out.append((f"bg{band}", _clean((diff > band).astype(np.uint8) * 255)))
    return out


def _comps(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    n, _, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return [(int(st[i][0]), int(st[i][1]), int(st[i][2]), int(st[i][3]), int(st[i][4]))
            for i in range(1, n) if st[i][4] >= 24]


def _pick_cards(mask: np.ndarray, ref_w: float
                ) -> tuple[list[tuple[int, int, int, int, int]], float]:
    """从掩膜里挑出「尺寸一致」的连通域作为卡牌，返回 (卡牌框, 分数)。

    所有卡牌尺寸完全相同，这是本作唯一的强先验，用它可以把
    「碎片」「粘连大块」「背景残留」一次性剔掉：
    先按宽松范围取全部候选，用各候选的中位尺寸做第二次紧过滤，
    留下的即为同尺寸卡牌，落选者按个数扣分。
    """
    comps = [c for c in _comps(mask)
             if ref_w * 0.30 <= c[2] <= ref_w * 2.00
             and ref_w * 0.30 <= c[3] <= ref_w * 2.20
             and c[4] >= ref_w * ref_w * 0.10]
    if len(comps) < 2:
        return [], -1e9
    mw = float(np.median([c[2] for c in comps]))
    mh = float(np.median([c[3] for c in comps]))
    # 卡宽必须与「棋盘宽×0.095」同量级：低于 0.7 的多半是卡面图标本身，
    # 高于 1.6 的则是多张粘连，两种都不能当卡牌。
    if not (ref_w * 0.70 <= mw <= ref_w * 1.60):
        return [], -1e9
    # 高度下限定得比宽度松：棋局最下一排常被场地边界裁短（实测 68px 只剩 52px），
    # 若按等大硬卡，整排会被误判为碎片而漏检。
    inl = [c for c in comps
           if 0.72 * mw <= c[2] <= 1.32 * mw and 0.55 * mh <= c[3] <= 1.45 * mh]
    # 只惩罚「粘连大块」：那是把两张卡并成一张的信号，会直接污染图标与点击点。
    # 偏小的连通域多是暗卡残缺边或图标，天然被上面的尺寸条件滤掉，不必连坐，
    # 否则阈值一旦放宽到能看见暗卡，分数反而被大量碎片压低而被判为更差的候选。
    over = sum(1 for c in comps
               if c[2] > 1.32 * mw or c[3] > 1.45 * mh)
    score = len(inl) - 5 * over
    return inl, score


def _face_mask(img: np.ndarray, ref_w: float,
               roi: np.ndarray | None = None) -> np.ndarray:
    """返回用于取卡面的最佳掩膜（槽位条等简单场景直接调用）。"""
    best, best_score = None, -1e9
    for _, m in _mask_candidates(img):
        if roi is not None:
            m = cv2.bitwise_and(m, roi)
        _, sc = _pick_cards(m, ref_w)
        if sc > best_score:
            best_score, best = sc, m
    return best if best is not None else np.zeros(img.shape[:2], np.uint8)


def _face_vmedian(img: np.ndarray, x: int, y: int, w: int, h: int) -> float:
    """卡面亮度中位数：亮卡 V=255、暗卡 V=153，可用于可靠区分前后层。"""
    sub = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2HSV)
    low_s = sub[:, :, 1] < 100
    v = sub[:, :, 2][low_s]
    return float(np.median(v)) if v.size else 0.0


def _extract_icon(img: np.ndarray, card: Card) -> tuple[np.ndarray | None, np.ndarray | None]:
    """提取卡面上的图标本体并归一化。

    以卡片四边的中位色作为「卡面基色」，凡是与之色差显著的像素即图标。
    这样不依赖饱和度/明度阈值，白色药瓶、灰色锯子这类低饱和图标也能取到。
    """
    m = max(2, min(card.w, card.h) // 10)
    sub = img[card.y + m:card.y + card.h - m, card.x + m:card.x + card.w - m]
    if sub.size == 0 or sub.shape[0] < 6 or sub.shape[1] < 6:
        return None, None

    # 亮度还原：被遮挡的卡是被半透明黑幕压暗的（V 由 255 降到 153，即 ×0.6），
    # 卡面与图标的色差会同比压缩。若不先把亮度拉回来，固定的色差阈值
    # 会把暗卡图标漏掉——这正是「下层牌看起来不可识别」的真正原因。
    vmed = card.score if card.score >= 50 else _face_vmedian(
        img, card.x, card.y, card.w, card.h)
    if 50 <= vmed < 250:
        gain = min(255.0 / vmed, 2.4)
        sub = np.clip(sub.astype(np.float32) * gain, 0, 255).astype(np.uint8)

    border = np.concatenate([
        sub[0, :].reshape(-1, 3), sub[-1, :].reshape(-1, 3),
        sub[:, 0].reshape(-1, 3), sub[:, -1].reshape(-1, 3),
    ])
    base = np.median(border, axis=0)
    diff = np.linalg.norm(sub.astype(np.int16) - base.astype(np.int16), axis=2)
    mk = (diff > 45).astype(np.uint8) * 255
    mk = cv2.morphologyEx(mk, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mk, connectivity=8)
    if n <= 1:
        return None, None
    best = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    bx, by, bw, bh, area = stats[best]
    if area < 0.06 * sub.shape[0] * sub.shape[1]:
        return None, None
    pad = 2
    x1, y1 = max(0, bx - pad), max(0, by - pad)
    x2 = min(sub.shape[1], bx + bw + pad)
    y2 = min(sub.shape[0], by + bh + pad)
    patch = sub[y1:y2, x1:x2]
    if patch.size == 0:
        return None, None
    patch = cv2.resize(patch, (ICON_SIZE, ICON_SIZE), interpolation=cv2.INTER_AREA)
    # 灰度比对版：缩到 24px + 3x3 高斯，且【不做】直方图均衡。
    # 实测同一图标在牌面卡（39px）与槽位卡（49px）上，若都走 40px + equalizeHist，
    # NCC 只有 0.66 →「同类被判两类」，槽位记账立刻错乱（这是此前两次失败的根源）。
    # 根因是两边的重采样模糊程度不同，equalizeHist 又把这点差异放大成
    # 整体亮度分布差异。改用 24px + 轻模糊、不做均衡后，同类 NCC 升到 0.91~0.94。
    g = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (ICON_CMP, ICON_CMP), interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    return patch, g


def detect_cards(img: np.ndarray, board: tuple[int, int, int, int] | None = None) -> list[Card]:
    """检测棋盘内所有可见卡牌（含后排变暗卡）。"""
    if board is None:
        board = find_board(img)
    gx, gy, gw, gh = board
    ref_w = gw * 0.095          # 依棋盘宽度估算卡宽（仅作量级参考，实际尺寸自适应）

    roi = np.zeros(img.shape[:2], np.uint8)
    # 屏蔽棋盘顶部 HUD 与底部道具栏，只保留牌区
    # 下界取 0.72：木质槽位条带自棋盘约 0.73 处开始，若放宽到 0.80
    # 会把槽内已收集的牌误判为场上可点牌。
    roi[gy + int(gh * 0.12): gy + int(gh * 0.72),
        gx + int(gw * 0.03): gx + int(gw * 0.97)] = 255

    # 多个掩膜候选都用「等大」这一先验评估，取得分最高的那组卡牌
    best, best_score = [], -1e9
    for _name, m in _mask_candidates(img):
        picked, sc = _pick_cards(cv2.bitwise_and(m, roi), ref_w)
        if sc > best_score:
            best_score, best = sc, picked

    cards: list[Card] = []
    for x, y, w, h, _area in best:
        vmed = _face_vmedian(img, x, y, w, h)
        card = Card(x, y, w, h, bright=vmed >= 200, score=vmed)
        card.icon, card.icon_gray = _extract_icon(img, card)
        cards.append(card)

    _resolve_occlusion(cards)
    return cards


def _rank(card: Card) -> tuple[int, int]:
    """绘制前后序：亮卡在前；同亮度下 y 越大越靠前（后绘制覆盖前者）。"""
    return (1 if card.bright else 0, card.y)


def _resolve_occlusion(cards: list[Card]) -> None:
    """判定每张卡是否被其它卡遮挡；被遮挡即不可点击。

    该美术风格里「变暗」即表示被上层卡覆盖，因此暗卡一律视为不可点击，
    不必再依赖几何重叠推断（密集关卡中暗卡常只露出窄边，重叠比反而偏小）。
    """
    for c in cards:
        c.blocked = not c.bright
        c.block_by.clear()

    # 另外记录「每张暗卡被哪几张亮卡压着」。这只用于估算点击收益，
    # 不参与可点击判定——判定仍以亮暗为准，避免几何推断把亮卡误判为不可点。
    bright_idx = [i for i, c in enumerate(cards) if c.bright]
    for i, d in enumerate(cards):
        if d.bright:
            continue
        for j in bright_idx:
            if _overlap_ratio(d, cards[j]) > 0.12:
                d.block_by.append(j)


def _overlap_ratio(a: Card, b: Card) -> float:
    """b 覆盖了 a 的面积比例。"""
    ox = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    oy = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = ox * oy
    if inter <= 0:
        return 0.0
    return inter / max(1, a.w * a.h)


def coverage(cards: list[Card]) -> dict[int, int]:
    """每张亮卡压住了多少张暗卡。

    点击一张压住 4 张暗卡的牌，比点一张什么都没压的牌收益高得多——
    这是人类玩这类堆叠消除游戏的通用策略，且完全不依赖识别下层图案。
    """
    cov: dict[int, int] = {i: 0 for i, c in enumerate(cards) if c.bright}
    for c in cards:
        if c.bright:
            continue
        for j in c.block_by:
            if j in cov:
                cov[j] += 1
    return cov


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    """等尺寸图像的归一化互相关，返回 0~1。"""
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    a -= a.mean()
    b -= b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float((a * b).sum() / (na * nb))


def _hist_sim(a: np.ndarray, b: np.ndarray) -> float:
    ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0, 1], None, [24, 24], [0, 180, 0, 256])
    hb = cv2.calcHist([cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [0, 1], None, [24, 24], [0, 180, 0, 256])
    cv2.normalize(ha, ha); cv2.normalize(hb, hb)
    return float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))


class TypeRegistry:
    """跨帧稳定的图标类型编号。

    逐帧聚类的编号没有跨帧含义（帧 N 的 #0 与帧 N+1 的 #0 可能是不同图标），
    一旦用它记录槽位占用，「三张同图案消除」的推理就会失效并导致槽位溢出。
    因此这里维护一份进程内持久化的原型库：新图标追加编号，已有图标始终复用它。
    """

    def __init__(self, thr: float = NCC_SAME, hist_thr: float = 0.80):
        self.thr = thr
        self.hist_thr = hist_thr
        self.protos: list[dict] = []

    def _score(self, card: Card, p: dict) -> tuple[bool, float]:
        """判定卡与原型是否同种。

        单靠形状 NCC 不够：槽位卡与牌面卡的绘制比例/锐度不同，
        同一图标的 NCC 可能只有 0.79 而被误判为不同类（实测出现过 0.797）。
        因此补充一条「颜色组成几乎相同 + 形状中等相似」的判据，二者取或。
        """
        v = _ncc(card.icon_gray, p["gray"])
        h = _hist_sim(card.icon, p["color"])
        # 两种卡（牌面 39px / 槽位 49px）的同类 NCC 实测落在 0.71~0.94，
        # 单靠 0.80 会漏掉 0.7x 的那部分；辅以「颜色组成几乎相同」兜住。
        same = (v >= self.thr) or (v >= 0.70 and h >= 0.90)
        return same, v

    def _best(self, card: Card) -> tuple[float, int]:
        best, bid = 0.0, -1
        for i, p in enumerate(self.protos):
            v = _ncc(card.icon_gray, p["gray"])
            if v > best:
                best, bid = v, i
        return best, bid

    def _find(self, card: Card) -> int:
        """在所有原型中找同种编号；优先返回相似度最高者。"""
        cands: list[tuple[float, int]] = []
        for i, p in enumerate(self.protos):
            same, v = self._score(card, p)
            if same:
                cands.append((v, i))
        if not cands:
            return -1
        cands.sort(reverse=True)
        return cands[0][1]

    def assign(self, cards: list[Card]) -> int:
        for c in cards:
            c.ttype = -1

        # 亮卡图标完整，可用于建立新原型
        for c in sorted(cards, key=lambda x: (not x.bright, x.y, x.x)):
            if c.icon_gray is None:
                continue
            idx = self._find(c)
            if idx >= 0:
                c.ttype = idx
            elif c.bright:
                self.protos.append({"gray": c.icon_gray, "color": c.icon})
                c.ttype = len(self.protos) - 1

        # 暗卡图标常被截断，只允许匹配已有原型，不建立新类型
        for c in cards:
            if c.ttype != -1 or c.icon_gray is None:
                continue
            idx = self._find(c)
            if idx >= 0:
                c.ttype = idx

        return len(self.protos)

    def label(self, t: int) -> str:
        return f"T{t}" if 0 <= t < len(self.protos) else "?"


_DEFAULT_REGISTRY = TypeRegistry()


def assign_types(cards: list[Card], registry: "TypeRegistry | None" = None) -> int:
    """兼容旧签名；单帧分析时复用模块级注册表。"""
    reg = registry or _DEFAULT_REGISTRY
    return reg.assign(cards)


def analyze(img: np.ndarray) -> tuple[list[Card], tuple[int, int, int, int], int]:
    board = find_board(img)
    cards = detect_cards(img, board)
    ntypes = assign_types(cards)
    return cards, board, ntypes


def read_slots(img: np.ndarray, board: tuple[int, int, int, int],
               registry: "TypeRegistry") -> tuple[dict[int, int], int]:
    """读取底部槽位已占用的卡，返回 ({类型编号: 张数}, 未识别张数)。

    槽内卡图标完整可见，因此允许它们为注册表补充新原型——这解决了
    「槽里的图案当前牌面上已不存在」导致无法归类的问题，也是跨次运行
    恢复槽位模型的前提。
    """
    gx, gy, gw, gh = board
    y1 = gy + int(gh * 0.70)
    y2 = gy + int(gh * 0.92)
    strip = img[y1:y2, gx:gx + gw].copy()
    if strip.size == 0:
        return {}, 0

    ref_w = gw * 0.095
    picked, _sc = _pick_cards(_face_mask(strip, ref_w), ref_w)
    out: dict[int, int] = {}
    unknown = 0
    for x, y, w, h, _area in picked:
        if w / max(1, h) < 0.65 or w / max(1, h) > 1.55:
            continue
        card = Card(x, y, w, h, bright=True)
        card.icon, card.icon_gray = _extract_icon(strip, card)
        if card.icon_gray is None:
            unknown += 1
            continue
        registry.assign([card])
        if card.ttype >= 0:
            out[card.ttype] = out.get(card.ttype, 0) + 1
        else:
            unknown += 1
    return out, unknown
