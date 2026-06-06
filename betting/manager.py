"""
下注管理器。

负责：
- 等额校验：所有人下注额必须相等才能进入下一阶段
- 循环加注：当前玩家可以加注，下一位必须跟注/弃牌/再加注
- All-in 规则：资金最少者 all-in 时，该金额成为上限
- 弃牌结算：弃牌者失去已投入资金
"""

from __future__ import annotations

from models.player import Player
from models.pot import Pot

MIN_BET = 5


class BettingRound:
    """
    单次下注轮：从当前下注额开始，轮询玩家直到所有人等额或全部弃牌。
    """

    def __init__(
        self,
        players: list[Player],
        pot: Pot,
        start_player_idx: int = 0,
        can_fold: bool = True,
    ):
        self._players = [p for p in players if not p.folded]
        self._pot = pot
        self._can_fold = can_fold
        self._current_bet: int = 0  # 本轮当前最高下注额
        self._current_player_idx = start_player_idx % max(len(self._players), 1)

    @property
    def current_bet(self) -> int:
        return self._current_bet

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self._players if not p.folded]

    def get_bet_cap(self) -> int | None:
        """
        返回下注上限（All-in 规则）。
        资金最少者如果押上全部资金，该金额成为上限；否则无上限。
        """
        active = self.active_players
        if not active:
            return None
        min_money = min(p.money for p in active)
        # 检查资金最少者是否在当前轮已 all-in
        for p in active:
            if p.money == 0 and p.current_bet > 0:
                return p.current_bet
        return None

    def is_balanced(self) -> bool:
        """所有未弃牌玩家下注额是否相同。"""
        active = self.active_players
        if len(active) <= 1:
            return True
        bets = {p.current_bet for p in active}
        return len(bets) == 1

    def resolve_player_action(self, player: Player, action, to_call: int) -> int:
        """
        执行玩家的下注动作，返回实际支付的金额。
        """
        if action.type.name == "FOLD":
            if self._can_fold:
                player.folded = True
                return 0
            # 不能弃牌时强制跟注
            actual = player.place_bet(to_call)
            self._pot.collect(actual)
            if player.current_bet > self._current_bet:
                self._current_bet = player.current_bet
            return actual

        elif action.type.name == "CALL":
            actual = player.place_bet(to_call)
            self._pot.collect(actual)
            return actual

        elif action.type.name == "RAISE":
            # 先跟注再加注
            call_actual = player.place_bet(to_call)
            self._pot.collect(call_actual)
            raise_actual = player.place_bet(action.amount)
            self._pot.collect(raise_actual)

            cap = self.get_bet_cap()
            effective_bet = player.current_bet
            if cap is not None:
                effective_bet = min(effective_bet, cap)

            if effective_bet > self._current_bet:
                self._current_bet = effective_bet
            return call_actual + raise_actual

        return 0
