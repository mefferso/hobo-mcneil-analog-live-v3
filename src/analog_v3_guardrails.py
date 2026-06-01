"""
Analog crest forecast V3 guardrail logic for Hobo/McNeil.

This module separates the analog most-likely crest from the operational
DECISION crest. The decision crest intentionally leans conservative when the
river is elevated and still rising, because dangerous underforecasting of major
events is the failure mode we most want to avoid.
"""

from __future__ import annotations


def v3_remaining_rise_floor(
    stage_ft: float,
    r1_ft_per_hr: float,
    r3_ft_per_hr: float,
    r6_ft_per_hr: float,
    elapsed_hr_since_rise_start: float,
    momentum_r1_minus_r3: float,
) -> float:
    """
    Explainable stage-aware minimum remaining rise floor.

    This is not a standalone forecast. It is a safety floor used only when the
    river is elevated and still rising.
    """
    s = float(stage_ft)
    r1 = float(r1_ft_per_hr)
    r3 = float(r3_ft_per_hr)
    r6 = float(r6_ft_per_hr)
    e = float(elapsed_hr_since_rise_start)
    mom = float(momentum_r1_minus_r3)

    floor = 0.0

    # If the hydrograph has clearly rolled over, do not force extra rise.
    if r1 <= -0.05 and r3 <= 0.00 and r6 <= 0.05:
        return 0.0

    # Strong early/mid-rise signals.
    if s >= 12.0 and r6 >= 0.30 and e <= 36:
        floor = max(floor, 3.0)
    if s >= 14.0 and r6 >= 0.20 and e <= 48:
        floor = max(floor, 3.0)
    if s >= 16.0 and r6 >= 0.10 and e <= 60:
        floor = max(floor, 2.5)
    if s >= 18.0 and r6 >= 0.05:
        floor = max(floor, 1.5)

    # Shorter-term acceleration. R1 alone is noisy, so require elevation/momentum.
    if s >= 11.0 and r3 >= 0.60 and e <= 30:
        floor = max(floor, 3.0)
    if s >= 12.0 and r1 >= 0.75 and mom >= 0.20 and e <= 30:
        floor = max(floor, 3.5)

    # Late-event taper if still barely rising after a long duration.
    if e > 48 and r6 < 0.15:
        floor = min(floor, 1.5)

    return max(0.0, floor)


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
    s = float(stage_ft)
    r1 = float(r1_ft_per_hr)
    r3 = float(r3_ft_per_hr)
    r6 = float(r6_ft_per_hr)
    e = float(elapsed_hr_since_rise_start)
    mom = float(momentum_r1_minus_r3)
    analog_max = float(analog_max_ft) if analog_max_ft is not None else -999.0
    p90 = float(p90_top_analog_ft) if p90_top_analog_ft is not None else -999.0

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
) -> dict:
    """Compute V3 operational decision crest."""
    floor_remaining = v3_remaining_rise_floor(
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

    # Baseline: decision guidance should not fall below the 75th percentile of
    # top analogs. This is a modest safety move even outside major triggers.
    decision = max(float(most_likely_crest_ft), float(p75_top_analog_ft))
    method = "P75_TOP_ANALOG_BASELINE"

    if major_flag:
        decision = max(decision, float(p90_top_analog_ft), floor_crest)
        method = "V3_MAJOR_POTENTIAL_P90_PLUS_STAGE_FLOOR"

    spread = None
    if analog_max_ft is not None:
        spread = float(analog_max_ft) - min(float(most_likely_crest_ft), float(p75_top_analog_ft))

    if major_flag:
        confidence = "LOW" if spread is None or spread >= 3.0 else "MEDIUM"
        confidence_reason = (
            f"V3 major-potential trigger: {major_reason}; "
            f"floor_remaining={floor_remaining:.2f} ft"
        )
    elif spread is not None and spread >= 4.0:
        confidence = "LOW"
        confidence_reason = f"large analog spread; {major_reason}"
    else:
        confidence = "MEDIUM"
        confidence_reason = major_reason

    return {
        "decision_crest_ft": round(decision, 2),
        "decision_method": method,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "v3_floor_remaining_ft": round(floor_remaining, 2),
        "v3_floor_crest_ft": round(floor_crest, 2),
        "v3_major_potential_flag": major_flag,
        "v3_major_potential_reason": major_reason,
    }
