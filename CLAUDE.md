# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multiplayer dice gambling game. Dice values range from 2–7 (no cheating). Each round, players roll private dice, place bets across multiple stages, optionally add a public third die, then compare hands.

**Full rules, settings, and game flow are documented in `README.md`.** This file focuses on code architecture and development guidance.

Strategy design documents:
- `第二轮加注策略.md` — round 2 strategy design framework
- `第三轮加注策略.md` — round 3 strategy design framework

## Commands

```bash
# Run game (full AI simulation)
python main.py

# Run with custom settings
python main.py --players 4 --money 100 --seed 42

# Quiet mode (results only) + debug mode (show EV calculations per decision)
python main.py --quiet --seed 42
python main.py --debug --seed 42

# Custom player names
python main.py --names Alice Bob Charlie Diana

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_judge.py -v

# Run a single test function
python -m pytest tests/test_judge.py::TestJudge::test_exact_13_wins -v
```

## Architecture

```
models/                     Data classes: Player (incl. risk_aversion), Die, Pot
ai/                         AI decision-making: probability tables, strategy per phase
ai/strategy.py              Shared: BetAction, evaluate_hand_strength, decide_first_bet,
                            choose_reveal_die, MIN_BET, MIN_RAISE
ai/betting_strategy_round2.py   Second-round: decide_public_die, build_score_distribution,
                                compute_hand_strength, decide_second_bet
ai/betting_strategy_round3.py   Third-round: build_opponent_distribution,
                                judge_one_vs_one, monte_carlo_win_probability,
                                risk_adjusted_eu, decide_third_bet
ai/probability.py           Pre-computed 2-dice and 3-dice probability distributions
betting/                    BettingRound class — NOT used at runtime; betting loop is in game/round.py
scoring/                    Showdown judge: scoring rules, tiebreaker, pot distribution
game/                       Game flow: Round state machine (8 phases), GameEngine lifecycle
ui/                         CLI display utilities
tests/                      pytest suite (26 tests across 3 files)
```

### Key constants

- `TARGET = 13` — defined in both `ai/probability.py` and `scoring/judge.py` (duplicated)
- `MIN_BET = 5` — defined in both `ai/strategy.py` and `betting/manager.py`
- `MIN_RAISE = 6` — minimum raise in subsequent rounds (5+1)
- `risk_aversion` (α) ∈ [0.05, 0.55] — per-player bust sensitivity, set at game start, constant throughout. In round 2: penalizes HandStrength via `bust_penalty = α × P(bust)`. In round 3: amplifies perceived loss in EU via `loss = call × (1 + α)`
- `RULE_ADHERENCE = 0.95` (round 3) — assumed probability opponents follow "≤9 → join public die" rule
- `MC_SIMULATIONS = 500` (round 3) — Monte Carlo iterations for table win probability
- Die faces: 2–7 (uniform). 2-dice sum range: 4–14 (36 combos). 3-dice sum range: 6–21 (216 combos).

### AI decision points (5 per round)

1. **First bet** (`ai/strategy.py:decide_first_bet`): Always $5 (mandatory). No raising allowed.
2. **Public die choice** (`ai/betting_strategy_round2.py:decide_public_die`): `sum(hand) <= 9` → yes, otherwise no. Now part of the round 2 betting strategy module.
3. **Second bet** (`ai/betting_strategy_round2.py:decide_second_bet`): Pure own-hand evaluation — no opponent modeling.
   - `build_score_distribution()` constructs the full probability distribution of final scores
   - `compute_hand_strength()` extracts statistics (P(13), P(safe), P(bust), expected scores) and combines them via: `base = value_13 + (1-value_13) × value_safe`, then `strength = base - α × P(bust)`
   - The `risk_aversion` (α) parameter penalizes bust probability: conservative players fold risky hands, aggressive players stay in
   - Folds if strength < 0.35, raises if strength ≥ 0.75, otherwise calls. Target bet concept ensures natural convergence.
4. **Reveal die** (`ai/strategy.py:choose_reveal_die`): Random selection — `random.choice(hand)`.
5. **Third bet** (`ai/betting_strategy_round3.py:decide_third_bet`): Full-information stage — own score is known, all revealed dice and public die are known.
   - `build_opponent_distribution()`: Bayesian inference of each opponent's (score, chose_public) distribution from their revealed die + round-2 rule (soft rule adherence, 95%)
   - `monte_carlo_win_probability()`: 500-sim Monte Carlo to estimate true table P(win against all opponents) via `judge_one_vs_one()`
   - `risk_adjusted_eu()`: EU = P(win)×(pot+call) − (1−P(win))×call×(1+α). α modifies the utility function (loss amplification), not win probability
   - Folds if P(win)<2% or EU<0; raises if P(win)≥55% (step size 3×MIN_RAISE for fast convergence); otherwise calls. Target bet concept with MAX_BET_FRAC=0.35 ensures convergence.

### Betting loop (`game/round.py:_resolve_betting`)

The actual betting resolution is inline in `Round`, not in `betting/manager.py` (which is dead code). Only used for BET_2 and BET_3 (not BET_1, which is fixed at $5 with no raising). The loop:
1. Determines the max allowed bet (all-in cap from poorest player's total funds)
2. Makes trailing players catch up (call/fold/raise via AI)
3. Once equalized, gives each player one raise opportunity
4. If anyone raises → loop back to step 2; otherwise ends

### Game lifecycle

- `GameEngine.run()` assigns random `risk_aversion` (α ∈ [0.05, 0.55]) to each player at start, constant throughout. After each round, checks if any player's money < $5 (treated as losing all money, game over).
- `Round.run()` steps through 8 `Phase` enum states: INIT → DEAL → BET_1 → BET_2 → REVEAL → BET_3 → SHOWDOWN → DONE.（公共骰选择已合并入 BET_2）
- Showdown judgment in `scoring/judge.py`: exact 13 > highest under 13 > bust (unless all bust, then lowest wins). Public-die choosers win ties.

### Test structure

- `tests/test_probability.py` — verifies pre-computed distributions and conditional probabilities
- `tests/test_judge.py` — showdown rules: 13 wins, bust, all-bust, tiebreakers, public-die advantage
- `tests/test_betting.py` — player betting mechanics, all-in cap, fold, reset
