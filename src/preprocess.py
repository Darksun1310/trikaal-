"""
preprocess.py
-------------
Loads raw USGS and (optionally) ISC catalogs, merges them, deduplicates by
spatio-temporal proximity, and adds derived columns used throughout the EDA
notebook.

Outputs
-------
data/processed/kutch_clean.csv  -- merged, deduplicated, enriched catalog

Depth categories (ISC/USGS convention)
---------------------------------------
  shallow      :  depth < 70 km
  intermediate : 70 <= depth < 300 km
  deep         : depth >= 300 km

Deduplication strategy
-----------------------
USGS and ISC may report the same physical event under different internal IDs.
Events within +/-60 seconds AND within DUP_DIST_KM (default 15 km, haversine)
are considered duplicates; the USGS entry is preferred.

Why haversine, not degrees?
  0.5 degrees ~ 55 km at Kutch's latitude -- far too coarse for a tightly
  clustered intraplate fault zone where distinct events can sit <10 km apart.
  15 km is a conservative threshold that catches true cross-catalog duplicates
  without collapsing legitimately separate events.
"""

from pathlib import Path
import pandas as pd
import numpy as np

USGS_RAW = Path(__file__).parent.parent / "data" / "raw" / "kutch_usgs.csv"
ISC_RAW  = Path(__file__).parent.parent / "data" / "raw" / "kutch_isc.csv"
OUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "kutch_clean.csv"

# Deduplication thresholds (cross-catalog)
DUP_TIME_SECONDS = 60.0
DUP_DIST_KM      = 15.0   # haversine; 0.5 deg ~ 55 km at Kutch lat -- too coarse


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0

def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """
    Vectorised haversine distance (km) from a single point (lat1, lon1)
    to arrays of points (lat2, lon2).  All inputs in decimal degrees.
    """
    lat1_r = np.radians(lat1)
    lat2_r = np.radians(lat2)
    dlat   = lat2_r - lat1_r
    dlon   = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Depth classification
# ---------------------------------------------------------------------------
def classify_depth(depth_km: pd.Series) -> pd.Series:
    """ISC/USGS standard depth classification."""
    bins   = [-np.inf, 70.0, 300.0, np.inf]
    labels = ["shallow", "intermediate", "deep"]
    return pd.cut(depth_km, bins=bins, labels=labels)


# ---------------------------------------------------------------------------
# Catalog loader
# ---------------------------------------------------------------------------
def _load_csv(path: Path, source_label: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["time_utc", "updated_utc"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    if "source" not in df.columns:
        df["source"] = source_label
    print(f"  {source_label:>5}: {len(df):>6,} events loaded from {path.name}")
    return df


# ---------------------------------------------------------------------------
# Cross-catalog deduplication
# ---------------------------------------------------------------------------
def _drop_cross_catalog_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove ISC rows that are spatio-temporally coincident with a USGS row.
    USGS entries take precedence (preferred authoritative processing).

    Duplicate criterion:
      - Same event time within +/- DUP_TIME_SECONDS
      - Epicentres within DUP_DIST_KM (haversine)

    Note: haversine replaces the old 0.5-degree threshold (~55 km at Kutch
    latitude), which was too coarse for a densely clustered fault zone.
    """
    usgs = df[df["source"] == "usgs"].copy()
    isc  = df[df["source"] == "isc"].copy()

    if isc.empty or usgs.empty:
        return df

    def _is_duplicate(row):
        t = row["time_utc"]
        lo = t - pd.Timedelta(seconds=DUP_TIME_SECONDS)
        hi = t + pd.Timedelta(seconds=DUP_TIME_SECONDS)
        # Step 1: narrow to time window (cheap)
        cands = usgs[(usgs["time_utc"] >= lo) & (usgs["time_utc"] <= hi)]
        if cands.empty:
            return False
        # Step 2: haversine distance filter (exact)
        dist_km = haversine_km(
            row["latitude"], row["longitude"],
            cands["latitude"].values, cands["longitude"].values
        )
        return (dist_km <= DUP_DIST_KM).any()

    print(f"  Checking cross-catalog duplicates (haversine <= {DUP_DIST_KM} km, +/-{DUP_TIME_SECONDS}s) ...", end=" ")
    dup_mask = isc.apply(_is_duplicate, axis=1)
    n_dup = dup_mask.sum()
    print(f"{n_dup} ISC events are duplicates of USGS events -> dropped.")

    isc_clean = isc[~dup_mask]
    return pd.concat([usgs, isc_clean], ignore_index=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not USGS_RAW.exists():
        raise FileNotFoundError(
            f"USGS raw catalog not found: {USGS_RAW}\n"
            "Run `python src/fetch_usgs.py` first."
        )

    frames = []
    print("Loading raw catalogs …")
    frames.append(_load_csv(USGS_RAW, "usgs"))

    if ISC_RAW.exists():
        frames.append(_load_csv(ISC_RAW, "isc"))
    else:
        print("  isc: raw file not found — skipping. Run src/fetch_isc.py to add ISC data.")

    df = pd.concat(frames, ignore_index=True)
    print(f"  Combined before deduplication: {len(df):,} events")

    # ---- Cross-catalog dedup ----
    if len(frames) > 1:
        df = _drop_cross_catalog_duplicates(df)

    # ---- Intra-catalog dedup (by id) ----
    before = len(df)
    df.drop_duplicates(subset="id", inplace=True)
    if len(df) != before:
        print(f"  Dropped {before - len(df)} intra-catalog duplicate IDs.")

    # ---- Drop missing critical fields ----
    n_before = len(df)
    df.dropna(subset=["time_utc", "latitude", "longitude", "magnitude"], inplace=True)
    n_dropped = n_before - len(df)
    if n_dropped:
        print(f"  Dropped {n_dropped} rows with missing time/coords/magnitude.")

    # ---- Fix negative depths (ISC surface-reference artefact) ----
    # Negative depth_km has no physical meaning for crustal earthquakes.
    # Null and drop rather than zero-clip, to avoid polluting the depth distribution.
    neg_depth = (df["depth_km"] < 0).sum()
    if neg_depth:
        df.loc[df["depth_km"] < 0, "depth_km"] = np.nan
        df.dropna(subset=["depth_km"], inplace=True)
        print(f"  Dropped {neg_depth} rows with negative depth (ISC surface-reference artefact).")

    # ---- Sort chronologically ----
    df.sort_values("time_utc", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # ---- Derived columns ----
    df["year"]              = df["time_utc"].dt.year
    df["month"]             = df["time_utc"].dt.month
    df["decade"]            = (df["year"] // 10) * 10
    t0                      = pd.Timestamp("1990-01-01", tz="UTC")
    df["days_since_1990"]   = (df["time_utc"] - t0).dt.total_seconds() / 86_400
    df["depth_cat"]         = classify_depth(df["depth_km"])
    df["magnitude"]         = df["magnitude"].astype(float)
    df["depth_km"]          = df["depth_km"].astype(float)

    # ---- Save ----
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"\n✓ Saved {len(df):,} events → {OUT_PATH}")

    # ---- Summary ----
    print("\n=== Summary stats ===")
    print(df[["magnitude", "depth_km", "year"]].describe().round(2))
    print("\nSource breakdown:")
    print(df["source"].value_counts())
    print("\nDepth category breakdown:")
    print(df["depth_cat"].value_counts())
    print(f"\nDate range: {df['time_utc'].min().date()} → {df['time_utc'].max().date()}")


if __name__ == "__main__":
    main()
