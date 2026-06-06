"""
第二轮下注策略。

包含：
- decide_public_die：是否加入公共骰子
- build_score_distribution：构建自身最终点数概率分布
- compute_hand_strength：基于概率分布统计量的牌力评估
- decide_second_bet：基于 HandStrength 决定跟注/加注/弃牌

核心思路（来自 第二轮加注策略.md）：
第二轮是不完全信息决策——不知道对手手牌、对手是否加入公共骰、公共骰结果。
因此不应估算对局胜率，而应视作纯粹的"自身牌力评估问题"。

实现框架：
1. 构建完整概率分布（枚举第三骰 2~7，各 1/6 概率）
2. 提取关键统计量：P(恰好 13)、P(安全区)、P(爆牌)、安全区期望分数、方差
3. 加权组合为统一的 HandStrength
"""

from __future__ import annotations

import math

from .strategy import (
    MIN_RAISE,
    BetAction,
    BetActionType,
)
from .probability import TARGET

# 骰子面值
FACES = list(range(2, 8))  # [2, 3, 4, 5, 6, 7]

# ---- 决策阈值 ----
FOLD_THRESHOLD = 0.35      # HandStrength 低于此值 → 弃牌
RAISE_THRESHOLD = 0.75     # HandStrength 高于此值 → 加注
# 二者之间 → 跟注

# ---- 资金投入上限 ----
# 保守原则：加注过多会吓跑点数一般的对手，降低整体收益。
# 点数好（strength 高）→ 跟得多；点数差（strength 低）→ 跟得少。
# 但即使最强牌也不应投入过多：上限为总可支配资金的 20%。
MAX_BET_FRAC = 0.20        # strength=1.0 时的最大投入比例

# ---- HandStrength 权重 ----
# 13 点几乎是自动胜利，权重最高。安全区（<13）次之，分数越接近 13 越好。
# 爆牌区（>13）仅在全員爆牌时有机会，价值极小。
# 使用乘法复合公式避免加法权重之间的张力。
# 非线性指数 POW_UNDER 使离 13 近的分数获得不成比例的高价值。
POW_UNDER = 3               # 安全区质量 = (exp_safe/13)^POW_UNDER
BUST_BASE = 0.04            # 爆牌区最大残余价值


def decide_public_die(hand: list[int], money: int, current_bet: int, pot: int) -> bool:
    """
    决定是否加入第三颗公共骰子。

    当前策略：2 骰和 ≤ 9 → 加入，> 9 → 不加入。

    参数：
        hand: 暗骰点数列表（2 颗）
        money: 剩余资金
        current_bet: 本轮已下注额
        pot: 当前奖池总额
    """
    return sum(hand) <= 9


def build_score_distribution(hand: list[int], has_public: bool) -> dict[int, float]:
    """
    构建自身最终点数的完整概率分布。

    无公共骰：分布为单点 {score: 1.0}
    有公共骰：枚举第三骰 2~7（均匀分布，各 1/6），得到 6 种可能得分的概率分布。

    返回：{score: probability}，所有 probability 之和为 1.0。

    参数：
        hand: 暗骰点数列表（2 颗）
        has_public: 是否已选择加入公共骰子
    """
    two_sum = sum(hand)

    if not has_public:
        return {two_sum: 1.0}

    dist: dict[int, float] = {}
    for d in FACES:
        score = two_sum + d
        dist[score] = dist.get(score, 0.0) + 1.0 / len(FACES)
    return dist


def compute_hand_strength(hand: list[int], has_public: bool, risk_aversion: float = 0.30) -> float:
    """
    基于自身点数概率分布统计量计算手牌强度。

    返回 [0, 1]，1.0 = 最佳（恰好 13），0.0 = 最差。

    算法分三步：
    1. 构建最终点数的完整概率分布
    2. 提取三个区域的统计量：
       - 13 区：P(恰好 13)
       - 安全区（<13）：P(安全)、期望分数、分数质量
       - 爆牌区（>13）：P(爆牌)、期望分数
    3. 乘法复合 + 风险惩罚：
       base = value_13 + (1 - value_13) × (value_safe + value_bust)
       bust_penalty = risk_aversion × P(bust)
       strength = base - bust_penalty

    risk_aversion ∈ [0, 0.6] 控制对爆牌的敏感程度：
      0.0 = 激进型（无视爆牌风险）
      0.3 = 中性（默认）
      0.6 = 保守型（对爆牌极度敏感，倾向于弃牌/跟注而非加注）

    参数：
        hand: 暗骰点数列表（2 颗）
        has_public: 是否已选择加入公共骰子
        risk_aversion: 爆牌厌恶度 [0, 0.6]
    """
    dist = build_score_distribution(hand, has_public)

    # ---- 提取统计量 ----
    p_13 = dist.get(TARGET, 0.0)

    # 安全区（< 13）
    safe_scores = [(s, p) for s, p in dist.items() if s < TARGET]
    p_safe = sum(p for _, p in safe_scores)
    if p_safe > 0:
        exp_safe = sum(s * p for s, p in safe_scores) / p_safe
    else:
        exp_safe = 0.0

    # 爆牌区（> 13）
    bust_scores = [(s, p) for s, p in dist.items() if s > TARGET]
    p_bust = sum(p for _, p in bust_scores)
    if p_bust > 0:
        exp_bust = sum(s * p for s, p in bust_scores) / p_bust
    else:
        exp_bust = float('inf')

    # 整体统计量
    exp_all = sum(s * p for s, p in dist.items())
    var_all = sum((s - exp_all) ** 2 * p for s, p in dist.items())

    # ---- 加权组合（乘法复合公式） ----
    # 核心思路：13 点是独立的获胜路径，安全区是另一条路径。
    # 两条路径并非独立累加，而是：先看 13 点概率，剩余概率分配给安全区。
    #
    # strength = value_13 + (1 - value_13) × value_safe
    #
    # 这样保证了：
    #   - P(13)=1.0 → strength≈1.0（最高）
    #   - P(13)=0, 高分安全 → strength≈under_quality（中等）
    #   - 爆牌 → strength≈0（最低）

    # 13 区价值：P(13) × 平局优势
    tie_adv = 1.05 if has_public else 1.0
    value_13 = min(p_13 * tie_adv, 1.0)

    # 安全区价值：概率 × 分数质量（非线性幂函数，越接近 13 越好）
    # (score/13)^POW_UNDER 对高分给不成比例的奖励
    if p_safe > 0:
        under_quality = (exp_safe / TARGET) ** POW_UNDER
    else:
        under_quality = 0.0
    value_safe = p_safe * under_quality

    # 爆牌区价值：极低，仅考虑全員爆牌时"分数越低越好"的微弱可能
    if p_bust > 0 and exp_bust < float('inf'):
        value_bust = BUST_BASE * (TARGET / exp_bust)
    else:
        value_bust = 0.0

    # 乘法复合：先分配 13 路径，剩余部分分配安全/爆牌路径
    base_strength = value_13 + (1.0 - value_13) * (value_safe + value_bust)

    # 风险惩罚：爆牌概率 × 玩家风险厌恶度
    # 保守型玩家（高 α）对爆牌概率敏感，手牌估值大幅下调
    # 激进型玩家（低 α）几乎不受爆牌概率影响
    bust_penalty = risk_aversion * p_bust
    strength = base_strength - bust_penalty

    return max(0.0, min(1.0, strength))


def decide_second_bet(
    hand: list[int],
    has_public: bool,
    current_bet: int,
    my_current_bet: int,
    pot: int,
    money: int,
    max_allowed: int,
    risk_aversion: float = 0.30,
) -> BetAction:
    """
    第二轮下注决策：纯基于自身牌力（HandStrength）。

    决策逻辑：
    1. 计算 HandStrength
    2. 根据 strength 计算"目标总注额"（本 round 愿意投入的最大金额）
    3. strength < FOLD_THRESHOLD → 弃牌
    4. 当前注额已达目标 → 仅跟注，不加注
    5. 当前注额未达目标 → 加注至目标

    "目标注额"的概念确保了加注会自然收敛：
    HandStrength 越高 → 目标注额越高 → 愿意投入更多资金。
    一旦当前注额达到目标，就不再加注，避免无限循环。

    参数：
        hand: 暗骰点数列表（2 颗）
        has_public: 是否已选择加入公共骰子
        current_bet: 当前轮最高下注额
        my_current_bet: 我本轮已下注额
        pot: 当前奖池总额
        money: 我的剩余资金
        max_allowed: 本轮下注上限（all-in 规则）
    """
    strength = compute_hand_strength(hand, has_public, risk_aversion)
    remaining_cap = max_allowed - my_current_bet
    to_call = current_bet - my_current_bet

    # 计算目标总注额（本轮愿意投入的最大金额）
    # 保守原则：加注过大会吓跑对手 → 根据自身资金设定上限
    # target_frac: [FOLD_THRESHOLD, 1.0] → [0, 1.0]
    if strength <= FOLD_THRESHOLD:
        target_frac = 0.0
    else:
        target_frac = (strength - FOLD_THRESHOLD) / (1.0 - FOLD_THRESHOLD)
    total_available = money + my_current_bet  # 本轮最多可支配资金
    target_bet = int(total_available * target_frac * MAX_BET_FRAC)
    # 确保至少能跟注
    target_bet = max(target_bet, current_bet) if strength >= FOLD_THRESHOLD else target_bet

    # ---- 情况 1：已经等额，考虑加注 ----
    if to_call <= 0:
        if strength >= RAISE_THRESHOLD and my_current_bet < target_bet and remaining_cap >= MIN_RAISE:
            # 加注金额 = 目标注额 - 当前注额（至少 MIN_RAISE）
            raise_to_target = target_bet - my_current_bet
            raise_amt = max(MIN_RAISE, raise_to_target)
            raise_amt = min(raise_amt, remaining_cap)
            if raise_amt >= MIN_RAISE:
                return BetAction(BetActionType.RAISE, raise_amt)
        return BetAction(BetActionType.CALL, 0)

    # ---- 情况 2：需要跟注追赶 ----

    # 资金不足：被迫 all-in 或弃牌
    if to_call > money or to_call > remaining_cap:
        if strength >= FOLD_THRESHOLD:
            actual = min(to_call, money, remaining_cap)
            return BetAction(BetActionType.CALL, actual)
        return BetAction(BetActionType.FOLD, 0)

    # 弃牌判断：牌力太弱
    if strength < FOLD_THRESHOLD:
        return BetAction(BetActionType.FOLD, 0)

    # 跟注后判断是否加注
    if strength >= RAISE_THRESHOLD and remaining_cap > to_call + MIN_RAISE:
        # 跟注后能达到的注额
        after_call = my_current_bet + to_call
        if after_call < target_bet:
            raise_to_target = target_bet - after_call
            raise_amt = max(MIN_RAISE, raise_to_target)
            raise_amt = min(raise_amt, remaining_cap - to_call)
            if raise_amt >= MIN_RAISE:
                return BetAction(BetActionType.RAISE, raise_amt)

    return BetAction(BetActionType.CALL, to_call)
