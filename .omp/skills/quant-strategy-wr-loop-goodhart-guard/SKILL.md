---
name: quant-strategy-wr-loop-goodhart-guard
description: "Use when running an autonomous or semi-autonomous win-rate/metric-improvement loop on a trading strategy (FreqTrade or similar backtest harness) — especially when asked to 'increase win rate' or iterate a strategy loop until interrupted. Prevents Goodhart-style metric gaming and over-selectivity traps that produce flattering headline numbers on a strategy that is actually worse or untradeable."
---

## The trap this guards against

Optimizing purely for win rate (WR) or any single scalar metric on a trading strategy reliably produces strategies that look great and perform badly: tiny/premature profit-taking, over-selective filters that leave near-zero trades, or filters that structurally conflict with the entry paradigm. This has happened repeatedly and independently in real backtests (not hypothetically) — treat every WR jump as a hypothesis to falsify, not a win to bank.

## Procedure

1. **Baseline first.** Capture full metrics (WR, Sharpe, total_profit_pct, max_drawdown, trade_count, profit_factor) before touching anything. WR alone is never sufficient.

2. **Change one variable per round, verify with a real backtest every time.** Never batch multiple untested parameter changes — you can't attribute the effect. Log the before/after numbers even when a change is reverted; the negative result is as valuable as the positive one for the next session.

3. **Distrust WR/PF spikes — always check total_profit_pct and Sharpe alongside them.** If WR or profit_factor jumps while total_profit_pct or Sharpe drops or trade_count collapses, that is metric gaming, not edge. Revert immediately regardless of how good the WR number looks. Concrete pattern seen in practice: an RSI>80 exit filter spiked WR from 62%->91% and PF from 2.3->11.6, while total return crashed 12.55%->3.60% — a strategy that *looks* dramatically better and *is* dramatically worse.

4. **Trade count is a validity gate, not a detail.** A strategy with <20 trades over a multi-year backtest cannot be trusted regardless of its WR/PF — 8-13 trades producing 84-92% WR is noise, not signal. If tightening a filter drops trade count into this range even while WR/PF look amazing, that round is a failure, not a win. Loosen back until trade count clears a meaningful threshold (~20+), even if that costs some WR/PF.

5. **When simple parameter tuning plateaus or reverses (tightening the same lever stops helping or starts hurting), escalate to a genuinely new variable — but check paradigm compatibility first.** Before adding e.g. an overbought/oversold filter to a strategy, ask whether the entry paradigm structurally requires or excludes that condition. A strong momentum/breakout entry paradigm will structurally coincide with overbought oscillator readings — adding 'RSI must not be overbought' as an entry filter to a breakout strategy is close to self-contradictory and will collapse trade count.

6. **When escalating to a new paradigm (e.g. adding mean-reversion to a portfolio of trend-following strategies), research prior failed attempts in the repo/codebase first.** Repos with long research histories usually already tried and killed similar paradigms — read why they failed (over-tuned to death vs. structurally broken vs. never properly calibrated) before re-deriving the same dead end from scratch.

7. **Know when to stop.** Once a change produces a genuinely clean result — healthy PF (not suspiciously huge), positive Sharpe, and a trade count that clears the validity bar — stop optimizing that specific lever. Pushing further risks re-entering the Goodhart trap for a few extra basis points. A credible, unspectacular result beats a spectacular, fragile one.

## Fast checklist before declaring any round a 'win'

- [ ] Backtest actually run this round (not assumed from a prior similar change)
- [ ] total_profit_pct and Sharpe checked, not just WR/PF
- [ ] trade_count > ~20 (over a multi-year backtest)
- [ ] If WR/PF jumped a lot, profit and Sharpe moved the same direction (not opposite)
- [ ] The paradigm and the new filter are not structurally contradictory
