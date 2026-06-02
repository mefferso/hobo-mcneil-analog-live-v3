// Browser what-if patch: summarize analogs by remaining rise from each matched
// snapshot, then add that remaining rise to the current/manual stage. This keeps
// old high-crest events from being pasted directly onto low or falling water.

window.runAnalogJs = function runAnalogJsRemainingRise(live, rows) {
  const scored = rows
    .map(r => ({ ...r, score: scoreRow(r, live) }))
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
      <th>Event</th><th>Snapshot</th><th>Stage</th><th>R1</th><th>R3</th><th>R6</th><th>Elapsed</th><th>Obs crest</th><th>Rem rise</th><th>Projected</th><th>Score</th>
    </tr></thead>
    <tbody>${rows.map(r => `
      <tr>
        <td>${r.event_id ?? ''}</td>
        <td>${shortTime(r.snapshot_datetime)}</td>
        <td>${fmt(r.stage_ft)} ft</td>
        <td>${fmt(r.r1_ft_per_hr, 3)}</td>
        <td>${fmt(r.r3_ft_per_hr, 3)}</td>
        <td>${fmt(r.r6_ft_per_hr, 3)}</td>
        <td>${fmt(r.elapsed_hr_since_rise_start, 1)}</td>
        <td>${fmt(r.observed_crest_ft ?? r.analog_crest_ft)} ft</td>
        <td>${fmt(r.analog_remaining_rise_ft)} ft</td>
        <td>${fmt(r.projected_crest_ft)} ft</td>
        <td>${fmt(r.score, 3)}</td>
      </tr>`).join('')}
    </tbody>`;
};
