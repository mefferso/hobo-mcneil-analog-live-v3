const forecastUrl = 'output/current_forecast.json';
const analogDbUrl = 'data/event_snapshots_web.json';

let latestForecast = null;
let analogDb = null;

const featureWeights = [
  ['stage_ft', 1.35, 2.00],
  ['rise_so_far_ft', 1.20, 2.00],
  ['r1_ft_per_hr', 0.90, 0.70],
  ['r3_ft_per_hr', 1.45, 0.55],
  ['r6_ft_per_hr', 1.35, 0.40],
  ['momentum_r1_minus_r3', 0.80, 0.45],
  ['elapsed_hr_since_rise_start', 0.85, 10.00],
  ['h0_stage_ft', 0.45, 2.50],
];

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}

function setStatus(message, isError = false) {
  const el = document.getElementById('statusMessage');
  el.textContent = message;
  el.className = isError ? 'notice bad' : 'notice';
}

function metric(label, value, sub = '') {
  return `<div class="metric"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`;
}

function rowsFromObject(obj, mapping) {
  return mapping.map(([label, key, digits, suffix = '']) => {
    const value = typeof key === 'function' ? key(obj) : obj[key];
    const display = typeof value === 'number' ? `${fmt(value, digits)}${suffix}` : `${value ?? '—'}${suffix}`;
    return `<tr><th>${label}</th><td>${display}</td></tr>`;
  }).join('');
}

function renderForecast(data) {
  latestForecast = data;
  const headline = data.headline || {};
  const state = data.current_state || {};
  const analog = data.analog_forecast || {};
  const v3 = data.v3_decision || {};

  document.getElementById('forecastGrid').innerHTML = [
    metric('V3 decision crest', `${fmt(headline.decision_crest_ft)} ft`, headline.crest_category || ''),
    metric('Most likely analog crest', `${fmt(headline.most_likely_crest_ft)} ft`, 'weighted mean analog'),
    metric('Current stage', `${fmt(state.stage_ft)} ft`, data.valid_time_utc || ''),
    metric('Confidence', headline.confidence || '—', headline.method || ''),
  ].join('');
  document.getElementById('forecastGrid').classList.remove('hidden');
  setStatus(`Loaded ${data.gage?.name || 'forecast'} from ${data.source || 'unknown source'}`);

  document.getElementById('stateTable').innerHTML = rowsFromObject(state, [
    ['Valid time UTC', 'valid_time_utc'],
    ['Stage', 'stage_ft', 2, ' ft'],
    ['H0 / rise-start stage', 'h0_stage_ft', 2, ' ft'],
    ['Rise so far', 'rise_so_far_ft', 2, ' ft'],
    ['Elapsed rise time', 'elapsed_hr_since_rise_start', 1, ' hr'],
    ['R1', 'r1_ft_per_hr', 3, ' ft/hr'],
    ['R3', 'r3_ft_per_hr', 3, ' ft/hr'],
    ['R6', 'r6_ft_per_hr', 3, ' ft/hr'],
    ['Momentum R1-R3', 'momentum_r1_minus_r3', 3, ' ft/hr'],
    ['Rise start UTC', 'rise_start_time_utc'],
  ]);

  document.getElementById('decisionTable').innerHTML = rowsFromObject({ ...analog, ...v3 }, [
    ['Decision crest', 'decision_crest_ft', 2, ' ft'],
    ['Decision method', 'decision_method'],
    ['Most likely crest', 'most_likely_crest_ft', 2, ' ft'],
    ['Analog min/max', o => `${fmt(o.analog_min_ft)} / ${fmt(o.analog_max_ft)} ft`],
    ['P75 / P90 analog crest', o => `${fmt(o.p75_top_analog_ft)} / ${fmt(o.p90_top_analog_ft)} ft`],
    ['V3 floor remaining', 'v3_floor_remaining_ft', 2, ' ft'],
    ['V3 major flag', o => o.v3_major_potential_flag ? 'YES' : 'no'],
    ['Confidence', 'confidence'],
  ]);
  document.getElementById('decisionReason').textContent = v3.confidence_reason || v3.v3_major_potential_reason || '';

  renderAnalogTable(analog.top_analogs || [], 'analogTable');
}

function renderAnalogTable(rows, tableId) {
  const table = document.getElementById(tableId);
  if (!rows.length) {
    table.innerHTML = '<tr><td>No analogs available.</td></tr>';
    return;
  }
  table.innerHTML = `
    <thead><tr>
      <th>Event</th><th>Snapshot</th><th>Stage</th><th>R1</th><th>R3</th><th>R6</th><th>Elapsed</th><th>Observed crest</th><th>Score</th>
    </tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${r.event_id ?? ''}</td>
        <td>${r.snapshot_datetime ?? ''}</td>
        <td>${fmt(r.stage_ft)} ft</td>
        <td>${fmt(r.r1_ft_per_hr, 3)}</td>
        <td>${fmt(r.r3_ft_per_hr, 3)}</td>
        <td>${fmt(r.r6_ft_per_hr, 3)}</td>
        <td>${fmt(r.elapsed_hr_since_rise_start, 1)}</td>
        <td>${fmt(r.observed_crest_ft ?? r.analog_crest_ft)} ft</td>
        <td>${fmt(r.score, 3)}</td>
      </tr>`).join('')}
    </tbody>`;
}

async function loadForecast() {
  try {
    const response = await fetch(`${forecastUrl}?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Missing ${forecastUrl}. Run the GitHub Action or live_forecast_v3.py first.`);
    const data = await response.json();
    renderForecast(data);
  } catch (err) {
    setStatus(err.message, true);
  }
}

async function loadAnalogDb() {
  if (analogDb) return analogDb;
  const response = await fetch(`${analogDbUrl}?t=${Date.now()}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Missing ${analogDbUrl}. Run build_web_analog_db.py first.`);
  analogDb = await response.json();
  return analogDb;
}

function scoreRow(row, live) {
  let score = 0;
  let used = 0;
  for (const [feature, weight, scale] of featureWeights) {
    const lv = Number(live[feature]);
    const av = Number(row[feature]);
    if (!Number.isFinite(lv) || !Number.isFinite(av)) continue;
    score += weight * Math.abs(lv - av) / scale;
    used += 1;
  }
  return score + (featureWeights.length - used) * 0.25;
}

function percentile(values, p) {
  if (!values.length) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

function weightedMean(values, scores) {
  let num = 0;
  let den = 0;
  for (let i = 0; i < values.length; i++) {
    const w = 1 / Math.pow(scores[i] + 0.25, 2);
    num += values[i] * w;
    den += w;
  }
  return num / den;
}

function applyV3(live, analog) {
  const s = live.stage_ft;
  const r1 = live.r1_ft_per_hr;
  const r3 = live.r3_ft_per_hr;
  const r6 = live.r6_ft_per_hr;
  const e = live.elapsed_hr_since_rise_start;
  const mom = live.momentum_r1_minus_r3;

  let floor = 0;
  if (r1 <= -0.05 && r3 <= 0.00 && r6 <= 0.05) floor = 0;
  else {
    if (s >= 12 && r6 >= 0.30 && e <= 36) floor = Math.max(floor, 3.0);
    if (s >= 14 && r6 >= 0.20 && e <= 48) floor = Math.max(floor, 3.0);
    if (s >= 16 && r6 >= 0.10 && e <= 60) floor = Math.max(floor, 2.5);
    if (s >= 18 && r6 >= 0.05) floor = Math.max(floor, 1.5);
    if (s >= 11 && r3 >= 0.60 && e <= 30) floor = Math.max(floor, 3.0);
    if (s >= 12 && r1 >= 0.75 && mom >= 0.20 && e <= 30) floor = Math.max(floor, 3.5);
    if (e > 48 && r6 < 0.15) floor = Math.min(floor, 1.5);
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
  let decision = Math.max(analog.most_likely_crest_ft, analog.p75_top_analog_ft);
  let method = 'P75_TOP_ANALOG_BASELINE';
  if (major) {
    decision = Math.max(decision, analog.p90_top_analog_ft, s + floor);
    method = 'V3_MAJOR_POTENTIAL_P90_PLUS_STAGE_FLOOR';
  }
  const spread = analog.analog_max_ft - Math.min(analog.most_likely_crest_ft, analog.p75_top_analog_ft);
  const confidence = major ? (spread >= 3 ? 'LOW' : 'MEDIUM') : (spread >= 4 ? 'LOW' : 'MEDIUM');

  return {
    decision_crest_ft: Number(decision.toFixed(2)),
    decision_method: method,
    confidence,
    v3_floor_remaining_ft: Number(floor.toFixed(2)),
    reason: major ? reasons.join('; ') : 'no V3 major-potential trigger',
  };
}

function runAnalogJs(live, rows) {
  const scored = rows.map(r => ({ ...r, score: scoreRow(r, live) })).filter(r => Number.isFinite(r.score));
  scored.sort((a, b) => a.score - b.score);

  const seen = new Set();
  const top = [];
  for (const r of scored) {
    if (seen.has(r.event_id)) continue;
    seen.add(r.event_id);
    top.push(r);
    if (top.length >= 7) break;
  }

  const crests = top.map(r => Number(r.analog_crest_ft));
  const scores = top.map(r => Number(r.score));
  const analog = {
    most_likely_crest_ft: Number(weightedMean(crests, scores).toFixed(2)),
    analog_min_ft: Math.min(...crests),
    analog_max_ft: Math.max(...crests),
    median_top_analog_ft: Number(percentile(crests, 0.50).toFixed(2)),
    p75_top_analog_ft: Number(percentile(crests, 0.75).toFixed(2)),
    p90_top_analog_ft: Number(percentile(crests, 0.90).toFixed(2)),
    top_analogs: top.map(r => ({ ...r, observed_crest_ft: r.analog_crest_ft, score: Number(r.score.toFixed(3)) })),
  };
  const v3 = applyV3(live, analog);
  return { analog, v3 };
}

function fillManualFromCurrent() {
  if (!latestForecast) return;
  const s = latestForecast.current_state;
  document.getElementById('mStage').value = s.stage_ft;
  document.getElementById('mH0').value = s.h0_stage_ft;
  document.getElementById('mElapsed').value = s.elapsed_hr_since_rise_start;
  document.getElementById('mR1').value = s.r1_ft_per_hr;
  document.getElementById('mR3').value = s.r3_ft_per_hr;
  document.getElementById('mR6').value = s.r6_ft_per_hr;
}

async function runManual() {
  const db = await loadAnalogDb();
  const live = {
    stage_ft: Number(document.getElementById('mStage').value),
    h0_stage_ft: Number(document.getElementById('mH0').value),
    elapsed_hr_since_rise_start: Number(document.getElementById('mElapsed').value),
    r1_ft_per_hr: Number(document.getElementById('mR1').value),
    r3_ft_per_hr: Number(document.getElementById('mR3').value),
    r6_ft_per_hr: Number(document.getElementById('mR6').value),
  };
  live.rise_so_far_ft = Math.max(0, live.stage_ft - live.h0_stage_ft);
  live.momentum_r1_minus_r3 = live.r1_ft_per_hr - live.r3_ft_per_hr;

  if (Object.values(live).some(v => !Number.isFinite(v))) {
    document.getElementById('manualOutput').innerHTML = '<p class="bad">Fill in all manual fields first.</p>';
    return;
  }

  const result = runAnalogJs(live, db.rows || []);
  document.getElementById('manualOutput').innerHTML = `
    <div class="grid">
      ${metric('Manual V3 decision crest', `${fmt(result.v3.decision_crest_ft)} ft`, result.v3.confidence)}
      ${metric('Manual most likely', `${fmt(result.analog.most_likely_crest_ft)} ft`, 'weighted mean')}
      ${metric('Manual P75 / P90', `${fmt(result.analog.p75_top_analog_ft)} / ${fmt(result.analog.p90_top_analog_ft)} ft`, 'top analogs')}
      ${metric('V3 method', result.v3.decision_method, result.v3.reason)}
    </div>
    <h3>Manual top analogs</h3>
    <div class="tableWrap"><table id="manualAnalogTable"></table></div>
  `;
  renderAnalogTable(result.analog.top_analogs, 'manualAnalogTable');
}

document.getElementById('refreshBtn').addEventListener('click', loadForecast);
document.getElementById('fillManualBtn').addEventListener('click', fillManualFromCurrent);
document.getElementById('runManualBtn').addEventListener('click', () => runManual().catch(err => {
  document.getElementById('manualOutput').innerHTML = `<p class="bad">${err.message}</p>`;
}));

loadForecast();
