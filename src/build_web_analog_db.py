"""Build a compact JSON analog database for browser what-if mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analog_matcher import FEATURE_WEIGHTS, load_analog_snapshots
from config import ANALOG_SNAPSHOT_CSV, WEB_DATA_DIR

KEEP_COLUMNS = [
    "event_id",
    "snapshot_datetime",
    "stage_ft",
    "h0_stage_ft",
    "rise_so_far_ft",
    "r1_ft_per_hr",
    "r3_ft_per_hr",
    "r6_ft_per_hr",
    "max_r1_so_far_ft_per_hr",
    "max_r3_so_far_ft_per_hr",
    "max_r6_so_far_ft_per_hr",
    "max_accel_3hr_so_far",
    "momentum_r1_minus_r3",
    "elapsed_hr_since_rise_start",
    "analog_crest_ft",
    "analog_remaining_rise_ft",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build docs/data/event_snapshots_web.json")
    parser.add_argument("--analog-csv", default=str(ANALOG_SNAPSHOT_CSV))
    parser.add_argument("--out", default=str(WEB_DATA_DIR / "event_snapshots_web.json"))
    args = parser.parse_args()

    df = load_analog_snapshots(args.analog_csv)
    keep = [c for c in KEEP_COLUMNS if c in df.columns]
    out_df = df[keep].copy()

    for c in out_df.select_dtypes(include="number").columns:
        out_df[c] = out_df[c].round(4)

    payload = {
        "description": "Compact historical analog snapshot database for browser what-if mode.",
        "feature_weights": [
            {"feature": f, "weight": w, "scale": s} for f, w, s in FEATURE_WEIGHTS
        ],
        "rows": out_df.to_dict(orient="records"),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {len(out_df)} analog rows to {out_path}")


if __name__ == "__main__":
    main()
