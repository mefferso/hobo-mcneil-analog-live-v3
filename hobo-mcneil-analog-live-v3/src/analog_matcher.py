"""Analog matching for Hobo/McNeil current crest forecast."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# feature, weight, scale. Scale is roughly "one meaningful difference".
FEATURE_WEIGHTS: list[tuple[str, float, float]] = [
    ("stage_ft", 1.35, 2.00),
    ("rise_so_far_ft", 1.20, 2.00),
    ("r1_ft_per_hr", 0.90, 0.70),
    ("r3_ft_per_hr", 1.45, 0.55),
    ("r6_ft_per_hr", 1.35, 0.40),
    ("momentum_r1_minus_r3", 0.80, 0.45),
    ("elapsed_hr_since_rise_start", 0.85, 10.00),
    ("h0_stage_ft", 0.45, 2.50),
]


@dataclass
class AnalogForecast:
    most_likely_crest_ft: float
    analog_min_ft: float
    analog_max_ft: float
    median_top_analog_ft: float
    p75_top_analog_ft: float
    p90_top_analog_ft: float
    num_analogs: int
    top_analogs: list[dict[str, Any]]

    def to_dict(self) -> dict:
        return asdict(self)


def load_analog_snapshots(path: str | Path) -> pd.DataFrame:
    """Load and normalize historical event snapshots."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Analog snapshot CSV not found: {path}. Copy your event_snapshots.csv into data/. "
            "For a quick smoke test, you can copy backtest_v2_all_snapshots.csv to data/event_snapshots.csv."
        )

    df = pd.read_csv(path)
    df = df.copy()

    # Flexible datetime name.
    if "snapshot_datetime" not in df.columns:
        if "datetime" in df.columns:
            df["snapshot_datetime"] = df["datetime"]
        elif "valid_time_utc" in df.columns:
            df["snapshot_datetime"] = df["valid_time_utc"]
        else:
            df["snapshot_datetime"] = ""

    # Normalize crest column.
    crest_candidates = [
        "actual_crest_ft",
        "observed_peak_stage_ft",
        "listed_crest_stage_ft",
        "crest_stage_ft",
    ]
    crest_col = next((c for c in crest_candidates if c in df.columns), None)
    if crest_col is None:
        raise ValueError(
            "Analog CSV needs one crest column: actual_crest_ft, observed_peak_stage_ft, "
            "listed_crest_stage_ft, or crest_stage_ft."
        )
    df["analog_crest_ft"] = pd.to_numeric(df[crest_col], errors="coerce")

    required = ["event_id", "stage_ft", "r1_ft_per_hr", "r3_ft_per_hr", "r6_ft_per_hr"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Analog CSV missing required columns: {missing}")

    # Derive optional fields if possible.
    if "rise_so_far_ft" not in df.columns and "h0_stage_ft" in df.columns:
        df["rise_so_far_ft"] = pd.to_numeric(df["stage_ft"], errors="coerce") - pd.to_numeric(df["h0_stage_ft"], errors="coerce")
    if "momentum_r1_minus_r3" not in df.columns:
        df["momentum_r1_minus_r3"] = pd.to_numeric(df["r1_ft_per_hr"], errors="coerce") - pd.to_numeric(df["r3_ft_per_hr"], errors="coerce")
    if "elapsed_hr_since_rise_start" not in df.columns:
        df["elapsed_hr_since_rise_start"] = np.nan
    if "h0_stage_ft" not in df.columns:
        df["h0_stage_ft"] = np.nan

    numeric_cols = [c for c, _, _ in FEATURE_WEIGHTS] + ["analog_crest_ft"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["event_id", "stage_ft", "r1_ft_per_hr", "r3_ft_per_hr", "r6_ft_per_hr", "analog_crest_ft"])
    if df.empty:
        raise ValueError("Analog CSV loaded, but no usable rows remained after cleaning")

    return df.reset_index(drop=True)


def _score_row(row: pd.Series, live: dict) -> float:
    score = 0.0
    used = 0
    for feature, weight, scale in FEATURE_WEIGHTS:
        live_value = live.get(feature)
        analog_value = row.get(feature)
        if live_value is None or pd.isna(live_value) or pd.isna(analog_value):
            continue
        diff = abs(float(live_value) - float(analog_value)) / float(scale)
        score += float(weight) * diff
        used += 1
    if used == 0:
        return float("inf")
    # Mild penalty if some fields were unavailable.
    missing_penalty = (len(FEATURE_WEIGHTS) - used) * 0.25
    return score + missing_penalty


def find_top_analogs(
    analog_df: pd.DataFrame,
    live_features: dict,
    top_n_events: int = 7,
    dedupe_by_event: bool = True,
) -> pd.DataFrame:
    """Score historical snapshots and return top analog events."""
    df = analog_df.copy()
    df["score"] = df.apply(lambda row: _score_row(row, live_features), axis=1)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["score"])
    df = df.sort_values("score", ascending=True)

    if dedupe_by_event:
        # Keep the best snapshot from each event so one storm cannot stuff the ballot box.
        df = df.groupby("event_id", as_index=False, sort=False).first()
        df = df.sort_values("score", ascending=True)

    return df.head(top_n_events).reset_index(drop=True)


def summarize_analogs(top: pd.DataFrame) -> AnalogForecast:
    if top.empty:
        raise ValueError("No analogs found")

    crests = top["analog_crest_ft"].astype(float).to_numpy()
    scores = top["score"].astype(float).to_numpy()
    # Stable inverse-square weighting. The +0.25 prevents one near-perfect match from
    # completely steamrolling the rest of the analog set.
    weights = 1.0 / np.square(scores + 0.25)
    most_likely = float(np.average(crests, weights=weights))

    top_rows = []
    for _, r in top.iterrows():
        top_rows.append({
            "event_id": str(r.get("event_id", "")),
            "snapshot_datetime": str(r.get("snapshot_datetime", "")),
            "stage_ft": round(float(r.get("stage_ft", np.nan)), 2),
            "h0_stage_ft": None if pd.isna(r.get("h0_stage_ft")) else round(float(r.get("h0_stage_ft")), 2),
            "r1_ft_per_hr": round(float(r.get("r1_ft_per_hr", np.nan)), 3),
            "r3_ft_per_hr": round(float(r.get("r3_ft_per_hr", np.nan)), 3),
            "r6_ft_per_hr": round(float(r.get("r6_ft_per_hr", np.nan)), 3),
            "momentum_r1_minus_r3": round(float(r.get("momentum_r1_minus_r3", np.nan)), 3),
            "elapsed_hr_since_rise_start": None if pd.isna(r.get("elapsed_hr_since_rise_start")) else round(float(r.get("elapsed_hr_since_rise_start")), 2),
            "observed_crest_ft": round(float(r.get("analog_crest_ft", np.nan)), 2),
            "score": round(float(r.get("score", np.nan)), 3),
        })

    return AnalogForecast(
        most_likely_crest_ft=round(most_likely, 2),
        analog_min_ft=round(float(np.min(crests)), 2),
        analog_max_ft=round(float(np.max(crests)), 2),
        median_top_analog_ft=round(float(np.percentile(crests, 50)), 2),
        p75_top_analog_ft=round(float(np.percentile(crests, 75)), 2),
        p90_top_analog_ft=round(float(np.percentile(crests, 90)), 2),
        num_analogs=int(len(top)),
        top_analogs=top_rows,
    )


def run_analog_forecast(
    analog_df: pd.DataFrame,
    live_features: dict,
    top_n_events: int = 7,
    dedupe_by_event: bool = True,
) -> AnalogForecast:
    top = find_top_analogs(
        analog_df=analog_df,
        live_features=live_features,
        top_n_events=top_n_events,
        dedupe_by_event=dedupe_by_event,
    )
    return summarize_analogs(top)
