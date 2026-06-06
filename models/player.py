class Player:
    """玩家：持有资金、手牌、状态标志。"""

    def __init__(self, name: str, money: int = 100, risk_aversion: float = 0.30):
        self.name = name
        self.money = money
        self.risk_aversion = risk_aversion  # 爆牌厌恶度 [0, 0.6]，越高越保守

        # 当前轮状态
        self.hand: list[int] = []          # 暗骰点数（2 颗）
        self.public_die: int | None = None # 公共骰子点数（如有）
        self.chose_public: bool = False    # 本轮是否选择加入公共骰子
        self.revealed_die: int | None = None  # 公开的那颗骰子
        self.current_bet: int = 0          # 本轮已下注总额
        self.folded: bool = False

    @property
    def score(self) -> int | None:
        """计算当前手牌总分。"""
        if not self.hand:
            return None
        total = sum(self.hand)
        if self.public_die is not None:
            total += self.public_die
        return total

    @property
    def is_bankrupt(self) -> bool:
        return self.money <= 0

    def place_bet(self, amount: int) -> int:
        """下注，返回实际下注金额。"""
        actual = min(amount, self.money)
        self.money -= actual
        self.current_bet += actual
        return actual

    def reset_for_round(self):
        """新一轮开始，重置状态。"""
        self.hand = []
        self.public_die = None
        self.chose_public = False
        self.revealed_die = None
        self.current_bet = 0
        self.folded = False

    def __repr__(self):
        return f"Player({self.name}, ${self.money})"
