# Hobo/McNeil Analog Crest Forecast - Live V3 Dashboard

This repo turns the V3 analog crest model into a GitHub-hosted operational situational-awareness dashboard.

**Architecture:**

```text
USGS current stage data
        ↓
Python fetch + hourly resample
        ↓
current hydrograph features: stage, R1/R3/R6, momentum, elapsed rise time
        ↓
historical analog matching against data/event_snapshots.csv
        ↓
V3 decision-crest guardrails
        ↓
docs/output/current_forecast.json
        ↓
GitHub Pages dashboard
```

This is **decision support only**. It is not an official NWS river forecast product.

---

## What you need from your existing files

Based on the files you already have, this is the clean split.

### Copy into this repo

Put this in `data/`:

```text
event_snapshots.csv
```

That is the key file. It is the analog library.

Optional but useful to keep in `data/archive/` or your repo for future development:

```text
historical_events.csv
event_summary_features.csv
stage_data_hourly.csv
hobo_mcneil_analog_dataset.csv
```

### You do not need for the live dashboard

These are backtest/development outputs, not live inputs:

```text
analog_backtest_by_elapsed_hour.csv
analog_forecast_v2_output.csv
backtest_v2_by_crest_threshold.csv
backtest_v2_by_elapsed_hour.csv
backtest_v2_by_event.csv
backtest_v3_all_snapshots.csv
backtest_v3_by_crest_threshold.csv
backtest_v3_by_event.csv
backtest_v3_summary.txt
fetch_report.csv
```

### Optional smoke-test shortcut

If you cannot find the original `event_snapshots.csv` immediately, copy this instead:

```text
backtest_v2_all_snapshots.csv → data/event_snapshots.csv
```

That has enough columns for the live analog matcher. Long term, use the original event snapshot database.

---

## Repo structure

```text
hobo-mcneil-analog-live-v3/
│
├── .github/
│   └── workflows/
│       └── update_forecast.yml
│
├── data/
│   ├── README.md
│   └── event_snapshots.csv              # YOU ADD THIS
│
├── docs/                                # GitHub Pages site
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── output/
│   │   ├── current_forecast.json        # generated
│   │   ├── current_forecast.csv         # generated
│   │   └── current_analogs.csv          # generated
│   └── data/
│       └── event_snapshots_web.json     # generated for browser what-if mode
│
├── src/
│   ├── analog_matcher.py
│   ├── analog_v3_guardrails.py
│   ├── build_web_analog_db.py
│   ├── config.py
│   ├── fetch_current_usgs.py
│   ├── hydro_features.py
│   └── live_forecast_v3.py
│
├── requirements.txt
└── README.md
```

---

## Install locally first

From the repo folder:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

On Mac/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Add your analog data

Copy your analog snapshot database here:

```text
data/event_snapshots.csv
```

The script expects columns like:

```text
event_id
snapshot_datetime or datetime
stage_ft
h0_stage_ft
rise_so_far_ft
r1_ft_per_hr
r3_ft_per_hr
r6_ft_per_hr
momentum_r1_minus_r3
elapsed_hr_since_rise_start
observed_peak_stage_ft or actual_crest_ft or listed_crest_stage_ft
```

The script is flexible with the crest column name, because your previous outputs used a few names.

---

## Run a local live forecast

```powershell
py src/live_forecast_v3.py
```

That will:

1. fetch recent USGS gage-height data,
2. resample to hourly,
3. calculate R1/R3/R6/momentum/elapsed,
4. match historical analogs,
5. apply V3 guardrails,
6. write dashboard files to `docs/output/`.

Generated files:

```text
docs/output/current_forecast.json
docs/output/current_forecast.csv
docs/output/current_analogs.csv
```

Then build the browser analog database:

```powershell
py src/build_web_analog_db.py
```

Generated file:

```text
docs/data/event_snapshots_web.json
```

---

## Local manual what-if run

```powershell
py src/live_forecast_v3.py --manual-stage 13.8 --manual-h0 10.2 --manual-r1 0.9 --manual-r3 0.7 --manual-r6 0.45 --manual-elapsed 8
```

If you omit `--manual-momentum`, the script computes:

```text
momentum = R1 - R3
```

---

## Test with a local stage CSV instead of live USGS

```powershell
py src/live_forecast_v3.py --stage-csv data/stage_data_hourly.csv
```

The stage CSV needs a datetime column and a stage column. Accepted names include:

```text
datetime_utc, datetime, time, timestamp
stage_ft, gage_height_ft, value
```

---

## Publish with GitHub Pages

1. Create a new GitHub repo.
2. Upload/push this full folder.
3. Make sure `data/event_snapshots.csv` is included.
4. Go to **Settings → Pages**.
5. Under **Build and deployment**, choose:

```text
Source: Deploy from a branch
Branch: main
Folder: /docs
```

6. Save.
7. Open the **Actions** tab.
8. Run **Update Hobo/McNeil Analog Forecast** manually once.
9. After it succeeds, your dashboard should show the current forecast.

The workflow runs every 15 minutes, but GitHub scheduled actions are best-effort. It is not a warning-ops-grade real-time scheduler.

---

## What the dashboard shows

- Current stage
- H0 / rise-start stage
- Rise so far
- R1 / R3 / R6
- Momentum
- Elapsed rise time
- Most likely analog crest
- V3 decision crest
- Confidence
- V3 trigger reason
- Top analog events
- Browser-based manual what-if mode

---

## Important operational notes

The `decision_crest_ft` is the number meant for conservative situational awareness.

The `most_likely_crest_ft` is the raw weighted analog answer.

Do not treat the weighted analog mean as the operational safety number during larger/elevated rises. That is exactly how V1/V2 got into underforecast trouble.

V3 uses:

```text
decision = max(most_likely, P75 analog)
```

Then, if elevated/still-rising major-potential triggers are present:

```text
decision = max(decision, P90 analog, stage + remaining-rise floor)
```

That is the whole damn point.
