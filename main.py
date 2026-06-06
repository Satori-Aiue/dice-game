"""
骰子游戏入口。

用法：
    python main.py              # 默认 4 名 AI 玩家，每人 $100
    python main.py --players 4 --money 100 --rounds 10
"""

from __future__ import annotations

import argparse
import random

from game.engine import GameEngine
from ui.cli import CLI


def main():
    parser = argparse.ArgumentParser(description="骰子赌博游戏 — AI 模拟")
    parser.add_argument(
        "--players", "-p", type=int, default=4,
        help="玩家数量（默认 4）"
    )
    parser.add_argument(
        "--money", "-m", type=int, default=100,
        help="初始资金（默认 100）"
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None,
        help="随机种子（用于复现）"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="静默模式（只显示最终结果）"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true",
        help="调试模式（显示每个决策的计算过程）"
    )
    parser.add_argument(
        "--names", "-n", nargs="*", default=None,
        help="玩家名称列表"
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    player_names = args.names
    if player_names is None:
        player_names = [f"AI-{i+1}" for i in range(args.players)]

    CLI.print_banner()

    engine = GameEngine(
        player_names=player_names,
        starting_money=args.money,
        verbose=not args.quiet,
        debug=args.debug,
    )
    engine.run()


if __name__ == "__main__":
    main()
