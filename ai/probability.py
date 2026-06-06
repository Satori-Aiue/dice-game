"""
概率计算工具。

骰子范围 2-7（均匀分布），以下为核心分布：
- 单骰：期望 4.5
- 2 骰和：4-14，期望 9
- 3 骰和：6-21，期望 13.5
"""

import itertools
from collections import Counter

FACES = list(range(2, 8))  # [2, 3, 4, 5, 6, 7]
TARGET = 13


def _all_rolls(n: int) -> list[tuple[int, ...]]:
    """生成 n 颗骰子的所有可能组合（有序，用于概率计算）。"""
    return list(itertools.product(FACES, repeat=n))


# ---- 预先计算分布 ----

# 2 骰和分布：{sum: count}，共 36 种组合
TWO_DICE_DIST: dict[int, int] = Counter(sum(roll) for roll in _all_rolls(2))
TWO_DICE_TOTAL = sum(TWO_DICE_DIST.values())

# 3 骰和分布：{sum: count}，共 216 种组合
THREE_DICE_DIST: dict[int, int] = Counter(sum(roll) for roll in _all_rolls(3))
THREE_DICE_TOTAL = sum(THREE_DICE_DIST.values())


def prob_two_dice(target: int) -> float:
    """2 骰和等于 target 的概率。"""
    return TWO_DICE_DIST.get(target, 0) / TWO_DICE_TOTAL


def prob_three_dice(target: int) -> float:
    """3 骰和等于 target 的概率。"""
    return THREE_DICE_DIST.get(target, 0) / THREE_DICE_TOTAL


def prob_two_dice_less_than(target: int) -> float:
    """2 骰和 < target 的概率。"""
    count = sum(v for k, v in TWO_DICE_DIST.items() if k < target)
    return count / TWO_DICE_TOTAL


def prob_two_dice_greater_than(target: int) -> float:
    """2 骰和 > target 的概率。"""
    count = sum(v for k, v in TWO_DICE_DIST.items() if k > target)
    return count / TWO_DICE_TOTAL


def prob_three_dice_less_than(target: int) -> float:
    """3 骰和 < target 的概率。"""
    count = sum(v for k, v in THREE_DICE_DIST.items() if k < target)
    return count / THREE_DICE_TOTAL


def prob_three_dice_greater_than(target: int) -> float:
    """3 骰和 > target 的概率。"""
    count = sum(v for k, v in THREE_DICE_DIST.items() if k > target)
    return count / THREE_DICE_TOTAL


def prob_three_dice_given_two(two_sum: int, condition: str = "equals", target: int = TARGET) -> float:
    """
    已知 2 骰和为 two_sum，加入第 3 颗公共骰子后满足 condition 的概率。
    condition: "equals" | "less" | "greater"
    """
    remaining = [(two_sum + f) for f in FACES]
    total = len(FACES)
    if condition == "equals":
        count = sum(1 for s in remaining if s == target)
    elif condition == "less":
        count = sum(1 for s in remaining if s < target)
    elif condition == "greater":
        count = sum(1 for s in remaining if s > target)
    else:
        raise ValueError(f"Unknown condition: {condition}")
    return count / total


def _opponent_score_distribution(opponent_has_public: bool) -> dict[int, int]:
    """获取对手的分数分布（根据是否有公共骰子）。"""
    return THREE_DICE_DIST if opponent_has_public else TWO_DICE_DIST


def estimate_win_probability(
    my_score: int | None,
    has_public: bool,
    num_opponents: int = 3,
    opponent_has_public: bool | None = None,
    public_die_known: int | None = None,
    revealed_dice: dict[str, int] | None = None,
) -> float:
    """
    基于真实概率分布估算胜率。

    返回值是 P(我赢) 的近似值，考虑了：
    - 我的确切分数
    - 对手数量
    - 平局时是否有公共骰子优势
    - 对手是否有公共骰子（如果未知，假设和我一样）
    """
    if my_score is None:
        return 0.0

    if opponent_has_public is None:
        opponent_has_public = has_public

    dist = THREE_DICE_DIST if opponent_has_public else TWO_DICE_DIST
    total = THREE_DICE_TOTAL if opponent_has_public else TWO_DICE_TOTAL

    if my_score > TARGET:
        # 爆牌：只有全员爆牌且我最小才赢
        # P(对手也爆牌) = P(score > 13)
        count_bust = sum(v for k, v in dist.items() if k > TARGET)
        p_bust = count_bust / total
        # 简化：不考虑"我是最小"的精确概率
        return (p_bust ** num_opponents) * 0.5

    if my_score == TARGET:
        # 恰好 =13，对手不可能比我更高（最多也是 13 平局）
        # has_public: 平局我赢 → 必胜
        if has_public:
            return 0.99
        # no public: 平局时可能输给选了公共骰子的人
        count_eq = dist.get(TARGET, 0)
        p_eq = count_eq / total
        # 对手刚好 13 且选了公共骰子→我输，简化：50% 的 13 对手会抢走胜利
        p_beat_one = 1.0 - p_eq * 0.5
        return max(0.0, p_beat_one ** num_opponents)

    # my_score < TARGET
    # 我赢的条件：对手不爆牌时分数 < 我，或者对手爆牌
    count_less = sum(v for k, v in dist.items() if k < my_score)
    count_greater = sum(v for k, v in dist.items() if k > TARGET)
    # 对手分数在 [my_score, TARGET] 区间则我输（或平局）
    count_bad = sum(v for k, v in dist.items() if my_score <= k <= TARGET)

    # P(赢 vs 1 个对手)
    # 我赢 = 对手比我小 + 对手爆牌
    p_win_vs_one = (count_less + count_greater) / total

    # 平局情况：如果对手恰好 = my_score
    count_tie = dist.get(my_score, 0)
    p_tie = count_tie / total
    if has_public:
        # 平局时我有优势 → 算作赢
        p_win_vs_one += p_tie
    # 如果不选公共骰子，平局可能输给选了公共骰子的人，简化忽略

    p_win_vs_one = max(0.01, min(0.99, p_win_vs_one))

    return p_win_vs_one ** num_opponents


def expected_three_dice_sum(two_sum: int) -> float:
    """已知 2 骰和，加入公共骰子后的期望总和。"""
    return two_sum + 4.5
