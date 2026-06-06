"""测试下注系统。"""

import pytest
from models.player import Player
from models.pot import Pot
from betting.manager import BettingRound, MIN_BET


class TestBettingRound:
    """下注轮测试。"""

    def test_all_equal_balanced(self):
        """所有人等额时直接通过。"""
        players = [Player("A"), Player("B")]
        pot = Pot()
        for p in players:
            p.place_bet(10)
            pot.collect(10)
        br = BettingRound(players, pot)
        assert br.is_balanced()

    def test_not_balanced(self):
        """不等额时未通过。"""
        players = [Player("A"), Player("B")]
        pot = Pot()
        players[0].place_bet(10)
        players[1].place_bet(5)
        br = BettingRound(players, pot)
        assert not br.is_balanced()

    def test_one_player_balanced(self):
        """只剩一个玩家时通过。"""
        players = [Player("A")]
        pot = Pot()
        br = BettingRound(players, pot)
        assert br.is_balanced()

    def test_fold_removes_player(self):
        """弃牌后玩家不再活跃。"""
        players = [Player("A"), Player("B")]
        pot = Pot()
        players[0].place_bet(10)
        players[0].folded = True
        br = BettingRound(players, pot)
        assert len(br.active_players) == 1

    def test_bet_cap_all_in(self):
        """All-in 上限检测。"""
        players = [Player("A", money=10), Player("B", money=100)]
        pot = Pot()
        players[0].place_bet(10)  # All-in
        players[1].place_bet(20)
        br = BettingRound(players, pot)
        # After all-in, cap should be the all-in player's bet
        cap = br.get_bet_cap()
        assert cap == 10


class TestPlayerBetting:
    """玩家下注测试。"""

    def test_place_bet_reduces_money(self):
        """下注减少资金。"""
        p = Player("A", money=100)
        actual = p.place_bet(30)
        assert actual == 30
        assert p.money == 70
        assert p.current_bet == 30

    def test_place_bet_capped_by_money(self):
        """下注不能超过资金。"""
        p = Player("A", money=10)
        actual = p.place_bet(30)
        assert actual == 10
        assert p.money == 0
        assert p.current_bet == 10

    def test_reset_for_round(self):
        """reset 清空所有轮内状态。"""
        p = Player("A", money=100)
        p.hand = [3, 4]
        p.public_die = 5
        p.chose_public = True
        p.revealed_die = 4
        p.current_bet = 20
        p.folded = True
        p.money = 80

        p.reset_for_round()
        assert p.hand == []
        assert p.public_die is None
        assert p.chose_public is False
        assert p.revealed_die is None
        assert p.current_bet == 0
        assert p.folded is False
        assert p.money == 80  # money persists


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
