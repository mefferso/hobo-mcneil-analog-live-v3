"""
Analog crest forecast V3.1 guardrail logic for Hobo/McNeil.

This module separates the analog most-likely crest from the operational
DECISION crest. The decision crest intentionally leans conservative when the
river is elevated and still rising, because dangerous underforecasting of major
events is the failure mode we most want to avoid.

V3.1 keeps the V3 high-side protection but adds a deceleration-aware limiter.
When the river is already elevated and the short-term rise rate is clearly
weakening versus the broader rise, the stage-floor component is reduced and the
decision crest leans more on the P90 analog envelope instead of forcing an
extra-large remaining rise.
"""

from __future__ import annotations


def _as_float(value: float | int | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def v3_trend_adjustment(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    momentum_r1_minus_r3: float,
) -> tuple[float | None, str]:
    """Return an optional cap for the stage-floor remaining rise."""
    s = _as_float(stage_ft)
    r1 = _as_float(r1_ft_per_hr)
    r3 = _as_float(r3_ft_per_hr)
    r6 = _as_float(r6_ft_per_hr)
    mom = _as_float(momentum_r1_minus_r3)

    if r1 <= -0.05 and r3 <= 0.00 and r6 <= 0.05:
        return 0.0, "hydrograph has likely rolled over"

    clearly_decelerating = (mom <= -0.05) or (r6 - r1 >= 0.20 and r6 >= 0.30)
    weakening = clearly_decelerating or (mom < 0.10) or (r6 - r1 >= 0.05 and r6 >= 0.30)

    if not weakening:
        return None, "no deceleration cap"

    if s >= 18.0 and r6 >= 0.30:
        if clearly_decelerating:
            return 1.25, "high-stage clear deceleration cap"
        return 1.50, "high-stage weakening-rise cap"

    if s >= 16.0 and r6 >= 0.40:
        if clearly_decelerating:
            return 2.00, "elevated-stage clear deceleration cap"
        return 2.50, "elevated-stage weakening-rise cap"

    if s >= 14.0 and r6 >= 0.50:
        if clearly_decelerating:
            return 2.50, "mid-stage clear deceleration cap"
        return 3.50, "mid-stage weakening-rise cap"

    return None, "weakening detected but no floor cap needed"


def v3_remaining_rise_floor(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    elapsed_hr_since_rise_start: float,
    momentum_r1_minus_r3: float,
) -> tuple[float, str]:
    """Explainable stage-aware minimum remaining rise floor."""
    s = _as_float(stage_ft)
    r1 = _as_float(r1_ft_per_hr)
    r3 = _as_float(r3_ft_per_hr)
    r6 = _as_float(r6_ft_per_hr)
    e = _as_float(elapsed_hr_since_rise_start)
    mom = _as_float(momentum_r1_minus_r3)

    floor = 0.0
    floor_reasons: list[str] = []

    cap, cap_reason = v3_trend_adjustment(s, r1, r3, r6, mom)
    if cap == 0.0:
        return 0.0, cap_reason

    if s >= 12.0 and r6 >= 0.30 and e <= 36:
        floor = max(floor, 3.0)
        floor_reasons.append("stage >=12 with strong 6-hr rise")
    if s >= 14.0 and r6 >= 0.20 and e <= 48:
        floor = max(floor, 3.0)
        floor_reasons.append("stage >=14 with sustained rise")
    if s >= 16.0 and r6 >= 0.10 and e <= 60:
        floor = max(floor, 2.5)
        floor_reasons.append("stage >=16 with persistent 6-hr rise")
    if s >= 18.0 and r6 >= 0.05:
        floor = max(floor, 1.5)
        floor_reasons.append("stage >=18 and still rising")

    if s >= 11.0 and r3 >= 0.60 and e <= 30:
        floor = max(floor, 3.0)
        floor_reasons.append("strong 3-hr rise while elevated")
    if s >= 12.0 and r1 >= 0.75 and mom >= 0.20 and e <= 30:
        floor = max(floor, 3.5)
        floor_reasons.append("accelerating elevated rise")

    if e > 48 and r6 < 0.15:
        floor = min(floor, 1.5)
        floor_reasons.append("late-event weak 6-hr rise taper")

    if cap is not None:
        floor = min(floor, cap)
        floor_reasons.append(cap_reason)

    reason = "; ".join(dict.fromkeys(floor_reasons)) if floor_reasons else "no stage-floor trigger"
    return max(0.0, floor), reason


def v3_major_potential_flag(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    elapsed_hr_since_rise_start: float,
    momentum_r1_minus_r3: float,
    analog_max_ft: float | None = None,
    p90_top_analog_ft: float | None = None,
) -> tuple[bool, str]:
    """Return whether V3 should use high-side decision logic and why."""
    s = _as_float(stage_ft)
    r1 = _as_float(r1_ft_per_hr)
    r3 = _as_float(r3_ft_per_hr)
    r6 = _as_float(r6_ft_per_hr)
    e = _as_float(elapsed_hr_since_rise_start)
    mom = _as_float(momentum_r1_minus_r3)
    analog_max = _as_float(analog_max_ft, -999.0) if analog_max_ft is not None else -999.0
    p90 = _as_float(p90_top_analog_ft, -999.0) if p90_top_analog_ft is not None else -999.0

    reasons: list[str] = []

    if s >= 18.0 and r6 >= 0.05:
        reasons.append("stage >=18 ft and still rising")
    if s >= 16.0 and r6 >= 0.10 and e <= 60:
        reasons.append("stage >=16 ft with persistent 6-hr rise")
    if s >= 14.0 and r6 >= 0.20 and e <= 48:
        reasons.append("stage >=14 ft with sustained rise")
    if s >= 12.0 and r6 >= 0.30 and e <= 36:
        reasons.append("stage >=12 ft with strong 6-hr rise")
    if s >= 11.0 and r3 >= 0.60 and e <= 30:
        reasons.append("strong 3-hr rise while elevated")
    if s >= 12.0 and r1 >= 0.75 and mom >= 0.20 and e <= 30:
        reasons.append("accelerating elevated rise")

    if analog_max >= 22.0 and p90 >= 21.0 and s >= 12.0 and r6 >= 0.10:
        reasons.append("major analog present in upper envelope")

    return (
        len(reasons) > 0,
        "; ".join(reasons) if reasons else "no V3 major-potential trigger",
    )


def infer_hydrograph_state(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    elapsed_hr_since_rise_start: float,
) -> str:
    """Fallback state classifier for callers that do not pass hydrograph_state."""
    s = _as_float(stage_ft)
    r1 = _as_float(r1_ft_per_hr)
    r3 = _as_float(r3_ft_per_hr)
    r6 = _as_float(r6_ft_per_hr)
    e = _as_float(elapsed_hr_since_rise_start)
    if s < 12.0 and e <= 1.0 and r1 <= 0.0 and r3 <= 0.0 and r6 <= 0.0:
        return "LOW_FLAT_FALLING"
    if r1 <= 0.0 and r3 <= 0.0 and r6 <= 0.0:
        return "FALLING_OR_RECESSION"
    if s >= 12.0 and r6 >= 0.30:
        return "ACTIVE_ELEVATED_RISE"
    if r3 >= 0.30 or r6 >= 0.20 or (r1 >= 0.50 and r3 > 0.0):
        return "ACTIVE_RISE"
    return "WEAK_OR_UNCLEAR_RISE"


def near_crest_taper_cap(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    max_r3_so_far_ft_per_hr: float | None = None,
    max_r6_so_far_ft_per_hr: float | None = None,
) -> tuple[float | None, str]:
    """
    Cap remaining rise when the creek is elevated and current rise rates have collapsed.

    This targets the backtest failure mode where analog/P90 guidance kept pushing
    20-23 ft crests even after the hydrograph was already flattening near the peak.
    """
    s = _as_float(stage_ft)
    r1 = _as_float(r1_ft_per_hr)
    r3 = _as_float(r3_ft_per_hr)
    r6 = _as_float(r6_ft_per_hr)
    max_r3 = _as_float(max_r3_so_far_ft_per_hr, max(0.0, r3))
    max_r6 = _as_float(max_r6_so_far_ft_per_hr, max(0.0, r6))

    if s < 16.0:
        return None, "near-crest taper not eligible below 16 ft"

    prior_momentum = max_r3 >= 0.45 or max_r6 >= 0.30
    if not prior_momentum:
        return None, "near-crest taper not eligible without prior rise momentum"

    # Hard flattening: very little current rise left, even though the event had
    # real earlier momentum. This should override high analog envelopes.
    if r1 <= 0.05 and r3 <= 0.15 and r6 <= 0.35:
        return 0.75, "hard near-crest flattening taper"

    # Softer taper for the 1-3 hours before crest, when hourly rise is small and
    # the 3/6-hour windows are already weakening.
    if r1 <= 0.12 and r3 <= 0.22 and r6 <= 0.50:
        return 1.50, "near-crest weakening taper"

    # At moderate/major levels, even a slightly stronger 6-hour rate can still be
    # flattening enough to stop using a 3+ ft high-side analog envelope.
    if s >= 19.0 and r1 <= 0.12 and r3 <= 0.25 and r6 <= 0.60:
        return 1.75, "high-stage near-crest taper"

    return None, "no near-crest taper trigger"


def apply_v3_decision_logic(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    elapsed_hr_since_rise_start: float,
    momentum_r1_minus_r3: float,
    most_likely_crest_ft: float,
    p75_top_analog_ft: float,
    p90_top_analog_ft: float,
    analog_max_ft: float | None = None,
    hydrograph_state: str | None = None,
    max_r3_so_far_ft_per_hr: float | None = None,
    max_r6_so_far_ft_per_hr: float | None = None,
) -> dict:
    """Compute V3.1 operational decision crest."""
    floor_remaining, floor_reason = v3_remaining_rise_floor(
        stage_ft,
        r1_ft_per_hr,
        r3_ft_per_hr,
        r6_ft_per_hr,
        elapsed_hr_since_rise_start,
        momentum_r1_minus_r3,
    )
    floor_crest = float(stage_ft) + floor_remaining

    major_flag, major_reason = v3_major_potential_flag(
        stage_ft,
        r1_ft_per_hr,
        r3_ft_per_hr,
        r6_ft_per_hr,
        elapsed_hr_since_rise_start,
        momentum_r1_minus_r3,
        analog_max_ft=analog_max_ft,
        p90_top_analog_ft=p90_top_analog_ft,
    )

    state = hydrograph_state or infer_hydrograph_state(
        stage_ft, r1_ft_per_hr, r3_ft_per_hr, r6_ft_per_hr, elapsed_hr_since_rise_start
    )
    analog_allowed_states = {"ACTIVE_RISE", "ACTIVE_ELEVATED_RISE"}
    suppress_analog = state not in analog_allowed_states and not major_flag

    if suppress_analog:
        decision = floor_crest
        method = f"{state}_HYDROGRAPH_BASELINE"
    else:
        decision = max(float(most_likely_crest_ft), float(p75_top_analog_ft))
        method = "P75_TOP_ANALOG_BASELINE"

    if major_flag:
        decision = max(decision, float(p90_top_analog_ft), floor_crest)
        method = "V3_MAJOR_POTENTIAL_P90_PLUS_STAGE_FLOOR"
        if "cap" in floor_reason:
            method = "V3_1_DECEL_AWARE_P90_PLUS_STAGE_FLOOR"

    taper_remaining, taper_reason = near_crest_taper_cap(
        stage_ft=stage_ft,
        r1_ft_per_hr=r1_ft_per_hr,
        r3_ft_per_hr=r3_ft_per_hr,
        r6_ft_per_hr=r6_ft_per_hr,
        max_r3_so_far_ft_per_hr=max_r3_so_far_ft_per_hr,
        max_r6_so_far_ft_per_hr=max_r6_so_far_ft_per_hr,
    )
    taper_crest = None
    taper_applied = False
    if taper_remaining is not None and not suppress_analog:
        taper_crest = float(stage_ft) + float(taper_remaining)
        if decision > taper_crest:
            decision = taper_crest
            taper_applied = True
            method = f"{method}_NEAR_CREST_TAPER"

    spread = None
    if analog_max_ft is not None:
        spread = float(analog_max_ft) - min(float(most_likely_crest_ft), float(p75_top_analog_ft))

    if major_flag:
        confidence = "LOW" if spread is None or spread >= 3.0 else "MEDIUM"
        confidence_reason = (
            f"V3.1 major-potential trigger: {major_reason}; "
            f"stage-floor={floor_remaining:.2f} ft ({floor_reason}); state={state}"
        )
    elif suppress_analog:
        confidence = "HIGH" if state in {"LOW_FLAT_FALLING", "FALLING_OR_RECESSION"} else "MEDIUM"
        confidence_reason = (
            f"hydrograph_state={state}; analog crest guidance suppressed because no active rise signal is present; "
            "decision held to current hydrograph/stage-floor baseline"
        )
    elif spread is not None and spread >= 4.0:
        confidence = "LOW"
        confidence_reason = f"large analog spread; {major_reason}; state={state}"
    else:
        confidence = "MEDIUM"
        confidence_reason = f"{major_reason}; state={state}"

    if taper_applied:
        confidence_reason = f"{confidence_reason}; near-crest taper applied: {taper_reason}"

    return {
        "decision_crest_ft": round(decision, 2),
        "decision_method": method,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "v3_floor_remaining_ft": round(floor_remaining, 2),
        "v3_floor_crest_ft": round(floor_crest, 2),
        "v3_floor_reason": floor_reason,
        "v3_major_potential_flag": major_flag,
        "v3_major_potential_reason": major_reason,
        "hydrograph_state": state,
        "analog_guidance_suppressed": suppress_analog,
        "near_crest_taper_remaining_cap_ft": None if taper_remaining is None else round(taper_remaining, 2),
        "near_crest_taper_crest_cap_ft": None if taper_crest is None else round(taper_crest, 2),
        "near_crest_taper_applied": taper_applied,
        "near_crest_taper_reason": taper_reason,
    }
