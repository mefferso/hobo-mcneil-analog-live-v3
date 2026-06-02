// Browser what-if patch: summarize analogs by remaining rise from each matched
// snapshot, add that remaining rise to the current/manual stage, and suppress
// analog crest guidance when there is no active rise signal.

const browserFeatureWeightsV32 = [
  ['stage_ft', 1.35, 2.00],
  ['rise_so_far_ft', 1.20, 2.00],
  ['r1_ft_per_hr', 0.60, 0.70],
  ['r3_ft_per_hr', 1.70, 0.50],
  ['r6_ft_per_hr', 1.60, 0.35],
  ['max_r3_so_far_ft_per_hr', 1.15, 0.50],
  ['max_r6_so_far_ft_per_hr', 1.00, 0.35],
  ['max_accel_3hr_so_far', 0.55, 0.30],
  ['momentum_r1_minus_r3', 0.70, 0.45],
  ['elapsed_hr_since_rise_start', 0.85, 10.00],
  ['h0_stage_ft', 0.45, 2.50],
];

function browserScoreRowV32(row, live) {
  let score = 0;
  let used = 0;
  for (const [feature, weight, scale] of browserFeatureWeightsV32) {
    let lv = Number(live[feature]);
    let av = Number(row[feature]);

    if (!Number.isFinite(lv)) {
      if (feature === 'max_r3_so_far_ft_per_hr') lv = Math.max(0, Number(live.r3_ft_per_hr));
      if (feature === 'max_r6_so_far_ft_per_hr') lv = Math.max(0, Number(live.r6_ft_per_hr));
      if (feature === 'max_accel_3hr_so_far') lv = Math.max(0, Number(live.momentum_r1_minus_r3));
    }
    if (!Number.isFinite(av)) {
      if (feature === 'max_r3_so_far_ft_per_hr') av = Math.max(0, Number(row.r3_ft_per_hr));
      if (feature === 'max_r6_so_far_ft_per_hr') av = Math.max(0, Number(row.r6_ft_per_hr));
      if (feature === 'max_accel_3hr_so_far') av = Math.max(0, Number(row.momentum_r1_minus_r3));
    }

    if (!Number.isFinite(lv) || !Number.isFinite(av)) continue;
    score += weight * Math.abs(lv - av) / scale;
    used += 1;
  }
  return score + (browserFeatureWeightsV32.length - used) * 0.25;
}

function browserHydrographStateV32(live) {
  const s = Number(live.stage_ft);
  const rise = Number(live.rise_so_far_ft ?? Math.max(0, live.stage_ft - live.h0_stage_ft));
  const e = Number(live.elapsed_hr_since_rise_start);
  const r1 = Number(live.r1_ft_per_hr);
  const r3 = Number(live.r3_ft_per_hr);
  const r6 = Number(live.r6_ft_per_hr);

  if (s < 12 && rise <= 0.25 && e <= 1 && r1 <= 0 && r3 <= 0 && r6 <= 0) return 'LOW_FLAT_FALLING';
  if (r1 <= 0 && r3 <= 0 && r6 <= 0) return 'FALLING_OR_RECESSION';
  if (s >= 12 && r6 >= 0.30) return 'ACTIVE_ELEVATED_RISE';
  if (r3 >= 0.30 || r6 >= 0.20 || (r1 >= 0.50 && r3 > 0)) return 'ACTIVE_RISE';
  return 'WEAK_OR_UNCLEAR_RISE';
}

window.applyV3 = function applyV3StateAware(live, analog) {
  const s = Number(live.stage_ft);
  const r1 = Number(live.r1_ft_per_hr);
  const r3 = Number(live.r3_ft_per_hr);
  const r6 = Number(live.r6_ft_per_hr);
  const e = Number(live.elapsed_hr_since_rise_start);
  const mom = Number(live.momentum_r1_minus_r3);
  const state = live.hydrograph_state || browserHydrographStateV32(live);

  let floor = 0;
  const floorReasons = [];

  if (r1 <= -0.05 && r3 <= 0.00 && r6 <= 0.05) {
    floor = 0;
    floorReasons.push('hydrograph has likely rolled over');
  } else {
    if (s >= 12 && r6 >= 0.30 && e <= 36) { floor = Math.max(floor, 3.0); floorReasons.push('stage >=12 with strong 6-hr rise'); }
    if (s >= 14 && r6 >= 0.20 && e <= 48) { floor = Math.max(floor, 3.0); floorReasons.push('stage >=14 with sustained rise'); }
    if (s >= 16 && r6 >= 0.10 && e <= 60) { floor = Math.max(floor, 2.5); floorReasons.push('stage >=16 with persistent 6-hr rise'); }
    if (s >= 18 && r6 >= 0.05) { floor = Math.max(floor, 1.5); floorReasons.push('stage >=18 and still rising'); }
    if (s >= 11 && r3 >= 0.60 && e <= 30) { floor = Math.max(floor, 3.0); floorReasons.push('strong 3-hr rise while elevated'); }
    if (s >= 12 && r1 >= 0.75 && mom >= 0.20 && e <= 30) { floor = Math.max(floor, 3.5); floorReasons.push('accelerating elevated rise'); }
    if (e > 48 && r6 < 0.15) { floor = Math.min(floor, 1.5); floorReasons.push('late-event weak 6-hr rise taper'); }
  }

  const reasons = [];
  if (s >= 18 && r6 >= 0.05) reasons.push('stage >=18 ft and still rising');
  if (s >= 16 && r6 >= 0.10 && e <= 60) reasons.push('stage >=16 ft with persistent 6-hr rise');
  if (s >= 14 && r6 >= 0.20 && e <= 48) reasons.push('stage >=14 ft with sustained rise');
  if (s >= 12 && r6 >= 0.30 && e <= 36) reasons.push('stage >=12 ft with strong 6-hr rise');
  if (s >= 11 && r3 >= 0.60 && e <= 30) reasons.push('strong 3-hr rise while elevated');
  if (s >= 12 && r1 >= 0.75 && mom >= 0.20 && e <= 30) reasons.push('accelerating elevated rise');
  if (analog.analog_max_ft >= 22 && analog.p90_top_analog_ft >= 21 && s >= 12 && r6 >= 0.10) reasons.push('major analog present in upper envelope');

  const major = reasons.length > 0;
  const analogAllowed = state === 'ACTIVE_RISE' || state === 'ACTIVE_ELEVATED_RISE';
  const suppressAnalog = !analogAllowed && !major;

  let decision;
  let method;
  if (suppressAnalog) {
    decision = s + floor;
    method = `${state}_HYDROGRAPH_BASELINE`;
  } else {
    decision = Math.max(analog.most_likely_crest_ft, analog.p75_top_analog_ft);
    method = 'P75_TOP_ANALOG_BASELINE';
  }

  if (major) {
    decision = Math.max(decision, analog.p90_top_analog_ft, s + floor);
    method = floorReasons.join('; ').includes('cap') ? 'V3_1_DECEL_AWARE_P90_PLUS_STAGE_FLOOR' : 'V3_MAJOR_POTENTIAL_P90_PLUS_STAGE_FLOOR';
  }

  const spread = analog.analog_max_ft - Math.min(analog.most_likely_crest_ft, analog.p75_top_analog_ft);
  const confidence = major
    ? (spread >= 3 ? 'LOW' : 'MEDIUM')
    : (suppressAnalog && (state === 'LOW_FLAT_FALLING' || state === 'FALLING_OR_RECESSION') ? 'HIGH' : (spread >= 4 ? 'LOW' : 'MEDIUM'));

  return {
    decision_crest_ft: Number(decision.toFixed(2)),
    decision_method: method,
    confidence,
    v3_floor_remaining_ft: Number(floor.toFixed(2)),
    v3_floor_crest_ft: Number((s + floor).toFixed(2)),
    v3_floor_reason: [...new Set(floorReasons)].join('; ') || 'no stage-floor trigger',
    hydrograph_state: state,
    analog_guidance_suppressed: suppressAnalog,
    reason: major
      ? `${reasons.join('; ')}; state=${state}`
      : (suppressAnalog
          ? `hydrograph_state=${state}; analog crest guidance suppressed because no active rise signal is present`
          : `no V3 major-potential trigger; state=${state}`),
  };
};

window.runAnalogJs = function runAnalogJsRemainingRise(live, rows) {
  live.max_r3_so_far_ft_per_hr = Number.isFinite(Number(live.max_r3_so_far_ft_per_hr)) ? Number(live.max_r3_so_far_ft_per_hr) : Math.max(0, Number(live.r3_ft_per_hr));
  live.max_r6_so_far_ft_per_hr = Number.isFinite(Number(live.max_r6_so_far_ft_per_hr)) ? Number(live.max_r6_so_far_ft_per_hr) : Math.max(0, Number(live.r6_ft_per_hr));
  live.max_accel_3hr_so_far = Number.isFinite(Number(live.max_accel_3hr_so_far)) ? Number(live.max_accel_3hr_so_far) : Math.max(0, Number(live.momentum_r1_minus_r3));
  live.hydrograph_state = live.hydrograph_state || browserHydrographStateV32(live);

  const scored = rows
    .map(r => ({ ...r, score: browserScoreRowV32(r, live) }))
    .filter(r => Number.isFinite(r.score));
  scored.sort((a, b) => a.score - b.score);

  const seen = new Set();
  const top = [];
  for (const r of scored) {
    if (seen.has(r.event_id)) continue;
    seen.add(r.event_id);
    top.push(r);
    if (top.length >= 7) break;
  }

  const currentStage = Number(live.stage_ft);
  const projectedCrests = top.map(r => {
    const fromDb = Number(r.analog_remaining_rise_ft);
    const fallback = Number(r.analog_crest_ft) - Number(r.stage_ft);
    const remaining = Math.max(0, Number.isFinite(fromDb) ? fromDb : fallback);
    return currentStage + remaining;
  });
  const scores = top.map(r => Number(r.score));

  const analog = {
    most_likely_crest_ft: Number(weightedMean(projectedCrests, scores).toFixed(2)),
    analog_min_ft: Math.min(...projectedCrests),
    analog_max_ft: Math.max(...projectedCrests),
    median_top_analog_ft: Number(percentile(projectedCrests, 0.50).toFixed(2)),
    p75_top_analog_ft: Number(percentile(projectedCrests, 0.75).toFixed(2)),
    p90_top_analog_ft: Number(percentile(projectedCrests, 0.90).toFixed(2)),
    top_analogs: top.map((r, i) => {
      const fromDb = Number(r.analog_remaining_rise_ft);
      const fallback = Number(r.analog_crest_ft) - Number(r.stage_ft);
      const remaining = Math.max(0, Number.isFinite(fromDb) ? fromDb : fallback);
      return {
        ...r,
        observed_crest_ft: r.analog_crest_ft,
        analog_remaining_rise_ft: Number(remaining.toFixed(2)),
        projected_crest_ft: Number(projectedCrests[i].toFixed(2)),
        score: Number(r.score.toFixed(3)),
      };
    }),
  };

  const v3 = applyV3(live, analog);
  return { analog, v3 };
};

window.renderAnalogTable = function renderAnalogTableRemainingRise(rows, tableId) {
  const table = document.getElementById(tableId);
  if (!rows.length) {
    table.innerHTML = '<tr><td>No analogs available.</td></tr>';
    return;
  }
  table.innerHTML = `
    <thead><tr>
      <th>Event</th><th>Snapshot</th><th>Stage</th><th>R1</th><th>R3</th><th>R6</th><th>Max R3</th><th>Max R6</th><th>Elapsed</th><th>Obs crest</th><th>Rem rise</th><th>Projected</th><th>Score</th>
    </tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${r.event_id ?? ''}</td>
        <td>${shortTime(r.snapshot_datetime)}</td>
        <td>${fmt(r.stage_ft)} ft</td>
        <td>${fmt(r.r1_ft_per_hr, 3)}</td>
        <td>${fmt(r.r3_ft_per_hr, 3)}</td>
        <td>${fmt(r.r6_ft_per_hr, 3)}</td>
        <td>${fmt(r.max_r3_so_far_ft_per_hr, 3)}</td>
        <td>${fmt(r.max_r6_so_far_ft_per_hr, 3)}</td>
        <td>${fmt(r.elapsed_hr_since_rise_start, 1)}</td>
        <td>${fmt(r.observed_crest_ft ?? r.analog_crest_ft)} ft</td>
        <td>${fmt(r.analog_remaining_rise_ft)} ft</td>
        <td>${fmt(r.projected_crest_ft)} ft</td>
        <td>${fmt(r.score, 3)}</td>
      </tr>`).join('')}
    </tbody>`;
};
