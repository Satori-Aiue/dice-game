import random


class Die:
    """单颗骰子，面值范围 2-7。"""

    MIN_FACE = 2
    MAX_FACE = 7

    def __init__(self):
        self._value: int | None = None

    @property
    def value(self) -> int | None:
        return self._value

    def roll(self) -> int:
        self._value = random.randint(self.MIN_FACE, self.MAX_FACE)
        return self._value

    def __repr__(self):
        return str(self._value) if self._value is not None else "?"
