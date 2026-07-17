"""
fetch_usgs.py
-------------
Downloads the Kutch region earthquake catalog from the USGS FDSN Event Web
Service and saves it as a CSV to data/raw/kutch_usgs.csv.

Bounding box  : 22.0–24.5°N, 68.0–71.5°E
Time range    : 1990-01-01 to today
Min magnitude : 2.0
Format        : GeoJSON (flattened to DataFrame)

Pagination strategy
-------------------
USGS caps responses at 20,000 events per request.  To avoid gaps the script
queries year-by-year using orderby=time-asc (ascending within each chunk so
boundary events are not duplicated).
"""

import time
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BBOX = dict(minlatitude=22.0, maxlatitude=24.5, minlongitude=68.0, maxlongitude=71.5)
MIN_MAG = 2.0
START_YEAR = 1990
END_YEAR = date.today().year  # inclusive
ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
OUT_PATH = Path(__file__).parent.parent / "data" / "raw" / "kutch_usgs.csv"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "trikaal-seismic-eda/1.0 (research)"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _query_year(year: int) -> list[dict]:
    """Fetch all events for a single calendar year and return a list of dicts."""
    params = {
        "format": "geojson",
        "starttime": f"{year}-01-01",
        "endtime": f"{year}-12-31",
        "minmagnitude": MIN_MAG,
        "orderby": "time-asc",  # ensures no boundary gaps
        **BBOX,
    }
    resp = SESSION.get(ENDPOINT, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])
    count = data.get("metadata", {}).get("count", len(features))
    print(f"  {year}: {count:>5} events retrieved")
    if count >= 20_000:
        print(f"  WARNING: year {year} hit the 20k cap — consider splitting further.")
    return features


def _features_to_rows(features: list[dict]) -> list[dict]:
    rows = []
    for f in features:
        p = f["properties"]
        g = f["geometry"]["coordinates"]  # [lon, lat, depth]
        rows.append(
            {
                "id": f["id"],
                "time_epoch_ms": p.get("time"),
                "latitude": g[1],
                "longitude": g[0],
                "depth_km": g[2],
                "magnitude": p.get("mag"),
                "mag_type": p.get("magType"),
                "place": p.get("place"),
                "type": p.get("type"),
                "status": p.get("status"),
                "net": p.get("net"),
                "nst": p.get("nst"),
                "dmin": p.get("dmin"),
                "rms": p.get("rms"),
                "gap": p.get("gap"),
                "updated_epoch_ms": p.get("updated"),
                "url": p.get("url"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    print(f"Fetching Kutch catalog {START_YEAR}–{END_YEAR} (M≥{MIN_MAG}) …")

    for year in range(START_YEAR, END_YEAR + 1):
        try:
            features = _query_year(year)
            all_rows.extend(_features_to_rows(features))
        except requests.HTTPError as exc:
            print(f"  ERROR fetching {year}: {exc}", file=sys.stderr)
        time.sleep(0.5)  # be polite to the USGS API

    df = pd.DataFrame(all_rows)

    # ---- Convert epoch ms to UTC datetime ----
    df["time_utc"] = pd.to_datetime(df["time_epoch_ms"], unit="ms", utc=True)
    df["updated_utc"] = pd.to_datetime(df["updated_epoch_ms"], unit="ms", utc=True)
    df.drop(columns=["time_epoch_ms", "updated_epoch_ms"], inplace=True)

    # ---- De-duplicate by event id ----
    before = len(df)
    df.drop_duplicates(subset="id", inplace=True)
    after = len(df)
    if before != after:
        print(f"Removed {before - after} duplicate events during merge.")

    df.sort_values("time_utc", inplace=True)
    df.reset_index(drop=True, inplace=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"\n✓ Saved {len(df):,} events → {OUT_PATH}")
    print(df[["time_utc", "latitude", "longitude", "depth_km", "magnitude"]].describe())


if __name__ == "__main__":
    main()
