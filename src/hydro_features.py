"""Build current hydrograph features from recent stage observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from config import HOURLY_RESAMPLE_RULE, MIN_TOTAL_RISE_FT, RISE_LOOKBACK_HOURS


@dataclass
class HydroFeatures:
    valid_time_utc: str
    current_stage_ft: float
    stage_ft: float
    h0_stage_ft: float
    rise_so_far_ft: float
    elapsed_hr_since_rise_start: float
    r1_ft_per_hr: float
    r3_ft_per_hr: float
    r6_ft_per_hr: float
    momentum_r1_minus_r3: float
    rise_start_time_utc: str

    def to_dict(self) -> dict:
        return asdict(self)


def read_stage_csv(path: str | Path) -> pd.DataFrame:
    """Read a local stage CSV with flexible datetime/stage column names."""
    df = pd.read_csv(path)
    lower_map = {c.lower().strip(): c for c in df.columns}

    datetime_col = None
    for candidate in ["datetime_utc", "datetime", "date_time", "time", "valid_time_utc", "timestamp"]:
        if candidate in lower_map:
            datetime_col = lower_map[candidate]
            break

    stage_col = None
    for candidate in ["stage_ft", "gage_height_ft", "gage height, feet", "height_ft", "value"]:
        if candidate in lower_map:
            stage_col = lower_map[candidate]
            break

    if datetime_col is None or stage_col is None:
        raise ValueError(
            "Could not identify datetime/stage columns. Expected datetime_utc/datetime/time "
            "and stage_ft/gage_height_ft/value."
        )

    out = pd.DataFrame({
        "datetime_utc": pd.to_datetime(df[datetime_col], utc=True),
        "stage_ft": pd.to_numeric(df[stage_col], errors="coerce"),
    }).dropna()
    return out.drop_duplicates("datetime_utc").sort_values("datetime_utc").reset_index(drop=True)


def to_hourly_stage_series(df: pd.DataFrame) -> pd.Series:
    """Resample observations to hourly using last value in each hour."""
    if df.empty:
        raise ValueError("No stage data supplied")
    temp = df.copy()
    temp["datetime_utc"] = pd.to_datetime(temp["datetime_utc"], utc=True)
    temp["stage_ft"] = pd.to_numeric(temp["stage_ft"], errors="coerce")
    temp = temp.dropna(subset=["datetime_utc", "stage_ft"]).sort_values("datetime_utc")
    s = temp.set_index("datetime_utc")["stage_ft"].astype(float)
    hourly = s.resample(HOURLY_RESAMPLE_RULE).last().interpolate(limit=2)
    return hourly.dropna()


def _hours_between(later: pd.Timestamp, earlier: pd.Timestamp) -> float:
    return max(0.0, (later - earlier).total_seconds() / 3600.0)


def _stage_hours_ago(hourly: pd.Series, latest_time: pd.Timestamp, hours: int) -> float:
    target = latest_time - pd.Timedelta(hours=hours)
    val = hourly.asof(target)
    if pd.isna(val):
        # Not enough lookback. Use oldest available stage, which makes rates less aggressive.
        return float(hourly.iloc[0])
    return float(val)


def detect_rise_start(
    hourly: pd.Series,
    lookback_hours: int = RISE_LOOKBACK_HOURS,
    min_total_rise_ft: float = MIN_TOTAL_RISE_FT,
) -> tuple[pd.Timestamp, float, float]:
    """
    Find the most recent local low before a sustained rise.

    This is intentionally explainable, not fancy: look back up to 96 hours, find
    the most recent local basin that has since risen at least min_total_rise_ft.
    If the river is not meaningfully rising, use the latest time/stage.
    """
    hourly = hourly.dropna().sort_index()
    latest_time = hourly.index[-1]
    current = float(hourly.iloc[-1])
    start_cutoff = latest_time - pd.Timedelta(hours=lookback_hours)
    window = hourly[hourly.index >= start_cutoff]

    if len(window) < 4 or current - float(window.min()) < min_total_rise_ft:
        return latest_time, current, 0.0

    values = window.values
    idxs = list(window.index)

    # Scan backward so we grab the current active rise rather than an older event.
    for i in range(len(values) - 4, -1, -1):
        cand = float(values[i])
        if current - cand < min_total_rise_ft:
            continue

        # Local basin check within +/- 3 hours.
        left = max(0, i - 3)
        right = min(len(values), i + 4)
        local_min = float(values[left:right].min())
        if cand > local_min + 0.05:
            continue

        # Require some follow-through shortly after the candidate low.
        j = min(len(values) - 1, i + 3)
        if float(values[j]) >= cand + 0.15 or current >= cand + min_total_rise_ft:
            start_time = idxs[i]
            elapsed = _hours_between(latest_time, start_time)
            return start_time, cand, elapsed

    start_time = window.idxmin()
    h0 = float(window.loc[start_time])
    elapsed = _hours_between(latest_time, start_time)
    return start_time, h0, elapsed


def build_features_from_stage_df(df: pd.DataFrame) -> tuple[HydroFeatures, pd.Series]:
    """Return current features and the hourly stage series used to compute them."""
    hourly = to_hourly_stage_series(df)
    if len(hourly) < 2:
        raise ValueError("Need at least two hourly stage values to compute features")

    latest_time = hourly.index[-1]
    current = float(hourly.iloc[-1])

    s1 = _stage_hours_ago(hourly, latest_time, 1)
    s3 = _stage_hours_ago(hourly, latest_time, 3)
    s6 = _stage_hours_ago(hourly, latest_time, 6)

    r1 = current - s1
    r3 = (current - s3) / 3.0
    r6 = (current - s6) / 6.0
    momentum = r1 - r3

    rise_start_time, h0, elapsed = detect_rise_start(hourly)
    rise_so_far = max(0.0, current - h0)

    features = HydroFeatures(
        valid_time_utc=latest_time.isoformat(),
        current_stage_ft=round(current, 2),
        stage_ft=round(current, 2),
        h0_stage_ft=round(h0, 2),
        rise_so_far_ft=round(rise_so_far, 2),
        elapsed_hr_since_rise_start=round(elapsed, 2),
        r1_ft_per_hr=round(r1, 3),
        r3_ft_per_hr=round(r3, 3),
        r6_ft_per_hr=round(r6, 3),
        momentum_r1_minus_r3=round(momentum, 3),
        rise_start_time_utc=rise_start_time.isoformat(),
    )
    return features, hourly


def build_manual_features(
    stage_ft: float,
    h0_stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    elapsed_hr_since_rise_start: float,
    momentum_r1_minus_r3: float | None = None,
    valid_time_utc: str | None = None,
) -> HydroFeatures:
    """Build features from manual inputs for local what-if testing."""
    if valid_time_utc is None:
        valid_time_utc = pd.Timestamp.utcnow().isoformat()
    if momentum_r1_minus_r3 is None:
        momentum_r1_minus_r3 = float(r1_ft_per_hr) - float(r3_ft_per_hr)
    rise_so_far = max(0.0, float(stage_ft) - float(h0_stage_ft))
    return HydroFeatures(
        valid_time_utc=valid_time_utc,
        current_stage_ft=round(float(stage_ft), 2),
        stage_ft=round(float(stage_ft), 2),
        h0_stage_ft=round(float(h0_stage_ft), 2),
        rise_so_far_ft=round(rise_so_far, 2),
        elapsed_hr_since_rise_start=round(float(elapsed_hr_since_rise_start), 2),
        r1_ft_per_hr=round(float(r1_ft_per_hr), 3),
        r3_ft_per_hr=round(float(r3_ft_per_hr), 3),
        r6_ft_per_hr=round(float(r6_ft_per_hr), 3),
        momentum_r1_minus_r3=round(float(momentum_r1_minus_r3), 3),
        rise_start_time_utc="manual",
    )
