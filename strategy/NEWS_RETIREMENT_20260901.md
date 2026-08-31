# News retirement — approved production deployment

Owner requested removal of news collection and all news/issue UI. Removed RSS sources, parsing, feed fetching and news aggregation from the cloud collector. Market fetching, A decision features, signal management, exchange calls, authentication and schedules are unchanged. Live snapshot writer omits issues/status/stats/hot_themes/hot_events and declares news_enabled=false. Existing trades and research records are not deleted.

Dashboard removes news navigation, news counters, themes/events panels and news render paths. Keeps market prices, A/B recommendations, combined A/B controls and separate public histories. Telegram retires old news alert state only after receiving news_enabled=false; this is not reported as a source recovery. Trade delivery markers and trading alerts are preserved.

Local browser checked A, B and separate password gates. Existing tests pass with --experimental-vm-modules (the first run omitted the required flag). Added three retirement tests. Production coin-collector v76 was identical to pre-edit local source.

Initial deployment was blocked pending explicit destination approval. The owner subsequently approved Supabase project ljazcstmwtuhideaarti and GitHub MINYOULLEE/coin-issue-ai. Deployed coin-collector v77 and telegram-trade-notify v30, preserving scheduler authentication. A/B enabled=true/test_mode=false verified after deployment. All 98 Node tests, two Python margin tests and the 59-file separation audit passed. No live orders were forced.
