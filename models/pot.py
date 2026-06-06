class Pot:
    """奖池管理。"""

    def __init__(self):
        self._total: int = 0

    @property
    def total(self) -> int:
        return self._total

    def collect(self, amount: int):
        """从玩家收取下注加入奖池。"""
        self._total += amount

    def refund(self, amount: int):
        """退还多出注额（用于 all-in 上限规则）。"""
        self._total -= amount

    def reset(self):
        """新一轮开始，清空奖池。"""
        self._total = 0

    def __repr__(self):
        return f"Pot(${self._total})"
