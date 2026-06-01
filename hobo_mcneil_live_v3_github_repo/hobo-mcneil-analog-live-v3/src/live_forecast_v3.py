"""Run live Hobo/McNeil analog forecast and write dashboard-ready outputs.

Default live run:
    python src/live_forecast_v3.py

Local test using a CSV of recent stage data:
    python src/live_forecast_v3.py --stage-csv data/stage_data_hourly.csv

Manual what-if:
    python src/live_forecast_v3.py --manual-stage 13.8 --manual-h0 10.2 --manual-r1 0.9 --manual-r3 0.7 --manual-r6 0.45 --manual-elapsed 8
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from analog_matcher import load_analog_snapshots, run_analog_forecast
from analog_v3_guardrails import apply_v3_decision_logic
from config import (
    ANALOG_SNAPSHOT_CSV,
    GAGE_NAME,
    NWS_GAUGE_ID,
    OUTPUT_DIR,
    TOP_N_ANALOG_EVENTS,
    USGS_LOOKBACK_DAYS,
    USGS_PARAMETER,
    USGS_SITE,
)
from fetch_current_usgs import fetch_usgs_iv
from hydro_features import build_features_from_stage_df, build_manual_features, read_stage_csv


def crest_category(stage: float) -> str:
    if stage < 15:
        return "below flood stage"
    if stage < 18:
        return "minor flood potential"
    if stage < 22:
        return "moderate flood potential"
    return "major flood potential"


def run(args: argparse.Namespace) -> dict:
    analog_path = Path(args.analog_csv or ANALOG_SNAPSHOT_CSV)
    analog_df = load_analog_snapshots(analog_path)

    source = "USGS live"
    hourly_rows = []

    if args.manual_stage is not None:
        required = [args.manual_h0, args.manual_r1, args.manual_r3, args.manual_r6, args.manual_elapsed]
        if any(v is None for v in required):
            raise SystemExit(
                "Manual mode requires --manual-h0 --manual-r1 --manual-r3 --manual-r6 --manual-elapsed"
            )
        features = build_manual_features(
            stage_ft=args.manual_stage,
            h0_stage_ft=args.manual_h0,
            r1_ft_per_hr=args.manual_r1,
            r3_ft_per_hr=args.manual_r3,
            r6_ft_per_hr=args.manual_r6,
            elapsed_hr_since_rise_start=args.manual_elapsed,
            momentum_r1_minus_r3=args.manual_momentum,
            valid_time_utc=args.manual_time_utc,
        )
        source = "manual override"
    else:
        if args.stage_csv:
            stage_df = read_stage_csv(args.stage_csv)
            source = f"local CSV: {args.stage_csv}"
        else:
            stage_df = fetch_usgs_iv(
                site=args.usgs_site,
                parameter=args.usgs_parameter,
                days=args.lookback_days,
            )
            source = f"USGS IV site={args.usgs_site} parameter={args.usgs_parameter}"
        features, hourly = build_features_from_stage_df(stage_df)
        hourly_tail = hourly.tail(12).reset_index()
        hourly_tail.columns = ["datetime_utc", "stage_ft"]
        hourly_rows = [
            {"datetime_utc": str(r["datetime_utc"]), "stage_ft": round(float(r["stage_ft"]), 2)}
            for _, r in hourly_tail.iterrows()
        ]

    live = features.to_dict()
    analog = run_analog_forecast(
        analog_df=analog_df,
        live_features=live,
        top_n_events=args.top_n,
        dedupe_by_event=not args.no_dedupe,
    )
    analog_dict = analog.to_dict()

    v3 = apply_v3_decision_logic(
        stage_ft=live["stage_ft"],
        r1_ft_per_hr=live["r1_ft_per_hr"],
        r3_ft_per_hr=live["r3_ft_per_hr"],
        r6_ft_per_hr=live["r6_ft_per_hr"],
        elapsed_hr_since_rise_start=live["elapsed_hr_since_rise_start"],
        momentum_r1_minus_r3=live["momentum_r1_minus_r3"],
        most_likely_crest_ft=analog_dict["most_likely_crest_ft"],
        p75_top_analog_ft=analog_dict["p75_top_analog_ft"],
        p90_top_analog_ft=analog_dict["p90_top_analog_ft"],
        analog_max_ft=analog_dict["analog_max_ft"],
    )

    decision = v3["decision_crest_ft"]
    payload = {
        "gage": {
            "name": GAGE_NAME,
            "nws_gauge_id": NWS_GAUGE_ID,
            "usgs_site": args.usgs_site,
            "usgs_parameter": args.usgs_parameter,
        },
        "source": source,
        "valid_time_utc": live["valid_time_utc"],
        "current_state": live,
        "analog_forecast": analog_dict,
        "v3_decision": v3,
        "headline": {
            "decision_crest_ft": decision,
            "most_likely_crest_ft": analog_dict["most_likely_crest_ft"],
            "crest_category": crest_category(decision),
            "confidence": v3["confidence"],
            "method": v3["decision_method"],
        },
        "recent_hourly_stage": hourly_rows,
        "notes": [
            "Decision-support only. This is not an official NWS river forecast.",
            "V3 decision crest intentionally leans conservative when elevated/still-rising signals are present.",
            "Official AHPS/NWC/NWS guidance should remain the authoritative forecast source.",
        ],
    }
    return payload


def write_outputs(payload: dict, out_dir: str | Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "current_forecast.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    analogs = pd.DataFrame(payload["analog_forecast"]["top_analogs"])
    analogs.to_csv(out_dir / "current_analogs.csv", index=False)

    one_line = {
        "valid_time_utc": payload["valid_time_utc"],
        "current_stage_ft": payload["current_state"]["stage_ft"],
        "r1_ft_per_hr": payload["current_state"]["r1_ft_per_hr"],
        "r3_ft_per_hr": payload["current_state"]["r3_ft_per_hr"],
        "r6_ft_per_hr": payload["current_state"]["r6_ft_per_hr"],
        "momentum_r1_minus_r3": payload["current_state"]["momentum_r1_minus_r3"],
        "elapsed_hr_since_rise_start": payload["current_state"]["elapsed_hr_since_rise_start"],
        "most_likely_crest_ft": payload["analog_forecast"]["most_likely_crest_ft"],
        "decision_crest_v3_ft": payload["v3_decision"]["decision_crest_ft"],
        "confidence": payload["v3_decision"]["confidence"],
        "decision_method": payload["v3_decision"]["decision_method"],
    }
    pd.DataFrame([one_line]).to_csv(out_dir / "current_forecast.csv", index=False)

    print(f"Wrote {json_path}")
    print(json.dumps(payload["headline"], indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live V3 analog crest forecast")
    parser.add_argument("--analog-csv", default=str(ANALOG_SNAPSHOT_CSV))
    parser.add_argument("--out-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--top-n", type=int, default=TOP_N_ANALOG_EVENTS)
    parser.add_argument("--no-dedupe", action="store_true", help="Do not dedupe top analogs by event_id")

    parser.add_argument("--usgs-site", default=USGS_SITE)
    parser.add_argument("--usgs-parameter", default=USGS_PARAMETER)
    parser.add_argument("--lookback-days", type=int, default=USGS_LOOKBACK_DAYS)
    parser.add_argument("--stage-csv", default=None, help="Use local recent stage CSV instead of fetching USGS")

    parser.add_argument("--manual-stage", type=float, default=None)
    parser.add_argument("--manual-h0", type=float, default=None)
    parser.add_argument("--manual-r1", type=float, default=None)
    parser.add_argument("--manual-r3", type=float, default=None)
    parser.add_argument("--manual-r6", type=float, default=None)
    parser.add_argument("--manual-elapsed", type=float, default=None)
    parser.add_argument("--manual-momentum", type=float, default=None)
    parser.add_argument("--manual-time-utc", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    write_outputs(payload, args.out_dir)


if __name__ == "__main__":
    main()
