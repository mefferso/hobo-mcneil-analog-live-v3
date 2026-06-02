"""Secondary regression guidance for active-rise situations.

This is intentionally diagnostic. It is not allowed to create a flood crest
forecast when the hydrograph state says the creek is flat, falling, or unclear.
"""

from __future__ import annotations


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def attenuation_factor(h0_stage_ft: float) -> float:
    """Dampen future remaining rise when the event starts from an elevated baseline."""
    h0 = _as_float(h0_stage_ft)
    if h0 <= 8.0:
        return 1.0
    return max(0.55, min(1.0, 1.0 - 0.08 * (h0 - 8.0)))


def active_rise_regression_guidance(live: dict) -> dict:
    """Return diagnostic regression crest guidance for active-rise states only."""
    state = str(live.get("hydrograph_state", ""))
    if state not in {"ACTIVE_RISE", "ACTIVE_ELEVATED_RISE"}:
        stage = _as_float(live.get("stage_ft"))
        return {
            "enabled": False,
            "reason": f"hydrograph_state={state}; regression disabled outside active rise",
            "raw_regression_crest_ft": None,
            "attenuation_factor": None,
            "projected_crest_ft": round(stage, 2),
        }

    stage = _as_float(live.get("stage_ft"))
    h0 = _as_float(live.get("h0_stage_ft"), stage)
    vmax3 = max(
        _as_float(live.get("max_r3_so_far_ft_per_hr")),
        _as_float(live.get("r3_ft_per_hr")),
    )
    vmax6 = max(
        _as_float(live.get("max_r6_so_far_ft_per_hr")),
        _as_float(live.get("r6_ft_per_hr")),
    )

    # Conservative blend: 3-hr rate is the earlier operational signal; 6-hr rate
    # is better volume evidence once available. Do not use this alone without
    # backtesting; it is a second opinion against the analog forecast.
    raw_r3_crest = 8.54 + 0.82 * h0 + 12.45 * vmax3
    raw_r6_crest = 7.12 + 19.32 * vmax6
    raw = max(raw_r3_crest, raw_r6_crest)

    raw_remaining = max(0.0, raw - stage)
    cf = attenuation_factor(h0)
    projected = stage + raw_remaining * cf

    return {
        "enabled": True,
        "reason": "active rise diagnostic; remaining rise attenuated by baseline stage",
        "raw_regression_crest_ft": round(raw, 2),
        "attenuation_factor": round(cf, 2),
        "projected_crest_ft": round(projected, 2),
        "vmax3_used_ft_per_hr": round(vmax3, 3),
        "vmax6_used_ft_per_hr": round(vmax6, 3),
    }
