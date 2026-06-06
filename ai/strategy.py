"""
AI 策略模块。

基于概率计算做出理性决策：手牌评估 → EV 估算 → 下注/弃牌。

第二轮和第三轮的下注策略已拆分到独立文件：
- betting_strategy_round2.py — 公共骰子选择 + 第二轮下注
- betting_strategy_round3.py — 第三轮下注
"""

from __future__ import annotations

import random
from enum import Enum

from .probability import TARGET

MIN_BET = 5       # 第一轮必须下注金额
MIN_RAISE = 6     # 加注最小单位（每次追下注至少为 5+1 元）


class BetActionType(Enum):
    FOLD = "fold"
    CALL = "call"
    RAISE = "raise"


class BetAction:
    """下注动作。"""
    def __init__(self, action: BetActionType, amount: int = 0):
        self.type = action
        self.amount = amount

    def __repr__(self):
        if self.type == BetActionType.RAISE:
            return f"Raise(+${self.amount})"
        return self.type.value.capitalize()


def evaluate_hand_strength(hand: list[int], has_public: bool, public_die: int | None = None) -> float:
    """
    评估手牌强度，返回 [0, 1] 区间的值。
    1.0 = 完美（恰好 13 且有公共骰子），0.0 = 最差。
    """
    if not hand:
        return 0.0

    score = sum(hand)
    if public_die is not None:
        score += public_die

    if score == TARGET:
        return 0.95 if has_public else 0.85

    if score > TARGET:
        # 爆牌。如果全员可能爆牌则还有微弱希望。
        return 0.05

    # score < TARGET
    distance = TARGET - score
    # 距离越大越弱。最大距离：TARGET - 4 = 9（2 骰最小 4）
    max_dist = 9
    strength = 1.0 - (distance / max_dist)
    # 有公共骰子略微加分（平局优势）
    if has_public:
        strength = min(1.0, strength + 0.05)
    return max(0.0, min(1.0, strength))


def decide_first_bet(hand: list[int], money: int, max_allowed: int) -> int:
    """
    第一轮下注决策：必须下注 5 元（流程规定）。
    受 max_allowed_bet 限制（最小资金玩家总资金）。
    """
    return min(MIN_BET, money, max_allowed)


def choose_reveal_die(hand: list[int]) -> int:
    """
    选择公开哪颗骰子。
    流程规定：随机选择一枚骰子公开。
    """
    return random.choice(hand)
