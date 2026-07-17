"""
run_etas.py
-----------
Trikaal -- Fit ETAS on the real Kutch catalog and save outputs.

Outputs
-------
  outputs/etas_params.json     -- fitted parameters
  outputs/etas_forecast.csv    -- multi-horizon forecast table
  outputs/etas_rolling.csv     -- 14-day rolling expected counts
"""

from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from etas_model import ETASModel
from etas_forecast import ETASForecast

DATA_PATH = Path(__file__).parent.parent / "data" / "processed" / "kutch_clean.csv"
OUT_DIR   = Path(__file__).parent.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

SEP = "=" * 62


def main():
    print(SEP)
    print("  TRIKAAL -- ETAS Real Catalog Fit")
    print(SEP)

    # ── Load catalog ──────────────────────────────────────────────
    print("\n[1] Loading catalog ...")
    df = pd.read_csv(DATA_PATH)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc", "magnitude", "latitude", "longitude"])
    df = df.sort_values("time_utc").reset_index(drop=True)

    MC = 3.0
    df_mc = df[df["magnitude"] >= MC].reset_index(drop=True)

    t0    = df_mc["time_utc"].iloc[0]
    times = (df_mc["time_utc"] - t0).dt.total_seconds().values / 86400.0
    mags  = df_mc["magnitude"].values

    print(f"    Total events  : {len(df):,}")
    print(f"    M>={MC} events : {len(df_mc):,}")
    print(f"    Magnitude range: {mags.min():.1f} - {mags.max():.1f}")
    print(f"    Catalog span   : {times[-1]:.1f} days  (~{times[-1]/365.25:.1f} years)")
    print(f"    t0             : {t0.date()}")

    large_n = len(df_mc) > ETASModel._PRECOMPUTE_LIMIT
    if large_n:
        print(f"\n    N={len(df_mc):,} > {ETASModel._PRECOMPUTE_LIMIT:,}  -->  chunked mode (slower but memory-safe)")
    else:
        print(f"\n    N={len(df_mc):,} <= {ETASModel._PRECOMPUTE_LIMIT:,}  -->  fast precomputed matrix mode")

    # ── Fit ───────────────────────────────────────────────────────
    print("\n[2] Fitting ETAS model (n_restarts=5) ...")
    print("    This may take a few minutes for a large catalog ...\n")

    model = ETASModel(times, mags, Mc=MC)
    model.fit(n_restarts=5, seed=42)
    fp = model.params_

    print(f"    mu    = {fp['mu']:.6f}  (background rate, events/day)")
    print(f"    K     = {fp['K']:.6f}  (productivity)")
    print(f"    alpha = {fp['alpha']:.4f}  (magnitude scaling)")
    print(f"    c     = {fp['c']:.6f}  (Omori time offset, days)")
    print(f"    p     = {fp['p']:.4f}  (Omori decay exponent)")
    print(f"    -logL = {fp['neg_loglik']:.4f}")

    # Compare p to Omori fit from refit_analysis
    print(f"\n    Cross-check: Omori p from refit_analysis ~ 0.83")
    print(f"    ETAS p = {fp['p']:.4f}  (ETAS captures more structure, expected to differ slightly)")

    # Save params
    params_path = OUT_DIR / "etas_params.json"
    model.save_params(params_path)

    # ── KS goodness-of-fit ────────────────────────────────────────
    print("\n[3] Time-rescaling KS test ...")
    ks_stat, ks_pval = model.time_rescaling_test()
    ks_ok = ks_pval > 0.05
    print(f"    KS statistic : {ks_stat:.4f}")
    print(f"    KS p-value   : {ks_pval:.4f}  {'PASS (>0.05)' if ks_ok else 'MARGINAL/FAIL -- model may need refinement'}")

    # ── Forecasts ─────────────────────────────────────────────────
    print("\n[4] Generating forecasts from end of catalog ...")
    fc  = ETASForecast(model)
    tbl = fc.forecast_table(horizons_days=[1, 7, 14, 30, 90, 180, 365])
    print(tbl.to_string(index=False))

    fc_path = OUT_DIR / "etas_forecast.csv"
    tbl.to_csv(fc_path, index=False)
    print(f"\n    Saved --> {fc_path.name}")

    # ── Rolling 14-day expected counts ────────────────────────────
    print("\n[5] Rolling 14-day forecast (first 50 bins shown) ...")
    rolling = fc.rolling_forecast(window_days=14, step_days=14)
    print(rolling.head(50).to_string(index=False))

    roll_path = OUT_DIR / "etas_rolling.csv"
    rolling.to_csv(roll_path, index=False)
    print(f"\n    Saved --> {roll_path.name}  ({len(rolling)} bins total)")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  ETAS fit complete. Next steps:")
    print("    1. Open outputs/etas_params.json to inspect parameters")
    print("    2. Run risk_score.py to compare composite risk vs ETAS forecast")
    print("    3. Build 02_etas.ipynb with diagnostic plots")
    print(SEP)


if __name__ == "__main__":
    main()
