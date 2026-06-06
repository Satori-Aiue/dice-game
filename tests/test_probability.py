"""测试概率计算工具。"""

import pytest
from ai.probability import (
    TARGET,
    TWO_DICE_TOTAL,
    THREE_DICE_TOTAL,
    prob_two_dice,
    prob_three_dice,
    prob_two_dice_less_than,
    prob_two_dice_greater_than,
    prob_three_dice_given_two,
    expected_three_dice_sum,
)


class TestProbability:
    """概率计算测试。"""

    def test_total_combinations(self):
        """2 骰 36 种组合，3 骰 216 种组合。"""
        assert TWO_DICE_TOTAL == 36
        assert THREE_DICE_TOTAL == 216

    def test_prob_two_dice_sum(self):
        """2 骰和分布校验。"""
        # 最小和是 4（2+2），最大是 14（7+7）
        assert prob_two_dice(4) == 1/36   # (2,2)
        assert prob_two_dice(14) == 1/36  # (7,7)
        assert prob_two_dice(9) > prob_two_dice(4)  # 中间值概率更高

    def test_all_probabilities_sum_to_one(self):
        """所有概率和为 1。"""
        total = sum(prob_two_dice(s) for s in range(4, 15))
        assert abs(total - 1.0) < 0.0001

    def test_prob_less_than_target(self):
        """小于 13 的概率。"""
        p = prob_two_dice_less_than(TARGET)
        # 只有 (6,7)/(7,6)/(7,7) 不满足，即 3/36
        assert abs(p - 33/36) < 0.0001

    def test_prob_greater_than_target(self):
        """大于 13 的概率只有 (7,7)。"""
        p = prob_two_dice_greater_than(TARGET)
        assert abs(p - 1/36) < 0.0001

    def test_prob_three_dice_given_two(self):
        """已知 2 骰和，加入第 3 骰后的条件概率。"""
        # 2 骰和 = 7，要恰好 13，需要第 3 骰 = 6
        p = prob_three_dice_given_two(7, "equals", TARGET)
        assert abs(p - 1/6) < 0.0001

        # 2 骰和 = 7，要 >13，需要第 3 骰 = 7
        p = prob_three_dice_given_two(7, "greater", TARGET)
        assert abs(p - 1/6) < 0.0001

        # 2 骰和 = 7，要 <13，需要第 3 骰 ∈ {2,3,4,5}
        p = prob_three_dice_given_two(7, "less", TARGET)
        assert abs(p - 4/6) < 0.0001

    def test_expected_three_dice_sum(self):
        """第 3 骰期望值为 4.5。"""
        assert expected_three_dice_sum(7) == 11.5
        assert expected_three_dice_sum(10) == 14.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
