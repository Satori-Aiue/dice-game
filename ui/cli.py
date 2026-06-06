"""
命令行界面。

负责：
- 显示游戏状态
- 读取用户输入
- 人类玩家交互（可选 -- 目前是全 AI 模拟）
"""

from __future__ import annotations

import sys


class CLI:
    """简单的命令行界面工具。"""

    @staticmethod
    def print_banner():
        print("""
+==============================+
|       Dice Gambling Game     |
|         骰 子 游 戏          |
+==============================+
        """)

    @staticmethod
    def ask_yes_no(prompt: str) -> bool:
        """询问是/否。"""
        while True:
            ans = input(f"{prompt} (y/n): ").strip().lower()
            if ans in ("y", "yes", "是"):
                return True
            if ans in ("n", "no", "否"):
                return False
            print("请输入 y 或 n")

    @staticmethod
    def ask_int(prompt: str, min_val: int = 0, max_val: int = sys.maxsize) -> int:
        """询问整数输入。"""
        while True:
            try:
                val = int(input(f"{prompt}: ").strip())
                if min_val <= val <= max_val:
                    return val
                print(f"请输入 {min_val} 到 {max_val} 之间的数字")
            except ValueError:
                print("请输入有效的数字")

    @staticmethod
    def press_enter_to_continue():
        """等待用户按回车继续。"""
        input("\n按回车继续...")

    @staticmethod
    def show_player_state(players):
        """显示所有玩家状态。"""
        print("\n--- 玩家状态 ---")
        for p in players:
            status = "[FOLD] 弃牌" if p.folded else "[ACTIVE] 活跃"
            if p.money <= 0:
                status = "[BANKRUPT] 破产"
            print(f"  {p.name}: ${p.money} | {status}")
        print()
