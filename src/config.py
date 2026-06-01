from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = ROOT_DIR / "docs"
OUTPUT_DIR = DOCS_DIR / "output"
WEB_DATA_DIR = DOCS_DIR / "data"

# West Hobolochitto Creek near McNeill / McNeil
USGS_SITE = os.getenv("USGS_SITE", "02492360")
USGS_PARAMETER = os.getenv("USGS_PARAMETER", "00065")  # gage height, ft
NWS_GAUGE_ID = os.getenv("NWS_GAUGE_ID", "MNLM6")
GAGE_NAME = os.getenv("GAGE_NAME", "West Hobolochitto Creek near McNeill")

ANALOG_SNAPSHOT_CSV = Path(os.getenv("ANALOG_SNAPSHOT_CSV", DATA_DIR / "event_snapshots.csv"))

# Analog matching defaults
TOP_N_ANALOG_EVENTS = int(os.getenv("TOP_N_ANALOG_EVENTS", "7"))
USGS_LOOKBACK_DAYS = int(os.getenv("USGS_LOOKBACK_DAYS", "4"))
HOURLY_RESAMPLE_RULE = os.getenv("HOURLY_RESAMPLE_RULE", "1h")

# Rise-start detector settings
RISE_LOOKBACK_HOURS = int(os.getenv("RISE_LOOKBACK_HOURS", "96"))
MIN_TOTAL_RISE_FT = float(os.getenv("MIN_TOTAL_RISE_FT", "0.40"))
