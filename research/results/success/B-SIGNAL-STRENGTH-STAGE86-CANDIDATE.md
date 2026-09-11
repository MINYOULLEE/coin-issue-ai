# B Stage86 signal-strength candidate (research only)

- Status: candidate only; not deployed and no live state changed.
- Scope: current B Stage66 plus one ALGO selector change.
- Rule: keep 3-hour 8% capitulation and 50% rejection wick; reduce the 48-hour-average volume gate from 1.5x to 1.0x.
- Current Stage66 baseline: 962 trades, 55.61% win rate, $100 -> $4,556,311.86, +4,556,211.86%, hourly mark MDD -54.65%, adverse bound -62.05%.
- Candidate: 966 trades, 55.69% win rate, $100 -> $4,865,852.40, +4,865,752.40%, hourly mark MDD -54.65%, adverse bound -62.05%.
- Double-cost stress: +103,878.75% versus baseline +98,430.96%; adverse bound -66.91%; liquidation proxy 0.
- Three chronological thirds: +12,036.76%, +2,298.80%, +1,566.41%; all positive.
- Interpretation: adds only four executed portfolio trades over five years while improving modeled compound return by about 6.79%, without worsening modeled MDD.
- Required before adoption: new-entry futures-minute fill/slippage validation and explicit user approval. This result is not proof of BingX live performance.

Evidence: `research/results/b_signal_strength_stage86/results.json`
