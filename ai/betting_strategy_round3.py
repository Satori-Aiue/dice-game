"""
第三轮下注策略。

此时已知：自己的 2 颗暗骰 + 公共骰子点数 + 所有人的公开骰子。
自己的最终点数已确定，可以精确推断对手得分分布。

实现框架：
1. 贝叶斯推断对手分布——由明骰 + 第二轮规则（≤9 加入公共骰）推断
   每位对手的 P(score, chose_public | revealed_die, public_die)
2. Monte Carlo——采样对手分布，模拟 showdown，估计真实桌面胜率 P(win)
3. 期望效用——EU = P(win) × pot − (1−P(win)) × call × (1+α)
   α 修改效用函数而非胜率：保守型玩家对损失的感知被放大
4. 基于 EU 决定弃牌（EU<0）、跟注、或加注（EU 足够高时按 P(win) 决定加注额）
"""

from __future__ import annotations

import random

from .strategy import (
    MIN_RAISE,
    BetAction,
    BetActionType,
)
from .probability import TARGET

# ---- 贝叶斯推断参数 ----
RULE_ADHERENCE = 0.95     # 对手遵循"≤9 加入公共骰"规则的概率（5% 可能偏离）

# ---- Monte Carlo 参数 ----
MC_SIMULATIONS = 500       # Monte Carlo 模拟次数

# ---- 资金投入上限 ----
MAX_BET_FRAC = 0.35        # 最强牌最多投入总可支配资金的 35%（第三轮信息充分，可适度提高）
RAISE_MIN_MULT = 3          # 每次加注至少是 MIN_RAISE 的 3 倍（加速收敛，避免小步循环）

# ---- 决策阈值 ----
EU_FOLD_FRAC = -0.08       # EU / money < 此值 → 弃牌
P_WIN_RAISE = 0.55         # P(win) > 此值 → 考虑加注
P_WIN_HOPELESS = 0.02      # P(win) < 此值 → 绝望手，即使 to_call=0 也弃牌


def build_opponent_distribution(revealed_die: int, public_die: int) -> list[tuple[int, bool, float]]:
    """
    贝叶斯推断对手的 (score, chose_public) 概率分布。

    已知对手公开骰 r，枚举暗骰 h ∈ [2,7]（均匀先验 1/6），
    利用第二轮规则做软推断（允许对手以 5% 概率偏离规则）：
    - r+h ≤ 9 → P(加入) = 0.95, P(不加入) = 0.05
    - r+h > 9 → P(加入) = 0.05, P(不加入) = 0.95

    返回列表，每个元素为 (score, chose_public, probability)，概率和为 1。

    参数：
        revealed_die: 对手公开的骰子点数
        public_die: 公共骰子点数
    """
    outcomes: list[tuple[int, bool, float]] = []
    for hidden in range(2, 8):
        two_sum = revealed_die + hidden
        joins_by_rule = (two_sum <= 9)
        base_prob = 1.0 / 6  # 均匀先验

        if joins_by_rule:
            p_join = RULE_ADHERENCE
            p_not = 1.0 - RULE_ADHERENCE
        else:
            p_join = 1.0 - RULE_ADHERENCE
            p_not = RULE_ADHERENCE

        if p_join > 0:
            score_with = two_sum + public_die
            outcomes.append((score_with, True, base_prob * p_join))
        if p_not > 0:
            score_without = two_sum
            outcomes.append((score_without, False, base_prob * p_not))
    return outcomes


def judge_one_vs_one(my_score: int, my_public: bool,
                     opp_score: int, opp_public: bool) -> int:
    """
    两人比点。返回 1（我赢）、-1（我输）、0（平局）。

    遵循游戏结算规则：
    1. 13 点 > 一切
    2. 均 < 13 → 高分赢
    3. 有人爆牌 → 未爆者赢；均爆牌 → 低分赢
    4. 平局 → 选公共骰者赢，否则真平
    """
    my_13 = (my_score == TARGET)
    opp_13 = (opp_score == TARGET)
    my_bust = (my_score > TARGET)
    opp_bust = (opp_score > TARGET)

    # 13 点优先
    if my_13 and not opp_13:
        return 1
    if opp_13 and not my_13:
        return -1
    if my_13 and opp_13:
        if my_public and not opp_public:
            return 1
        if opp_public and not my_public:
            return -1
        return 0

    # 爆牌处理
    if my_bust and opp_bust:
        if my_score < opp_score:
            return 1
        if opp_score < my_score:
            return -1
        if my_public and not opp_public:
            return 1
        if opp_public and not my_public:
            return -1
        return 0

    if my_bust and not opp_bust:
        return -1
    if opp_bust and not my_bust:
        return 1

    # 均 < 13：高分赢，同分平局裁决
    if my_score > opp_score:
        return 1
    if opp_score > my_score:
        return -1
    if my_public and not opp_public:
        return 1
    if opp_public and not my_public:
        return -1
    return 0


def monte_carlo_win_probability(
    my_score: int, my_public: bool,
    opponent_dists: list[list[tuple[int, bool, float]]],
    n_sim: int = MC_SIMULATIONS,
) -> float:
    """
    Monte Carlo 估计真实桌面胜率：P(击败所有对手)。

    每次模拟：
    1. 从每个对手的分布中采样一个 (score, chose_public)
    2. 模拟 showdown：我是否击败所有对手
    3. 统计获胜次数

    参数：
        my_score: 我的最终得分
        my_public: 我是否选了公共骰
        opponent_dists: 每个对手的分布列表
        n_sim: 模拟次数
    """
    if not opponent_dists:
        return 1.0

    # 预处理：为每个对手构建累积概率表（加速采样）
    opp_tables = []
    for dist in opponent_dists:
        scores = []
        publics = []
        cumsum = []
        total = 0.0
        for score, pub, prob in dist:
            scores.append(score)
            publics.append(pub)
            total += prob
            cumsum.append(total)
        # 归一化
        opp_tables.append((scores, publics, [c / total for c in cumsum]))

    wins = 0
    for _ in range(n_sim):
        all_beat = True
        for scores, publics, cumsum in opp_tables:
            # 采样
            r = random.random()
            idx = 0
            for i, c in enumerate(cumsum):
                if r <= c:
                    idx = i
                    break
            opp_score = scores[idx]
            opp_public = publics[idx]

            result = judge_one_vs_one(my_score, my_public, opp_score, opp_public)
            if result != 1:
                # 没有击败这个对手（输了或平了且平局不利）
                all_beat = False
                break

        if all_beat:
            wins += 1

    return wins / n_sim


def risk_adjusted_eu(p_win: float, pot: int, to_call: int, risk_aversion: float) -> float:
    """
    风险调整后的期望效用。

    标准 EV = P(win) × pot_gain − P(lose) × call_cost
    其中 pot_gain = pot + to_call（跟注后奖池扩大），call_cost = to_call

    风险调整：保守型玩家（高 α）对损失的感知被放大。
    EU = P(win) × (pot + to_call) − (1 − P(win)) × to_call × (1 + α)

    α 作用于损失项，不影响 P(win) 本身：
    - α ≈ 0（激进）：损失感知接近真实值 → EU ≈ 标准 EV
    - α ≈ 0.5（保守）：损失被放大 1.5 倍 → 需要更高胜率才愿意跟注

    参数：
        p_win: Monte Carlo 估计的真实桌面胜率
        pot: 当前奖池（跟注前）
        to_call: 需要跟注的金额
        risk_aversion: 爆牌厌恶度 α
    """
    p_lose = 1.0 - p_win
    gain = pot + to_call
    loss = to_call * (1.0 + risk_aversion)
    return p_win * gain - p_lose * loss


def decide_third_bet(
    hand: list[int],
    has_public: bool,
    public_die: int | None,
    revealed_dice: dict[str, int],
    current_bet: int,
    my_current_bet: int,
    pot: int,
    money: int,
    max_allowed: int,
    risk_aversion: float = 0.30,
    opponent_moneys: list[int] | None = None,
) -> BetAction:
    """
    第三轮下注决策——基于 Monte Carlo 胜率 + 风险调整期望效用。

    框架：
    1. 贝叶斯推断每位对手的 (score, chose_public) 分布
    2. Monte Carlo 估计真实桌面胜率 P(击败所有对手)
    3. 计算风险调整期望效用 EU
    4. EU < 0 → 弃牌；否则跟注；P(win) 足够高时加注

    参数：
        hand: 暗骰点数列表（2 颗）
        has_public: 是否选择了公共骰子
        public_die: 公共骰子点数（如有，None 表示未选公共骰）
        revealed_dice: {对手名称: 公开骰点数}
        current_bet: 当前轮最高下注额
        my_current_bet: 我本轮已下注额
        pot: 当前奖池总额
        money: 我的剩余资金
        max_allowed: 本轮下注上限（all-in 规则）
        risk_aversion: 爆牌厌恶度 α ∈ [0.05, 0.55]
        opponent_moneys: 其他存活对手的剩余资金列表（未使用，保留兼容）
    """
    # 计算自己的最终得分
    score = sum(hand)
    if public_die is not None and has_public:
        score += public_die

    # ---- 步骤 1：贝叶斯推断对手分布 ----
    opponent_dists = []
    for opp_name, revealed_die in revealed_dice.items():
        dist = build_opponent_distribution(revealed_die, public_die if public_die is not None else 0)
        opponent_dists.append(dist)

    # ---- 步骤 2：Monte Carlo 桌面胜率 ----
    p_win = monte_carlo_win_probability(score, has_public, opponent_dists)

    remaining_cap = max_allowed - my_current_bet
    to_call = current_bet - my_current_bet

    # ---- 步骤 3：风险调整期望效用 ----
    eu = risk_adjusted_eu(p_win, pot, max(to_call, 0), risk_aversion)

    # ---- 步骤 4：决策 ----

    # 已等额，考虑加注
    if to_call <= 0:
        # 绝望手：即使不需要跟注也主动弃牌，避免后续被加注套牢
        if p_win < P_WIN_HOPELESS:
            return BetAction(BetActionType.FOLD, 0)
        if p_win >= P_WIN_RAISE and remaining_cap >= MIN_RAISE:
            # 加注金额基于 P(win)：胜率越高，加注越多
            # excess: [P_WIN_RAISE, 1.0] → [0, 1]
            if p_win >= 1.0:
                raise_frac = 1.0
            else:
                raise_frac = (p_win - P_WIN_RAISE) / (1.0 - P_WIN_RAISE)
            total_available = money + my_current_bet
            target_bet = int(total_available * raise_frac * MAX_BET_FRAC)
            target_bet = max(target_bet, my_current_bet + MIN_RAISE * RAISE_MIN_MULT)

            if my_current_bet < target_bet and target_bet - my_current_bet >= MIN_RAISE:
                raise_amt = min(target_bet - my_current_bet, remaining_cap)
                if raise_amt >= MIN_RAISE:
                    return BetAction(BetActionType.RAISE, raise_amt)
        return BetAction(BetActionType.CALL, 0)

    # 需要跟注追赶
    if to_call > money or to_call > remaining_cap:
        # 被迫 all-in 或弃牌——用 EU 判断
        if eu >= 0:
            return BetAction(BetActionType.CALL, min(to_call, money, remaining_cap))
        return BetAction(BetActionType.FOLD, 0)

    # 绝望手
    if p_win < P_WIN_HOPELESS:
        return BetAction(BetActionType.FOLD, 0)

    # EU 判断
    if eu < 0:
        return BetAction(BetActionType.FOLD, 0)

    # 跟注 + 可能加注
    if p_win >= P_WIN_RAISE and remaining_cap > to_call + MIN_RAISE:
        if p_win >= 1.0:
            raise_frac = 1.0
        else:
            raise_frac = (p_win - P_WIN_RAISE) / (1.0 - P_WIN_RAISE)
        total_available = money + my_current_bet
        target_bet = int(total_available * raise_frac * MAX_BET_FRAC)
        after_call = my_current_bet + to_call
        target_bet = max(target_bet, after_call + MIN_RAISE * RAISE_MIN_MULT)

        if after_call < target_bet:
            raise_amt = min(target_bet - after_call, remaining_cap - to_call)
            if raise_amt >= MIN_RAISE:
                return BetAction(BetActionType.RAISE, raise_amt)

    return BetAction(BetActionType.CALL, to_call)
