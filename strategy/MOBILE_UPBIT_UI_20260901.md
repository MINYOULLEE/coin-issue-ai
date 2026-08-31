# Upbit ticker and mobile presentation

Owner requested Upbit USDT at the right of the major-market strip and a clearer mobile dashboard. The sixth card uses existing market.USDT (Upbit KRW quote); no API calls or collector changes added. Missing/invalid/wrong-source data displays an unavailable placeholder; quotes older than three minutes show a delayed label instead of a fresh-looking change percentage.

Responsive CSS: six desktop tickers, three columns on mobile, two below 360px. A/B navigation fits on-screen with a full-width combined-control button. Larger touch targets and text, two-column account/history metrics, contained horizontal tables, and 16px password inputs. A/B colors and separate authentication preserved. No orders, credentials, strategy settings, polling frequency or live switches changed.

Local browser checks: 390px ticker screenshot showed real Upbit KRW USDT; 320px B recommendation table scrolls inside its container without horizontal page overflow. Separate A/B password gates retained. Regression tests include ordering/currency, missing quote and stale quote cases. Publication uses existing GitHub Pages repository.
