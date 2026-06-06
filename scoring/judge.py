"""
结算系统。

判定规则（按优先级）：
1. 选择公共骰子的玩家在平局时单独获胜
2. 点数 = 13 获胜
3. 均 < 13 则最大点数获胜
4. > 13 出局（如果场上还有 ≤13 的玩家），全员 >13 则最小点数获胜
5. 获胜者获得全部奖金，多人平局则平分
"""

from __future__ import annotations

from models.player import Player

TARGET = 13


class ShowdownResult:
    """结算结果。"""

    def __init__(self, winners: list[Player], pot: int):
        self.winners = winners
        self.pot = pot
        self.prize_per_winner = pot // len(winners) if winners else 0

    def distribute(self):
        """分配奖金给获胜者。"""
        for w in self.winners:
            w.money += self.prize_per_winner


def judge(players: list[Player], pot: int) -> ShowdownResult:
    """
    判定胜负。

    参数：
        players: 所有未弃牌玩家列表
        pot: 奖池总额

    返回：ShowdownResult（包含获胜者列表和每人奖金）
    """
    active = [p for p in players if not p.folded]

    if not active:
        return ShowdownResult([], pot)

    if len(active) == 1:
        return ShowdownResult([active[0]], pot)

    # 计算每人得分
    scores: dict[Player, int] = {}
    for p in active:
        score = sum(p.hand)
        if p.public_die is not None:
            score += p.public_die
        scores[p] = score

    # 分类玩家
    perfect = [p for p in active if scores[p] == TARGET]
    under = [p for p in active if scores[p] < TARGET]
    over = [p for p in active if scores[p] > TARGET]

    # 规则 2：有人恰好 =13
    if perfect:
        return _resolve_tie(perfect, pot)

    # 规则 3：全部 <13
    if under and not over:
        max_score = max(scores[p] for p in under)
        candidates = [p for p in under if scores[p] == max_score]
        return _resolve_tie(candidates, pot)

    # 规则 4：有人 >13，且有人 ≤13
    if under:
        # 有 ≤13 的玩家，>13 的出局
        max_score = max(scores[p] for p in under)
        candidates = [p for p in under if scores[p] == max_score]
        return _resolve_tie(candidates, pot)

    # 全员 >13：最小点数获胜
    min_score = min(scores[p] for p in over)
    candidates = [p for p in over if scores[p] == min_score]
    return _resolve_tie(candidates, pot)


def _resolve_tie(candidates: list[Player], pot: int) -> ShowdownResult:
    """
    平局处理。
    规则 1：选择了公共骰子的玩家在平局时单独获胜。
    """
    if len(candidates) == 1:
        return ShowdownResult(candidates, pot)

    # 选择公共骰子的玩家单独获胜
    public_choosers = [p for p in candidates if p.chose_public]
    if public_choosers:
        return ShowdownResult(public_choosers, pot)

    # 均分
    return ShowdownResult(candidates, pot)
