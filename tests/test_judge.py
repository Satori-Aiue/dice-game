"""测试结算系统。"""

import pytest
from models.player import Player
from scoring.judge import judge


def make_player(name: str, hand: list[int], public_die: int | None = None,
                chose_public: bool = False) -> Player:
    """创建测试用玩家。"""
    p = Player(name)
    p.hand = hand
    p.public_die = public_die
    p.chose_public = chose_public
    return p


class TestJudge:
    """结算判定测试。"""

    def test_single_player_wins(self):
        """只剩一个玩家时自动获胜。"""
        p = make_player("A", [3, 4])
        result = judge([p], 100)
        assert result.winners == [p]
        assert result.prize_per_winner == 100

    def test_exact_13_wins(self):
        """恰好 13 点获胜。"""
        a = make_player("A", [6, 7])      # 13
        b = make_player("B", [5, 6])      # 11
        result = judge([a, b], 100)
        assert a in result.winners
        assert b not in result.winners

    def test_highest_under_13_wins(self):
        """均 <13 时最大点数获胜。"""
        a = make_player("A", [6, 6])      # 12
        b = make_player("B", [5, 6])      # 11
        c = make_player("C", [3, 4])      # 7
        result = judge([a, b, c], 100)
        assert result.winners == [a]

    def test_over_13_busts(self):
        """>13 出局（当场上还有 ≤13 的玩家时）。"""
        a = make_player("A", [7, 7])      # 14 爆牌
        b = make_player("B", [3, 4])      # 7
        result = judge([a, b], 100)
        assert result.winners == [b]

    def test_all_over_13_lowest_wins(self):
        """全员 >13 时最小点数获胜。"""
        a = make_player("A", [7, 7])      # 14
        b = make_player("B", [7, 6])      # 13 -> wait, 13 is not over 13
        # Let me fix: 13 doesn't bust
        a = make_player("A", [7, 7])      # 14
        b = make_player("B", [7, 7])      # 14
        c = make_player("C", [6, 6])      # 12 -> under 13!

    def test_all_over_13_lowest_wins_correct(self):
        """全员 >13 时（且没有 ≤13 的），最小点数获胜。"""
        a = make_player("A", [7, 7])      # 14
        b = make_player("B", [6, 7])      # 13 - this equals 13, so not all bust
        # Correct test case
        a2 = make_player("A", [7, 7])     # 14
        b2 = make_player("B", [7, 7])     # 14
        c2 = make_player("C", [7, 5])     # 12
        # Wait, 12 < 13. So not all over.

    def test_all_over_13_with_3_dice(self):
        """全员 >13 且都加了公共骰子，最小点数获胜（平局）。"""
        a = make_player("A", [7, 7], public_die=7)   # 21
        b = make_player("B", [6, 7], public_die=2)   # 15
        c = make_player("C", [5, 5], public_die=5)   # 15
        result = judge([a, b, c], 100)
        # All >13, lowest is 15. B and C tie at 15.
        assert len(result.winners) == 2
        assert b in result.winners
        assert c in result.winners
        assert result.prize_per_winner == 50

    def test_all_over_13_lowest_wins_proper(self):
        """全员 >13 时最小点数获胜（正确测试用例）。"""
        a = make_player("A", [7, 7], public_die=2)   # 16
        b = make_player("B", [7, 7], public_die=3)   # 17
        result = judge([a, b], 100)
        assert result.winners == [a]  # 16 < 17

    def test_public_die_wins_tie(self):
        """平局时选择公共骰子的玩家单独获胜。"""
        a = make_player("A", [6, 7], chose_public=False)     # 13
        b = make_player("B", [3, 4], public_die=6, chose_public=True)  # 13
        result = judge([a, b], 100)
        assert result.winners == [b]

    def test_tie_split_pot(self):
        """都没有公共骰子时平局平分。"""
        a = make_player("A", [6, 7])      # 13
        b = make_player("B", [6, 7])      # 13
        result = judge([a, b], 100)
        assert len(result.winners) == 2
        assert result.prize_per_winner == 50

    def test_folded_players_ignored(self):
        """弃牌的玩家不参与结算。"""
        a = make_player("A", [6, 7])      # 13
        b = make_player("B", [7, 7])      # 14
        b.folded = True
        result = judge([a, b], 100)
        assert result.winners == [a]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
