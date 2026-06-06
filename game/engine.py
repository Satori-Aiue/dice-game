"""
游戏引擎：管理整局游戏生命周期。

结束条件：任意玩家资金归零时结束。
"""

from __future__ import annotations

import random

from models.player import Player
from models.pot import Pot
from .round import Round, Phase
from betting.manager import MIN_BET

# 风险偏好范围
RISK_AVERSION_MIN = 0.05   # 激进型
RISK_AVERSION_MAX = 0.55   # 保守型


class GameEngine:
    """整局游戏控制器。"""

    def __init__(self, player_names: list[str] | None = None, starting_money: int = 100,
                 verbose: bool = True, debug: bool = False, seed_risk: bool = True):
        if player_names is None:
            player_names = ["Alice", "Bob", "Charlie", "Diana"]
        # 为每个玩家生成随机的风险厌恶度，模拟不同策略风格
        self._players = [
            Player(name, starting_money,
                   risk_aversion=round(random.uniform(RISK_AVERSION_MIN, RISK_AVERSION_MAX), 2)
                   if seed_risk else 0.30)
            for name in player_names
        ]
        self._pot = Pot()
        self._verbose = verbose
        self._debug = debug
        self._round_number = 0
        self._history: list[dict] = []

    @property
    def players(self) -> list[Player]:
        return self._players

    @property
    def round_number(self) -> int:
        return self._round_number

    def run(self) -> dict:
        """
        运行整局游戏，直到有人破产。
        返回游戏摘要。
        """
        self._log(f"\n{'='*50}")
        self._log(f"骰子游戏开始！")
        self._log(f"每人初始资金：${self._players[0].money}")
        self._log(f"{'='*50}")
        for p in self._players:
            label = _risk_label(p.risk_aversion)
            self._log(f"  {p.name}: α={p.risk_aversion:.2f}（{label}）")
        self._log(f"{'='*50}")

        while True:
            # 检查结束条件：有玩家资金归零
            bankrupt = [p for p in self._players if p.is_bankrupt]
            if bankrupt:
                self._log(f"\n[GAME OVER] 游戏结束！{', '.join(p.name for p in bankrupt)} 破产！")
                break

            self._round_number += 1
            self._log(f"\n{'='*40}")
            self._log(f"第 {self._round_number} 轮")
            self._log(f"{'='*40}")

            round_game = Round(self._players, self._pot, verbose=self._verbose, debug=self._debug)
            result = round_game.run()

            self._history.append({
                "round": self._round_number,
                "winners": [w.name for w in result.winners],
                "pot": result.pot,
                "player_money": {p.name: p.money for p in self._players},
            })

            # 每轮结束时检查：资金 < 5 的玩家视为失去全部资金，游戏结束
            low_money = [p for p in self._players if 0 < p.money < MIN_BET]
            for p in low_money:
                self._log(f"  {p.name}: 资金 ${p.money} 低于最低下注 ${MIN_BET}，视为失去全部资金")
                p.money = 0
            if low_money:
                self._log(f"\n[GAME OVER] 游戏结束！{', '.join(p.name for p in low_money)} 余额不足，游戏结束！")
                break

        # 最终排名
        ranked = sorted(self._players, key=lambda p: p.money, reverse=True)
        self._log(f"\n{'='*50}")
        self._log("--- 最终排名 ---")
        for i, p in enumerate(ranked, 1):
            label = _risk_label(p.risk_aversion)
            self._log(f"  {i}. {p.name}: ${p.money}（α={p.risk_aversion:.2f} {label}）")

        return {
            "rounds": self._round_number,
            "history": self._history,
            "final_ranking": [(p.name, p.money) for p in ranked],
        }

    def _log(self, msg: str):
        if self._verbose:
            print(msg)


def _risk_label(alpha: float) -> str:
    """将风险厌恶度映射为中文标签。"""
    if alpha <= 0.10:
        return "激进"
    elif alpha <= 0.25:
        return "偏激进"
    elif alpha <= 0.40:
        return "中性"
    elif alpha <= 0.50:
        return "偏保守"
    else:
        return "保守"
