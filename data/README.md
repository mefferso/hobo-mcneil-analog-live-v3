# Data files

Copy your historical analog database CSV here.

## Required for live forecasting

Recommended filename:

```text
data/event_snapshots.csv
```

Minimum useful columns:

```text
event_id
stage_ft
h0_stage_ft
rise_so_far_ft
r1_ft_per_hr
r3_ft_per_hr
r6_ft_per_hr
momentum_r1_minus_r3
elapsed_hr_since_rise_start
observed_peak_stage_ft OR actual_crest_ft OR listed_crest_stage_ft
snapshot_datetime OR datetime
```

Your existing `event_snapshots.csv` is the best file to use here.

For a quick smoke test only, you can copy `backtest_v2_all_snapshots.csv` to:

```text
data/event_snapshots.csv
```

That file has enough columns to run the live matcher, but the cleaner long-term setup is the original event snapshot database.

## Optional / archive files

These are useful for development and validation, but the live dashboard does not need them:

```text
historical_events.csv
event_summary_features.csv
stage_data_hourly.csv
backtest_v2_all_snapshots.csv
backtest_v3_all_snapshots.csv
backtest_v3_by_event.csv
backtest_v3_by_crest_threshold.csv
```
