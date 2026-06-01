"""Fetch current/recent USGS instantaneous gage-height data."""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from config import USGS_PARAMETER, USGS_SITE, USGS_LOOKBACK_DAYS

USGS_IV_ENDPOINT = "https://waterservices.usgs.gov/nwis/iv/"


def fetch_usgs_iv(
    site: str = USGS_SITE,
    parameter: str = USGS_PARAMETER,
    days: int = USGS_LOOKBACK_DAYS,
    timeout: int = 30,
) -> pd.DataFrame:
    """Return dataframe with datetime_utc and stage_ft from USGS IV JSON."""
    params = {
        "format": "json",
        "sites": site,
        "parameterCd": parameter,
        "period": f"P{days}D",
        "siteStatus": "all",
    }
    url = f"{USGS_IV_ENDPOINT}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "hobo-mcneil-analog-forecast/1.0"})

    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    series = payload.get("value", {}).get("timeSeries", [])
    if not series:
        raise RuntimeError(f"No USGS timeSeries returned for site={site}, parameter={parameter}")

    values = series[0].get("values", [])
    if not values or not values[0].get("value"):
        raise RuntimeError(f"No USGS values returned for site={site}, parameter={parameter}")

    rows = []
    for item in values[0]["value"]:
        raw_value = item.get("value")
        raw_time = item.get("dateTime")
        if raw_value in (None, "", "Ice", "Eqp") or raw_time is None:
            continue
        try:
            rows.append({
                "datetime_utc": pd.to_datetime(raw_time, utc=True),
                "stage_ft": float(raw_value),
            })
        except ValueError:
            continue

    if not rows:
        raise RuntimeError("USGS returned data, but no numeric gage-height values were parseable")

    df = pd.DataFrame(rows).drop_duplicates("datetime_utc").sort_values("datetime_utc")
    return df.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch recent USGS gage-height data")
    parser.add_argument("--site", default=USGS_SITE)
    parser.add_argument("--parameter", default=USGS_PARAMETER)
    parser.add_argument("--days", type=int, default=USGS_LOOKBACK_DAYS)
    parser.add_argument("--out", default="stage_data_recent_usgs.csv")
    args = parser.parse_args()

    df = fetch_usgs_iv(args.site, args.parameter, args.days)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")
    print(df.tail().to_string(index=False))


if __name__ == "__main__":
    main()
