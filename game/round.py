"""
单轮游戏状态机。

流程：
1. 投暗骰 → 第一轮下注（固定 5 元，不可弃牌/加注）
2. 第二轮下注（选择公共骰子 + 下注，可弃牌）
3. 公开骰子 + 投公共骰子
4. 第三轮下注（可弃牌） → 结算
"""

from __future__ import annotations

from enum import Enum, auto

from models.player import Player
from models.die import Die
from models.pot import Pot
from betting.manager import BettingRound, MIN_BET
from scoring.judge import judge, ShowdownResult, TARGET
from ai.strategy import (
    decide_first_bet,
    choose_reveal_die,
    evaluate_hand_strength,
    BetAction,
    BetActionType,
)
from ai.betting_strategy_round2 import (
    decide_public_die, decide_second_bet,
    compute_hand_strength, build_score_distribution,
)
from ai.betting_strategy_round3 import (
    decide_third_bet,
    build_opponent_distribution,
    monte_carlo_win_probability,
    risk_adjusted_eu,
)
from ai.probability import estimate_win_probability, expected_three_dice_sum, prob_three_dice_given_two


class Phase(Enum):
    INIT = auto()
    DEAL = auto()
    BET_1 = auto()
    BET_2 = auto()
    REVEAL = auto()
    BET_3 = auto()
    SHOWDOWN = auto()
    DONE = auto()


class Round:
    """单轮游戏。"""

    def __init__(self, players: list[Player], pot: Pot, verbose: bool = True, debug: bool = False):
        self._players = players
        self._pot = pot
        self._public_die: int | None = None
        self._phase: Phase = Phase.INIT
        self._round_bet: int = 0
        self._verbose = verbose
        self._debug = debug
        self._log: list[str] = []

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self._players if not p.folded]

    def _log_event(self, msg: str):
        self._log.append(msg)
        if self._verbose:
            print(msg)

    def run(self) -> ShowdownResult:
        for p in self._players:
            p.reset_for_round()
        self._pot.reset()

        self._phase = Phase.DEAL
        self._deal()

        self._phase = Phase.BET_1
        self._betting_phase_1()

        self._phase = Phase.BET_2
        self._betting_phase_2()

        self._phase = Phase.REVEAL
        self._reveal_and_roll_public()

        self._phase = Phase.BET_3
        self._betting_phase_3()

        self._phase = Phase.SHOWDOWN
        result = self._showdown()

        self._phase = Phase.DONE
        return result

    # ==================================================================
    # 阶段 0：发牌
    # ==================================================================
    def _deal(self):
        self._log_event("\n" + "—" * 60)
        self._log_event(f"  发牌")
        self._log_event("—" * 60)
        for p in self._players:
            if p.is_bankrupt:
                continue
            d1 = Die(); d2 = Die()
            d1.roll(); d2.roll()
            p.hand = [d1.value, d2.value]
            self._log_event(f"  {p.name}: [{d1.value},{d2.value}] sum={d1.value+d2.value}  资金=${p.money}")

    # ==================================================================
    # 阶段 1：第一轮下注（固定 5 元，不可弃牌，不可加注）
    # ==================================================================
    def _betting_phase_1(self):
        self._log_event(f"\n— 第一轮下注（每人固定 5 元）—")
        active = self.active_players
        max_allowed = self._max_allowed_bet()

        for p in active:
            amount = decide_first_bet(p.hand, p.money, max_allowed)
            actual = p.place_bet(amount)
            self._pot.collect(actual)
            self._log_event(f"  {p.name}: 下注 ${actual}")

        self._log_event(f"  >> 奖池 ${self._pot.total}")

    # ==================================================================
    # 阶段 2：选择公共骰子 + 第二轮下注（可弃牌）—— 关键决策点
    # ==================================================================
    def _betting_phase_2(self):
        self._log_event(f"\n{'—'*60}")
        self._log_event(f"  第二轮：选择公共骰子 + 下注（可弃牌）")
        self._log_event(f"{'—'*60}")
        self._log_event(f"  公共骰子尚未投掷，需基于期望值决策")

        # 步骤 1：秘密选择是否加入公共骰子
        self._log_event(f"")
        self._log_event(f"  [选择公共骰子]")
        for p in self.active_players:
            s = sum(p.hand)
            choose = decide_public_die(p.hand, p.money, p.current_bet, self._pot.total)
            p.chose_public = choose
        choosers = [p.name for p in self.active_players if p.chose_public]
        non_choosers = [p.name for p in self.active_players if not p.chose_public]
        self._log_event(f"    加入: {', '.join(choosers) if choosers else '无'}  |  不加入: {', '.join(non_choosers) if non_choosers else '无'}")

        # 步骤 2：展示手牌分析与概率分布
        self._log_event(f"")
        self._log_event(f"  [手牌分析]")
        for p in self.active_players:
            s = sum(p.hand)
            pub = "有" if p.chose_public else "无"
            strength = compute_hand_strength(p.hand, p.chose_public, p.risk_aversion)
            dist = build_score_distribution(p.hand, p.chose_public)

            # 从概率分布提取统计量
            p_13 = dist.get(TARGET, 0.0)
            p_bust = sum(prob for score, prob in dist.items() if score > TARGET)
            p_safe = 1.0 - p_bust - p_13  # score < 13
            # 安全区期望
            safe_scores = [score for score in dist if score < TARGET]
            if safe_scores:
                exp_safe = sum(score * dist[score] for score in safe_scores) / p_safe if p_safe > 0 else 0
            else:
                exp_safe = 0.0

            # 分布展示
            if p.chose_public:
                scores_str = " ".join(
                    f"{score}:{dist.get(score, 0):.0%}" for score in sorted(dist.keys())
                )
                self._log_event(
                    f"    {p.name}: [{p.hand[0]},{p.hand[1]}] +? → 分布 [{scores_str}]"
                )
            else:
                self._log_event(
                    f"    {p.name}: [{p.hand[0]},{p.hand[1]}] = {s}（确定）"
                )

            self._log_event(
                f"         公共骰={pub}  |  牌力={strength:.3f}  |  "
                f"P(13)={p_13:.0%}  P(安全)={p_safe:.0%}(E={exp_safe:.1f})  P(爆)={p_bust:.0%}  "
                f"α={p.risk_aversion:.2f}"
            )

        # 步骤 3：下注循环
        self._log_event(f"")
        self._log_event(f"  [下注]")
        self._resolve_betting(can_fold=True)

    # ==================================================================
    # 阶段 4：公开骰子 + 投公共骰子
    # ==================================================================
    def _reveal_and_roll_public(self):
        self._log_event(f"\n— 公开骰子 + 投公共骰子 —")
        for p in self.active_players:
            die_to_reveal = choose_reveal_die(p.hand)
            p.revealed_die = die_to_reveal

        self._public_die = Die()
        self._public_die.roll()

        for p in self.active_players:
            if p.chose_public:
                p.public_die = self._public_die.value

            other = [d for d in p.hand if d != p.revealed_die]
            score = sum(p.hand) + (p.public_die or 0)
            pub_str = f"+{self._public_die.value}" if p.chose_public else ""
            self._log_event(f"  {p.name}: 公开 {p.revealed_die}，暗骰 {other[0] if other else '?'}，公共骰子 {pub_str}，总分 {score}")

    # ==================================================================
    # 阶段 5：第三轮下注（可弃牌，最终轮）—— 关键决策点
    # ==================================================================
    def _betting_phase_3(self):
        self._log_event(f"\n{'—'*60}")
        self._log_event(f"  第三轮下注（可弃牌，最终轮）")
        self._log_event(f"{'—'*60}")
        self._log_event(f"  贝叶斯推断对手分布 → Monte Carlo 桌面胜率 → 风险调整 EU")
        self._log_event(f"")

        pub_val = self._public_die.value if self._public_die else 0

        for p in self.active_players:
            score = sum(p.hand) + (p.public_die or 0)

            # 贝叶斯推断对手分布 + Monte Carlo 胜率
            opponent_dists = []
            for op in self.active_players:
                if op is not p and op.revealed_die is not None:
                    dist = build_opponent_distribution(op.revealed_die, pub_val)
                    opponent_dists.append(dist)

            if opponent_dists:
                p_win = monte_carlo_win_probability(score, p.chose_public, opponent_dists)
                # 跟注 0 元时 EU 的符号判断（仅展示用）
                eu_check = risk_adjusted_eu(p_win, self._pot.total, 0, p.risk_aversion)
            else:
                p_win = 1.0
                eu_check = float('inf')

            status = ""
            if score == TARGET:
                status = "✨ 完美"
            elif score > TARGET:
                status = "💥 爆牌"
            else:
                status = f"距 13 差 {TARGET - score}"

            self._log_event(
                f"  {p.name}: 总分 {score} {status}  |  "
                f"P(win)={p_win:.0%}  EU₀={eu_check:+.1f}  α={p.risk_aversion:.2f}"
            )

        self._resolve_betting(can_fold=True)

    # ==================================================================
    # 结算
    # ==================================================================
    def _showdown(self) -> ShowdownResult:
        self._log_event(f"\n{'—'*60}")
        self._log_event(f"  结算")
        self._log_event(f"{'—'*60}")

        for p in self.active_players:
            score = sum(p.hand) + (p.public_die or 0)
            bust = " 💥爆牌" if score > TARGET else ""
            perfect = " ✨完美" if score == TARGET else ""
            self._log_event(f"  {p.name}: 总分 {score}{bust}{perfect}")

        result = judge(self._players, self._pot.total)

        # 判定理由
        scores = {}
        active = [p for p in self._players if not p.folded]
        for p in active:
            scores[p] = sum(p.hand) + (p.public_die or 0)

        perfect = [p for p in active if scores[p] == TARGET]
        under = [p for p in active if scores[p] < TARGET]
        over = [p for p in active if scores[p] > TARGET]

        if perfect:
            reason = f"恰好 13 点 → {', '.join(p.name for p in perfect)} 获胜"
        elif under and not over:
            reason = f"均 <13，最大者获胜"
        elif under and over:
            reason = f"{', '.join(p.name for p in over)} 爆牌出局，剩余比较"
        else:
            reason = f"全员爆牌，最小者获胜"

        self._log_event(f"\n  判定：{reason}")

        result.distribute()

        self._log_event(f"  奖池：${result.pot}")
        if result.winners:
            names = ", ".join(w.name for w in result.winners)
            self._log_event(f"  获胜者：{names}  (+${result.prize_per_winner} x {len(result.winners)})")

        self._log_event(f"\n  资金变动：")
        for p in self._players:
            self._log_event(f"    {p.name}: ${p.money}")

        return result

    # ==================================================================
    # 下注循环
    # ==================================================================
    def _max_allowed_bet(self) -> int:
        active = self.active_players
        if not active:
            return 0
        return min(p.money + p.current_bet for p in active)

    def _resolve_betting(self, can_fold: bool):
        """
        循环下注直到所有人等额且无人再加注。

        流程：
        1. 找出当前最高下注额
        2. 让落后的玩家选择跟注/加注/弃牌
        3. 所有人等额后，给每人一次加注机会
        4. 有人加注 → 回到步骤 2；无人加注 → 结束
        """
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            active = self.active_players
            if len(active) <= 1:
                break

            max_allowed = self._max_allowed_bet()

            # 退还超过上限的注额
            for p in active:
                if p.current_bet > max_allowed:
                    excess = p.current_bet - max_allowed
                    p.money += excess
                    p.current_bet = max_allowed
                    self._pot.refund(excess)

            current_bet = max(p.current_bet for p in active)
            self._round_bet = current_bet

            # ---- 步骤 2：让落后玩家跟上 ----
            changed = False
            for p in active:
                if p.current_bet < current_bet:
                    changed |= self._handle_player_action(p, current_bet, max_allowed, can_fold)
                    if p.folded and len(self.active_players) <= 1:
                        break

            if len(self.active_players) <= 1:
                break

            # ---- 步骤 3：等额后，给每人一次加注机会 ----
            if all(p.current_bet == current_bet for p in active):
                raise_occurred = False
                for p in list(self.active_players):
                    # 如果该玩家已 all-in（资金为 0），跳过
                    if p.money <= 0:
                        continue
                    # 检查是否达到上限
                    if p.current_bet >= max_allowed:
                        continue

                    changed |= self._handle_player_action(
                        p, p.current_bet, max_allowed, can_fold, is_raise_opportunity=True
                    )
                    if p.folded and len(self.active_players) <= 1:
                        break
                    # 检查是否有人加注了
                    new_current = max(pp.current_bet for pp in self.active_players)
                    if new_current > current_bet:
                        raise_occurred = True
                        break

                if not raise_occurred and not changed:
                    break  # 无人加注，结束
            elif not changed:
                break

        self._log_event(f"  >> 奖池 ${self._pot.total}，剩余 {len(self.active_players)} 人")

    def _handle_player_action(self, player: Player, current_bet: int,
                               max_allowed: int, can_fold: bool,
                               is_raise_opportunity: bool = False) -> bool:
        """处理单个玩家的下注动作。返回是否有变化。"""
        to_call = current_bet - player.current_bet
        remaining_cap = max_allowed - player.current_bet

        if to_call > player.money:
            if can_fold:
                player.folded = True
                self._log_event(f"  {player.name}: 资金不足(${player.money})，无法跟注 ${to_call} → 弃牌")
                return True
            else:
                to_call = player.money

        # 构建公开信息
        active = self.active_players
        revealed: dict[str, int] = {}
        for op in active:
            if op is not player and op.revealed_die is not None:
                revealed[op.name] = op.revealed_die

        # AI 决策
        if self._phase == Phase.BET_3:
            pd_value = self._public_die.value if self._public_die else None
            # 收集对手资金用于资金位置判断
            opp_moneys = [op.money for op in active if op is not player]
            action = decide_third_bet(
                player.hand, player.chose_public, pd_value,
                revealed, current_bet, player.current_bet,
                self._pot.total, player.money, max_allowed,
                player.risk_aversion, opp_moneys,
            )
        else:
            action = decide_second_bet(
                player.hand, player.chose_public,
                current_bet, player.current_bet,
                self._pot.total, player.money, max_allowed,
                player.risk_aversion,
            )

        if not can_fold and action.type == BetActionType.FOLD:
            action = BetAction(BetActionType.CALL, to_call)

        # 加注机会时：如果 AI 选择跟注（不行动），直接跳过
        if is_raise_opportunity and action.type != BetActionType.RAISE:
            return False

        # ---- Debug: 决策分析 ----
        if self._debug:
            self._log_decision_analysis(player, action, current_bet, to_call, max_allowed)

        if action.type == BetActionType.FOLD:
            player.folded = True
            self._log_event(f"  {player.name}: 弃牌（失去 ${player.current_bet}）")
            return True
        elif action.type == BetActionType.CALL:
            actual = player.place_bet(min(to_call, player.money, remaining_cap))
            self._pot.collect(actual)
            if to_call > 0:
                self._log_event(f"  {player.name}: 跟注 ${actual}（当前共 ${player.current_bet}）")
            return True
        elif action.type == BetActionType.RAISE:
            call_actual = player.place_bet(min(to_call, player.money, remaining_cap))
            self._pot.collect(call_actual)
            raise_cap = max_allowed - player.current_bet
            raise_actual = player.place_bet(min(action.amount, player.money, raise_cap))
            self._pot.collect(raise_actual)
            if is_raise_opportunity:
                self._log_event(f"  {player.name}: 加注 +${action.amount}（当前共 ${player.current_bet}）")
            else:
                self._log_event(f"  {player.name}: 跟注并加注 +${action.amount}（当前共 ${player.current_bet}）")
            return True

        return False

    # ==================================================================
    # Debug：下注决策的详细数学分析
    # ==================================================================
    def _log_decision_analysis(self, player: Player, action: BetAction,
                               current_bet: int, to_call: int, max_allowed: int):
        """输出 AI 做出下注决策的完整计算过程。"""
        score = sum(player.hand) + (player.public_die or 0)
        strength = evaluate_hand_strength(player.hand, player.chose_public, player.public_die)

        # 计算胜率
        opponents = [op for op in self.active_players if op is not player]
        num_opponents = len(opponents)
        p_win = estimate_win_probability(score, player.chose_public, num_opponents) if num_opponents > 0 else 1.0

        # EV = P(win) * pot_gain - P(lose) * cost_to_call
        pot_if_win = self._pot.total + to_call  # 简化：跟注后奖池增加
        ev_call = p_win * pot_if_win - (1 - p_win) * to_call

        # 投资回报率
        pot_odds = to_call / (self._pot.total + to_call) if (self._pot.total + to_call) > 0 else 0

        lines = [
            f"",
            f"  ┌─ {player.name} 决策分析 ─────────────────────",
            f"  │ 当前分数：{score}（目标 13）",
            f"  │ 手牌强度：{strength:.2f}",
            f"  │ 估算胜率：{p_win:.0%}（对手 {num_opponents} 人）",
            f"  │ 当前奖池：${self._pot.total}",
            f"  │ 需要跟注：${to_call}（已下注 ${player.current_bet}）",
            f"  │ 剩余资金：${player.money}",
            f"  │ 下注上限：${max_allowed}",
            f"  │",
            f"  │ EV(跟注) = {p_win:.0%} × ${pot_if_win} - {(1-p_win):.0%} × ${to_call} = ${ev_call:+.1f}",
            f"  │ Pot Odds = ${to_call} / ${self._pot.total + to_call} = {pot_odds:.0%}",
        ]

        if action.type == BetActionType.FOLD:
            reason = "EV 为负或手牌太弱" if ev_call < 0 else "手牌强度不足"
            lines.append(f"  │ → 弃牌：{reason}")
        elif action.type == BetActionType.CALL:
            lines.append(f"  │ → 跟注：EV={ev_call:+.1f}，手牌强度 OK")
        elif action.type == BetActionType.RAISE:
            lines.append(f"  │ → 加注 ${action.amount}：强牌，最大化收益")

        lines.append(f"  └──────────────────────────────────────────")
        for line in lines:
            print(line)
