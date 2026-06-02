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
    max_r1_so_far_ft_per_hr: float
    max_r3_so_far_ft_per_hr: float
    max_r6_so_far_ft_per_hr: float
    max_accel_3hr_so_far: float
    hydrograph_state: str
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


def classify_hydrograph_state(
    stage_ft: float,
    rise_so_far_ft: float,
    elapsed_hr_since_rise_start: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
) -> str:
    """Classify the current hydrograph into decision-logic states."""
    s = float(stage_ft)
    rise = float(rise_so_far_ft)
    e = float(elapsed_hr_since_rise_start)
    r1 = float(r1_ft_per_hr)
    r3 = float(r3_ft_per_hr)
    r6 = float(r6_ft_per_hr)

    if s < 12.0 and rise <= 0.25 and e <= 1.0 and r1 <= 0.0 and r3 <= 0.0 and r6 <= 0.0:
        return "LOW_FLAT_FALLING"
    if r1 <= 0.0 and r3 <= 0.0 and r6 <= 0.0:
        return "FALLING_OR_RECESSION"
    if s >= 12.0 and r6 >= 0.30:
        return "ACTIVE_ELEVATED_RISE"
    if r3 >= 0.30 or r6 >= 0.20 or (r1 >= 0.50 and r3 > 0.0):
        return "ACTIVE_RISE"
    return "WEAK_OR_UNCLEAR_RISE"


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


def peak_rate_features_since_start(
    hourly: pd.Series,
    rise_start_time: pd.Timestamp,
) -> dict[str, float]:
    """Return max R1/R3/R6 and max 3-hr acceleration since the detected rise start."""
    hourly = hourly.dropna().sort_index().astype(float)
    rates = pd.DataFrame({
        "r1": hourly.diff(1),
        "r3": hourly.diff(3) / 3.0,
        "r6": hourly.diff(6) / 6.0,
    })
    rates["accel3"] = rates["r3"].diff(1)

    active = rates[rates.index >= rise_start_time]
    if active.empty:
        active = rates.tail(1)

    def _positive_max(series: pd.Series) -> float:
        value = series.max(skipna=True)
        if pd.isna(value):
            return 0.0
        return max(0.0, float(value))

    return {
        "max_r1_so_far_ft_per_hr": _positive_max(active["r1"]),
        "max_r3_so_far_ft_per_hr": _positive_max(active["r3"]),
        "max_r6_so_far_ft_per_hr": _positive_max(active["r6"]),
        "max_accel_3hr_so_far": _positive_max(active["accel3"]),
    }


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
    peak_rates = peak_rate_features_since_start(hourly, rise_start_time)
    hydrograph_state = classify_hydrograph_state(current, rise_so_far, elapsed, r1, r3, r6)

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
        max_r1_so_far_ft_per_hr=round(peak_rates["max_r1_so_far_ft_per_hr"], 3),
        max_r3_so_far_ft_per_hr=round(peak_rates["max_r3_so_far_ft_per_hr"], 3),
        max_r6_so_far_ft_per_hr=round(peak_rates["max_r6_so_far_ft_per_hr"], 3),
        max_accel_3hr_so_far=round(peak_rates["max_accel_3hr_so_far"], 3),
        hydrograph_state=hydrograph_state,
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
    hydrograph_state = classify_hydrograph_state(
        stage_ft=float(stage_ft),
        rise_so_far_ft=rise_so_far,
        elapsed_hr_since_rise_start=float(elapsed_hr_since_rise_start),
        r1_ft_per_hr=float(r1_ft_per_hr),
        r3_ft_per_hr=float(r3_ft_per_hr),
        r6_ft_per_hr=float(r6_ft_per_hr),
    )
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
        max_r1_so_far_ft_per_hr=round(max(0.0, float(r1_ft_per_hr)), 3),
        max_r3_so_far_ft_per_hr=round(max(0.0, float(r3_ft_per_hr)), 3),
        max_r6_so_far_ft_per_hr=round(max(0.0, float(r6_ft_per_hr)), 3),
        max_accel_3hr_so_far=round(max(0.0, float(momentum_r1_minus_r3)), 3),
        hydrograph_state=hydrograph_state,
        rise_start_time_utc="manual",
    )
