"""
fetch_isc.py
------------
Downloads the Kutch region earthquake catalog from the ISC (International
Seismological Centre) FDSN Event Web Service and saves it to:
    data/raw/kutch_isc.csv

ISC FDSN endpoint : http://www.isc.ac.uk/fdsnws/event/1/
Format            : text (pipe-delimited — ISC does NOT support GeoJSON)
Coverage          : global, 1900-present; M2-3 events that USGS misses

Response format (pipe-delimited, header line starts with #):
  EventID | Time | Latitude | Longitude | Depth/km | Author | Catalog |
  Contributor | ContributorID | MagType | Magnitude | MagAuthor |
  EventLocationName | EventType

Bounding box  : 22.0-24.5 N, 68.0-71.5 E
Time range    : 1990-01-01 to present
Min magnitude : 2.0

Pagination
----------
Year-by-year with orderby=time-asc (prevents boundary gaps).
ISC reviewed bulletin has a ~2-year lag; recent years will return fewer events.
"""

import io
import time
import sys
from datetime import date
from pathlib import Path

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BBOX = dict(minlatitude=22.0, maxlatitude=24.5, minlongitude=68.0, maxlongitude=71.5)
MIN_MAG    = 2.0
START_YEAR = 1990
END_YEAR   = date.today().year
ENDPOINT   = "http://www.isc.ac.uk/fdsnws/event/1/query"
OUT_PATH   = Path(__file__).parent.parent / "data" / "raw" / "kutch_isc.csv"

# ISC text format column names (header line prefixed with #, pipe-separated)
ISC_COLS = [
    "isc_event_id", "time_utc", "latitude", "longitude", "depth_km",
    "author", "catalog", "contributor", "contributor_id",
    "mag_type", "magnitude", "mag_author",
    "place", "event_type",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "trikaal-seismic-eda/1.0 (research)"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _query_year(year: int) -> pd.DataFrame:
    """
    Fetch all events for a single calendar year from ISC FDSN (text format).
    Returns a DataFrame with ISC_COLS columns (empty DataFrame if no events).
    """
    params = {
        "format":       "text",
        "starttime":    f"{year}-01-01",
        "endtime":      f"{year}-12-31",
        "minmagnitude": MIN_MAG,
        "orderby":      "time-asc",   # prevents boundary gaps
        **BBOX,
    }
    resp = SESSION.get(ENDPOINT, params=params, timeout=120)
    resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        print(f"  {year}:     0 events retrieved")
        return pd.DataFrame(columns=ISC_COLS)

    # Check for error response (ISC returns 200 with "Error 4xx" in body)
    if text.startswith("Error"):
        print(f"  {year}: ISC error — {text[:120]}", file=sys.stderr)
        return pd.DataFrame(columns=ISC_COLS)

    lines = text.splitlines()

    # ---- Parse header ----
    # Header line starts with '#'; strip the '#' and split on '|'
    header_line = next((l for l in lines if l.startswith("#")), None)
    if header_line is None:
        print(f"  {year}: no header found", file=sys.stderr)
        return pd.DataFrame(columns=ISC_COLS)

    # Data lines are everything that doesn't start with '#'
    data_lines = [l for l in lines if l and not l.startswith("#")]

    if not data_lines:
        print(f"  {year}:     0 events retrieved")
        return pd.DataFrame(columns=ISC_COLS)

    # ---- Read into DataFrame ----
    # Use StringIO so pandas can handle variable numbers of trailing fields
    csv_text = "\n".join(data_lines)
    try:
        df = pd.read_csv(
            io.StringIO(csv_text),
            sep="|",
            header=None,
            names=ISC_COLS,
            dtype=str,
            on_bad_lines="skip",
        )
    except Exception as exc:
        print(f"  {year}: parse error — {exc}", file=sys.stderr)
        return pd.DataFrame(columns=ISC_COLS)

    print(f"  {year}: {len(df):>5} events retrieved")
    if len(df) >= 20_000:
        print(f"  WARNING: {year} hit the 20k cap — consider quarterly splits.")

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    print(f"Fetching Kutch catalog from ISC FDSN {START_YEAR}-{END_YEAR} (M>={MIN_MAG}) ...")
    print("Note: ISC reviewed bulletin has a ~2-year lag; recent years will be sparse.\n")

    for year in range(START_YEAR, END_YEAR + 1):
        try:
            df_year = _query_year(year)
            if not df_year.empty:
                frames.append(df_year)
        except requests.HTTPError as exc:
            print(f"  ERROR {year}: {exc}", file=sys.stderr)
        except requests.exceptions.ReadTimeout:
            print(f"  TIMEOUT {year} — retrying once ...", file=sys.stderr)
            time.sleep(5)
            try:
                df_year = _query_year(year)
                if not df_year.empty:
                    frames.append(df_year)
            except Exception as exc2:
                print(f"  Retry failed {year}: {exc2}", file=sys.stderr)
        time.sleep(1.0)   # ISC asks for polite request rates

    if not frames:
        print("No data returned. Check network or ISC service status.", file=sys.stderr)
        return

    df = pd.concat(frames, ignore_index=True)

    # ---- Type conversions ----
    df["latitude"]   = pd.to_numeric(df["latitude"],   errors="coerce")
    df["longitude"]  = pd.to_numeric(df["longitude"],  errors="coerce")
    df["depth_km"]   = pd.to_numeric(df["depth_km"],   errors="coerce")
    df["magnitude"]  = pd.to_numeric(df["magnitude"],  errors="coerce")
    df["time_utc"]   = pd.to_datetime(df["time_utc"],  utc=True, errors="coerce")

    # ---- Rename isc_event_id -> id for compatibility with preprocess.py ----
    df["id"]     = "isc_" + df["isc_event_id"].astype(str)
    df["source"] = "isc"

    # Standardise column names to match USGS schema
    df.rename(columns={"magnitude": "magnitude", "mag_type": "mag_type"}, inplace=True)
    # Add stub columns present in USGS CSV (so concat works cleanly)
    for col in ["status", "net", "nst", "dmin", "rms", "gap", "updated_utc", "url", "type"]:
        if col not in df.columns:
            df[col] = pd.NA

    # ---- Deduplicate within ISC itself ----
    before = len(df)
    df.drop_duplicates(subset="id", inplace=True)
    if len(df) != before:
        print(f"Removed {before - len(df)} intra-ISC duplicate IDs.")

    # ---- Drop missing critical fields ----
    df.dropna(subset=["time_utc", "latitude", "longitude", "magnitude"], inplace=True)

    df.sort_values("time_utc", inplace=True)
    df.reset_index(drop=True, inplace=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(df):,} ISC events -> {OUT_PATH}")
    print(df[["time_utc", "latitude", "longitude", "depth_km", "magnitude"]].describe().round(3))


if __name__ == "__main__":
    main()
