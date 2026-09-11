# B complement Stage17

Preliminary research candidate only; not adopted or independently validated.

최종 상태: 초기 다시간 탐색 자료이며 최종 채택 아님. 시간 겹침 방지와 데이터 연속성 검사를 보강한 후속 결과 및 비용 검증 보류는 ../b_complement_stage18_1h/REPORT.md 참조.

{
  "candidate": {
    "id": "ETH:streak_exhaustion_n7_move0.03:h2:l3",
    "symbol": "ETH",
    "pattern": "streak_exhaustion_n7_move0.03",
    "hold_hours": 2,
    "leverage": 3,
    "raw_overlap_pct": 20.0,
    "segments": [
      {
        "trades": 35,
        "sum_log": 0.03990926065590401,
        "mean_net": 0.005912058913502739
      },
      {
        "trades": 25,
        "sum_log": 0.0027915456038532594,
        "mean_net": 0.0006545615036108243
      },
      {
        "trades": 43,
        "sum_log": 0.03536783950469405,
        "mean_net": 0.004233737474156518
      }
    ],
    "score": 0.0027915456038532594
  },
  "extra_target_fraction": 0.25,
  "full": {
    "start_usd": 100.0,
    "end_usd": 534717.8340496058,
    "return_pct": 534617.8340496058,
    "closed_trade_mdd_pct": -49.40104126277226,
    "hourly_mark_mdd_pct": -56.39014907328288,
    "hourly_adverse_bound_pct": -62.79214505502222,
    "trades": 759,
    "win_rate_pct": 55.86297760210804,
    "margin_clipped": 656,
    "rejected": 21,
    "liquidation_proxy_count": 0,
    "max_reserved_equity_ratio": 1.6222373018844494,
    "max_gross_equity_ratio": 6.322542232335291
  },
  "segments": [
    {
      "start_usd": 100.0,
      "end_usd": 4967.1998836552375,
      "return_pct": 4867.1998836552375,
      "closed_trade_mdd_pct": -38.757882482350915,
      "hourly_mark_mdd_pct": -46.00249936779256,
      "hourly_adverse_bound_pct": -57.8247887987567,
      "trades": 267,
      "win_rate_pct": 58.42696629213483,
      "margin_clipped": 232,
      "rejected": 5,
      "liquidation_proxy_count": 0,
      "max_reserved_equity_ratio": 1.3912984135623616,
      "max_gross_equity_ratio": 6.322542232335291
    },
    {
      "start_usd": 100.0,
      "end_usd": 1010.662580496156,
      "return_pct": 910.662580496156,
      "closed_trade_mdd_pct": -49.40104126277226,
      "hourly_mark_mdd_pct": -56.39014907328291,
      "hourly_adverse_bound_pct": -62.79214505502226,
      "trades": 223,
      "win_rate_pct": 55.60538116591928,
      "margin_clipped": 198,
      "rejected": 7,
      "liquidation_proxy_count": 0,
      "max_reserved_equity_ratio": 1.622237301884449,
      "max_gross_equity_ratio": 5.494155889753049
    },
    {
      "start_usd": 100.0,
      "end_usd": 1086.1347559396356,
      "return_pct": 986.1347559396357,
      "closed_trade_mdd_pct": -46.8075863300343,
      "hourly_mark_mdd_pct": -50.23629193550807,
      "hourly_adverse_bound_pct": -60.48432065317577,
      "trades": 267,
      "win_rate_pct": 53.558052434456926,
      "margin_clipped": 224,
      "rejected": 9,
      "liquidation_proxy_count": 0,
      "max_reserved_equity_ratio": 1.2104600455114454,
      "max_gross_equity_ratio": 5.79015653692194
    }
  ],
  "double_cost": {
    "start_usd": 100.0,
    "end_usd": 21709.632815981055,
    "return_pct": 21609.632815981055,
    "closed_trade_mdd_pct": -62.08160644622289,
    "hourly_mark_mdd_pct": -63.07989337848734,
    "hourly_adverse_bound_pct": -64.51459930740499,
    "trades": 760,
    "win_rate_pct": 52.23684210526316,
    "margin_clipped": 657,
    "rejected": 20,
    "liquidation_proxy_count": 0,
    "max_reserved_equity_ratio": 1.6181742948323108,
    "max_gross_equity_ratio": 6.308352412692216
  },
  "extra_trades": 103,
  "same_hour_entries": 0,
  "preliminary_pass": true
}

Details: ../b_complement_stage17/results.json
