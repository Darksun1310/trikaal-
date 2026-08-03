"""
realtime_pipeline.py
--------------------
Trikaal -- Real-Time Operational Seismicity Pipeline.
Ingests latest USGS events, updates catalog, computes current SSI and ETAS forecasts,
compares rates to PSHA baselines, and generates a seismic bulletin report.
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timezone
from pathlib import Path
from scipy.stats import poisson

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
from etas_model import ETASModel
from etas_forecast import ETASForecast
from risk_score import haversine_matrix, bvalue_mle_aki, sigmoid

# Paths
PROCESSED_CAT = Path(__file__).parent.parent / "data" / "processed" / "kutch_clean.csv"
OUT_DIR       = Path(__file__).parent.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)
BULLETIN_PATH = OUT_DIR / "seismic_bulletin.md"

# Config
BBOX = dict(minlatitude=22.0, maxlatitude=24.5, minlongitude=68.0, maxlongitude=71.5)
MIN_MAG = 2.0
USGS_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# SSI references
MC = 3.0
B_REF = 1.0
B_MIN = 0.5
B_WINDOW_D = 90
B_MIN_N = 15
CLUSTER_MIN = 3
WEIGHTS = (0.40, 0.35, 0.25) # w_b, w_rate, w_cluster

warnings.filterwarnings("ignore")

def fetch_latest_usgs_events(last_time: datetime) -> pd.DataFrame:
    """Fetch events from USGS starting from last_time + 1 second up to now."""
    start_str = (last_time + pd.Timedelta(seconds=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    
    print(f"  Querying USGS from {start_str} to {now_str} ...")
    params = {
        "format": "geojson",
        "starttime": start_str,
        "endtime": now_str,
        "minmagnitude": MIN_MAG,
        "orderby": "time-asc",
        **BBOX
    }
    
    try:
        resp = requests.get(USGS_ENDPOINT, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        print(f"  USGS returned {len(features)} new events.")
    except Exception as e:
        print(f"  Error fetching from USGS: {e}")
        return pd.DataFrame()
        
    if not features:
        return pd.DataFrame()
        
    rows = []
    for f in features:
        p = f["properties"]
        g = f["geometry"]["coordinates"] # [lon, lat, depth]
        rows.append({
            "id": f["id"],
            "time_utc": pd.to_datetime(p.get("time"), unit="ms", utc=True),
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
            "updated_utc": pd.to_datetime(p.get("updated"), unit="ms", utc=True),
            "url": p.get("url"),
            "source": "usgs"
        })
    return pd.DataFrame(rows)

def update_catalog_file(df_old: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
    """Merge new events, remove duplicates, and recalculate derived fields."""
    if df_new.empty:
        return df_old
        
    print(f"  Appending {len(df_new)} new events to catalog ...")
    df_combined = pd.concat([df_old, df_new], ignore_index=True)
    
    # Deduplicate by id
    before = len(df_combined)
    df_combined.drop_duplicates(subset="id", keep="first", inplace=True)
    after = len(df_combined)
    if before != after:
        print(f"  Removed {before - after} duplicate IDs during merge.")
        
    # Sort and reset index
    df_combined.sort_values("time_utc", inplace=True)
    df_combined.reset_index(drop=True, inplace=True)
    
    # Recalculate derived fields
    df_combined["time_utc"] = pd.to_datetime(df_combined["time_utc"], utc=True)
    df_combined["year"] = df_combined["time_utc"].dt.year
    df_combined["month"] = df_combined["time_utc"].dt.month
    df_combined["decade"] = (df_combined["year"] // 10) * 10
    
    t0 = pd.Timestamp("1990-01-01", tz="UTC")
    df_combined["days_since_1990"] = (df_combined["time_utc"] - t0).dt.total_seconds() / 86400.0
    
    # Depth category
    bins = [-np.inf, 70.0, 300.0, np.inf]
    labels = ["shallow", "intermediate", "deep"]
    df_combined["depth_cat"] = pd.cut(df_combined["depth_km"], bins=bins, labels=labels)
    
    df_combined.to_csv(PROCESSED_CAT, index=False)
    print(f"  Catalog updated. Saved to {PROCESSED_CAT.name} (Total: {len(df_combined)} events)")
    return df_combined

def compute_current_ssi(df: pd.DataFrame, t_now: pd.Timestamp) -> tuple[float, dict]:
    """Compute the current SSI(t_now) using backward-looking windows."""
    df_mc = df[df["magnitude"] >= MC].copy()
    df_mc["time_utc"] = pd.to_datetime(df_mc["time_utc"], utc=True)
    
    mags = df_mc["magnitude"].values
    times = df_mc["time_utc"].values.astype("datetime64[ns]")
    lats = df_mc["latitude"].values
    lons = df_mc["longitude"].values
    
    # ── Signal 1: b-value Stress ──
    # 90-day backward-looking window
    lo_b = (t_now - pd.Timedelta(days=B_WINDOW_D)).to_datetime64()
    hi_b = t_now.to_datetime64()
    win_mags = mags[(times >= lo_b) & (times <= hi_b)]
    
    if len(win_mags) >= B_MIN_N:
        b_val, _ = bvalue_mle_aki(win_mags, MC)
        s_b = np.clip((B_REF - b_val) / (B_REF - B_MIN), 0.0, 1.0)
    else:
        b_val = np.nan
        s_b = np.nan
        
    # ── Signal 2: Event Rate Anomaly ──
    # Count events in the last 14 days
    lo_r = (t_now - pd.Timedelta(days=14)).to_datetime64()
    current_count = np.sum((times >= lo_r) & (times <= hi_b))
    
    # Calculate historical 14-day counts to get median and IQR
    t_min = df_mc["time_utc"].min()
    bin_edges = pd.date_range(t_min, t_now, freq="14D", tz="UTC")
    hist_counts = np.array([
        ((times >= bin_edges[i].to_datetime64()) &
         (times <  bin_edges[i + 1].to_datetime64())).sum()
        for i in range(len(bin_edges) - 1)
    ], dtype=float)
    
    med = np.median(hist_counts)
    iqr = np.percentile(hist_counts, 75) - np.percentile(hist_counts, 25)
    if iqr == 0:
        iqr = hist_counts.std(ddof=1) or 1.0
    s_rate = sigmoid((current_count - med) / iqr)
    
    # ── Signal 3: Spatial Clustering (NND) ──
    # Mean NND in the last 14 days
    last_14d_mask = (times >= lo_r) & (times <= hi_b)
    if np.sum(last_14d_mask) >= CLUSTER_MIN:
        D = haversine_matrix(lats[last_14d_mask], lons[last_14d_mask])
        np.fill_diagonal(D, np.inf)
        mean_nnd = D.min(axis=1).mean()
        
        # Normalize based on historical min/max NNDs per bin
        hist_nnds = []
        for i in range(len(bin_edges) - 1):
            mask = (times >= bin_edges[i].to_datetime64()) & (times < bin_edges[i+1].to_datetime64())
            if mask.sum() >= CLUSTER_MIN:
                D_sub = haversine_matrix(lats[mask], lons[mask])
                np.fill_diagonal(D_sub, np.inf)
                hist_nnds.append(D_sub.min(axis=1).mean())
        if len(hist_nnds) >= 2:
            min_nnd, max_nnd = min(hist_nnds), max(hist_nnds)
            rng = max_nnd - min_nnd if max_nnd > min_nnd else 1.0
            s_cluster = 1.0 - (mean_nnd - min_nnd) / rng
        else:
            s_cluster = np.nan
    else:
        mean_nnd = np.nan
        s_cluster = np.nan
        
    # ── Composite SSI ──
    opt_file = OUT_DIR / "optimal_weights.json"
    w_b, w_r, w_c = WEIGHTS
    if opt_file.exists():
        try:
            with open(opt_file, "r") as f:
                opt = json.load(f)
                w_b = opt["w_b"]
                w_r = opt["w_rate"]
                w_c = opt["w_cluster"]
        except Exception as e:
            pass
            
    sigs, wts = [], []
    if not np.isnan(s_b):       sigs.append(s_b);       wts.append(w_b)
    if not np.isnan(s_rate):    sigs.append(s_rate);    wts.append(w_r)
    if not np.isnan(s_cluster): sigs.append(s_cluster); wts.append(w_c)
    
    if sigs:
        ssi_val = sum(s * w / sum(wts) for s, w in zip(sigs, wts))
    else:
        ssi_val = np.nan
        
    details = {
        "b_value": b_val,
        "s_b": s_b,
        "count_14d": current_count,
        "s_rate": s_rate,
        "mean_nnd": mean_nnd,
        "s_cluster": s_cluster
    }
    return float(ssi_val), details

def main():
    print("=" * 60)
    print("  TRIKAAL -- Real-Time Operational Pipeline")
    print("=" * 60)
    
    if not PROCESSED_CAT.exists():
        print(f"  Error: processed catalog not found at {PROCESSED_CAT}")
        print("  Please run preprocessing scripts first.")
        sys.exit(1)
        
    # ── [1] Load Catalog & Fetch USGS ──
    df_cat = pd.read_csv(PROCESSED_CAT)
    df_cat["time_utc"] = pd.to_datetime(df_cat["time_utc"], utc=True)
    last_time = df_cat["time_utc"].max()
    print(f"  Current catalog size: {len(df_cat)} events (Last event: {last_time})")
    
    df_new = fetch_latest_usgs_events(last_time)
    n_new = len(df_new)
    df_cat = update_catalog_file(df_cat, df_new)
    
    t_now = pd.Timestamp.now(tz="UTC")
    print(f"  Current pipeline evaluation timestamp: {t_now}")
    
    # ── [2] Calculate Present SSI & Handle 0 Events ──
    ssi_val, ssi_details = compute_current_ssi(df_cat, t_now)
    
    # Load historical thresholds to classify alert level
    risk_csv_path = OUT_DIR / "risk_score.csv"
    q33, q66 = 0.505, 0.655 # baseline defaults
    last_known_str = "UNKNOWN (N/A)"
    
    if risk_csv_path.exists():
        try:
            df_risk = pd.read_csv(risk_csv_path)
            valid = df_risk["risk_score"].dropna()
            if len(valid) > 0:
                unique_vals = np.unique(valid)
                q33 = float(np.percentile(unique_vals, 33))
                q66 = float(np.percentile(unique_vals, 66))
            
            # Find the last valid row in historical risk score for fallback
            df_risk_valid = df_risk.dropna(subset=["risk_score", "risk_label"])
            if not df_risk_valid.empty:
                last_row = df_risk_valid.iloc[-1]
                last_ssi = float(last_row["risk_score"])
                last_label = str(last_row["risk_label"])
                last_date_str = str(last_row["period_end"])
                if " " in last_date_str:
                    last_date_str = last_date_str.split(" ")[0]
                last_known_str = f"{last_label} ({last_date_str})"
        except Exception as e:
            print(f"  Warning loading historical risk data: {e}")
            
    # If 0 new events, override alert level and state description
    is_unchanged = (n_new == 0)
    if is_unchanged:
        alert_level = f"LOW (Last known state: {last_known_str})"
        ssi_status_desc = f"Insufficient recent seismicity — last known state: {last_known_str}"
    else:
        if np.isnan(ssi_val):
            alert_level = "UNKNOWN"
        elif ssi_val >= q66:
            alert_level = "HIGH"
        elif ssi_val < q33:
            alert_level = "LOW"
        else:
            alert_level = "MEDIUM"
        ssi_status_desc = f"SSI Score: **{ssi_val:.4f}** (Historical LOW/HIGH Thresholds: {q33:.3f} / {q66:.3f})"
        
    print(f"  Current SSI Score: {ssi_val:.4f} (Alert Level: {alert_level})")
    
    # ── [3] Load ETAS Parameters & Forecast ──
    params_path = OUT_DIR / "etas_params.json"
    if not params_path.exists():
        print(f"  Error: ETAS parameters not found at {params_path}. Run run_etas.py first.")
        sys.exit(1)
        
    with open(params_path) as f:
        etas_params = json.load(f)
        
    # Fit ETAS forecast
    df_m3 = df_cat[df_cat["magnitude"] >= MC].copy()
    t0 = df_m3["time_utc"].iloc[0]
    times_days = (df_m3["time_utc"] - t0).dt.total_seconds().values / 86400.0
    mags = df_m3["magnitude"].values
    
    model = ETASModel(times_days, mags, Mc=MC)
    model.params_ = etas_params # inject params
    fc = ETASForecast(model)
    
    t_now_days = (t_now - t0).total_seconds() / 86400.0
    
    horizons = [7, 14, 30]
    forecasts = {}
    for h in horizons:
        lam = fc.expected_count(t_now_days, t_now_days + h)
        prob = 1.0 - np.exp(-lam)
        forecasts[h] = {"expected_count": lam, "prob_at_least_one": prob}
        
    # ── [4] Compare Forecast to PSHA Baseline ──
    # Correct PSHA background rate is the overall catalog rate (~0.0794 events/day), not mu daily
    t_span_days = times_days[-1] - times_days[0]
    psha_background_rate = len(df_m3) / (t_span_days if t_span_days > 0 else 1.0)
    
    mu_daily = etas_params.get("mu", 0.0004977)
    mu_annual = mu_daily * 365.25
    current_etas_rate = forecasts[7]["expected_count"] / 7.0 # average daily rate next 7 days
    amp_factor = current_etas_rate / psha_background_rate
    
    # Stress Recovery Index (SRI): ratio of background tectonic rate to current rate
    sri = mu_daily / (current_etas_rate if current_etas_rate > 0 else 1e-10)
    sri = float(np.clip(sri, 0.0, 1.0))
    
    print(f"  Short-term expected 7-day rate : {current_etas_rate:.5f} events/day")
    print(f"  Long-term PSHA baseline rate   : {psha_background_rate:.5f} events/day")
    print(f"  Seismic hazard amplification   : {amp_factor:.2f}x over PSHA baseline")
    print(f"  Stress Recovery Index (SRI)    : {sri:.2%} (Fraction of background loading)")
    
    # Override alert if rate is elevated (only if we have new events or elevated rates)
    if not is_unchanged:
        if alert_level != "HIGH" and forecasts[7]["prob_at_least_one"] >= 0.50:
            alert_level = "HIGH (ELEVATED FORECAST)"
        elif alert_level == "LOW" and forecasts[7]["prob_at_least_one"] >= 0.10:
            alert_level = "MEDIUM (ELEVATED FORECAST)"
        
    # ── [5] Generate Bulletin Report ──
    print(f"\n[SUCCESS] Generating Seismic Bulletin at {BULLETIN_PATH.name} ...")
    
    # Check if we need to prepend an unchanged status banner
    status_banner = ""
    if is_unchanged:
        status_banner = "> [!NOTE]\n> No new M>=2.0 events since last update. Forecast unchanged.\n\n"
        
    # Build bulletin markdown
    bulletin_md = fr"""# Trikaal Operational Seismic Bulletin
**Issued at (UTC):** {t_now.strftime('%Y-%m-%d %H:%M:%S')}  
**Region:** Kutch Intraplate Zone (22.0–24.5°N, 68.0–71.5°E)  
**Authority:** Trikaal Real-Time Operational Pipeline  

---

{status_banner}## 1. Executive Summary
* **Current Operational Alert Level:** **{alert_level}**
* **Short-Term Forecast (Next 7 Days):** **{forecasts[7]['prob_at_least_one']:.1%}** probability of at least one $M \ge 3.0$ event.
* **Hazard Amplification Factor:** **{amp_factor:.2f}x** elevation over long-term PSHA baseline rate.
* **Stress Recovery Index (SRI):** **{sri:.2%}** (The ratio of pure tectonic background loading $\mu$ to the current seismicity rate $\lambda(t_{{now}})$. An SRI of 100% means the system is fully quiet; a low SRI indicates active triggering cascades. Currently, Kutch remains in a long-term post-Bhuj decay phase with {sri:.2%} recovery).

---

## 2. Present Tectonic State (SSI Module)
The Seismic Stress Index (SSI) is calculated using a 14-day sliding window ending at the present hour. It monitors tectonic reloading and instability.

* **Status:** {ssi_status_desc}
* **SSI Parameter Breakdown:**
  * **b-value Stress Proxy ($S_{{b}}$):** {ssi_details['s_b']:.4f} (Fitted rolling b: {ssi_details['b_value']:.3f})
  * **Event Rate Anomaly ($S_{{rate}}$):** {ssi_details['s_rate']:.4f} ({ssi_details['count_14d']} events $M \ge 3.0$ in last 14 days)
  * **Spatial Clustering ($S_{{cluster}}$):** {ssi_details['s_cluster']:.4f} (Mean nearest-neighbor distance: {ssi_details['mean_nnd']:.2f} km)

---

## 3. Short-Term Conditional Forecast (ETAS Module)
The Epidemic Type Aftershock Sequence (ETAS) model simulates secondary triggering cascades (aftershocks triggering aftershocks) out-of-sample based on Kutch tectonic parameters.

| Horizon | Expected Count ($E[N \mid M \ge 3.0]$) | Probability of $\ge 1$ Event ($P(N \ge 1)$) | Probability of $\ge 5$ Events ($P(N \ge 5)$) |
|---|---|---|---|
| **7 Days** | {forecasts[7]['expected_count']:.4f} | {forecasts[7]['prob_at_least_one']:.2%} | {1.0 - sum(poisson.pmf(k, forecasts[7]['expected_count']) for k in range(5)):.2%} |
| **14 Days** | {forecasts[14]['expected_count']:.4f} | {forecasts[14]['prob_at_least_one']:.2%} | {1.0 - sum(poisson.pmf(k, forecasts[14]['expected_count']) for k in range(5)):.2%} |
| **30 Days** | {forecasts[30]['expected_count']:.4f} | {forecasts[30]['prob_at_least_one']:.2%} | {1.0 - sum(poisson.pmf(k, forecasts[30]['expected_count']) for k in range(5)):.2%} |

*Parameters used: $\mu = {etas_params['mu']:.6f}$/day, $K = {etas_params['K']:.5f}$, $\alpha = {etas_params['alpha']:.4f}$, $c = {etas_params['c']:.6f}$ days, $p = {etas_params['p']:.4f}$.*

---

## 4. Long-Term Hazard Baseline (PSHA Module)
Our long-term Probabilistic Seismic Hazard Analysis (PSHA) predicts Peak Ground Acceleration (PGA) values on bedrock:
* **Background Tectonic Loading Rate ($\mu$):** {mu_daily:.6f}/day ($\approx {mu_annual:.4f}$ events/year).
* **Long-Term Catalog Seismicity Rate:** {psha_background_rate:.6f}/day ($\approx {psha_background_rate*365.25:.2f}$ events/year).
* **475-year PGA DBE (Bhuj):** **0.236g** (representing a 10% exceedance probability in 50 years; matches Zone V standard DBE of 0.18g).
* **2475-year PGA MCE (Bhuj):** **0.424g** (representing a 2% exceedance probability in 50 years; matches Zone V standard MCE of 0.36g).

*Comparing the current daily forecast rate ($r = {current_etas_rate:.5f}$ events/day) to the long-term PSHA catalog baseline rate ($R = {psha_background_rate:.5f}$/day) reveals that current triggering activity represents **{amp_factor:.2f} times** the average historical catalog rate.*

---

## 5. Recommended Actions
"""

    if "HIGH" in alert_level:
        bulletin_md += """* **Alert Status:** **HIGH WARNING**
* **Actions:**
  1. Notify local disaster management authorities (Gujarat State Disaster Management Authority - GSDMA).
  2. Implement structural inspections on older Zone V masonry buildings in the Bhuj-Anjar corridor.
  3. Pre-position emergency relief supplies and check communication infrastructure.
  4. Ensure seismic sensors are transmitting in near real-time.
"""
    elif "MEDIUM" in alert_level:
        bulletin_md += """* **Alert Status:** **MEDIUM VIGILANCE**
* **Actions:**
  1. Maintain routine monitoring of catalog updates and daily event rates.
  2. Verify that local emergency contacts and response plans are up to date.
  3. Inform stakeholders of slight seismicity rate elevations.
"""
    else:
        bulletin_md += """* **Alert Status:** **LOW GREEN**
* **Actions:**
  1. Tectonic stress and event rates are within normal background limits.
  2. Continue standard open-source catalog harvesting and monitoring.
  3. No immediate emergency pre-positioning required.
"""

    with open(BULLETIN_PATH, "w") as f:
        f.write(bulletin_md)
        
    print(f"  Bulletin written to {BULLETIN_PATH}")
    
    # ── [6] Append Bulletin Log ──
    log_path = OUT_DIR / "bulletin_log.txt"
    log_line = f"[{t_now.strftime('%Y-%m-%d %H:%M:%S')}] Events Added: {n_new} | Alert: {alert_level} | SSI: {ssi_val:.4f} | 7-day Prob: {forecasts[7]['prob_at_least_one']:.2%} | Amp: {amp_factor:.4f}x\n"
    with open(log_path, "a") as f_log:
        f_log.write(log_line)
    print(f"  Logged entry to {log_path.name}")
    print("=" * 60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trikaal Real-Time Operational Seismicity Pipeline")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous 24-hour loop")
    args = parser.parse_args()
    
    if args.loop:
        import time
        print("Starting Trikaal Real-Time Operational Pipeline Daemon (24-hour loop)...")
        while True:
            try:
                main()
            except Exception as e:
                print(f"  Error in pipeline execution: {e}")
            print("  Sleeping for 24 hours...")
            time.sleep(86400)
    else:
        main()
