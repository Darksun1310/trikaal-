"""
validate_forecasts.py
---------------------
Performs retrospective forecast validation of the ETAS model on a testing period.
Calculates Brier Score, information gain, AUC-ROC, and generates calibration plots.
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import poisson
def compute_roc_curve(y_true, y_score):
    """Compute Receiver Operating Characteristic (ROC) curve using numpy."""
    if len(y_true) == 0:
        return np.array([0.0, 1.0]), np.array([0.0, 1.0])
    
    # Sort scores descending
    desc_score_indices = np.argsort(y_score)[::-1]
    y_score = y_score[desc_score_indices]
    y_true = y_true[desc_score_indices]
    
    # Distinct thresholds
    distinct_value_indices = np.where(np.diff(y_score))[0]
    threshold_idxs = np.r_[distinct_value_indices, y_true.size - 1]
    
    tps = np.cumsum(y_true)[threshold_idxs]
    fps = 1 + threshold_idxs - tps
    
    tps = np.r_[0, tps]
    fps = np.r_[0, fps]
    
    tpr = tps / tps[-1] if tps[-1] > 0 else np.zeros_like(tps)
    fpr = fps / fps[-1] if fps[-1] > 0 else np.zeros_like(fps)
    return fpr, tpr

def compute_roc_auc(y_true, y_score):
    """Compute Area Under the ROC Curve (AUC) using numpy."""
    if len(np.unique(y_true)) < 2:
        return np.nan
    fpr, tpr = compute_roc_curve(y_true, y_score)
    # Custom trapezoidal integration to support NumPy 2.0+ where np.trapz is removed
    auc = 0.0
    for i in range(len(fpr) - 1):
        auc += 0.5 * (tpr[i] + tpr[i+1]) * (fpr[i+1] - fpr[i])
    return float(np.abs(auc))

from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
from etas_model import ETASModel
from etas_forecast import ETASForecast

# Paths
DATA_PATH = Path(__file__).parent.parent / "data" / "processed" / "kutch_clean.csv"
OUT_DIR   = Path(__file__).parent.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

warnings.filterwarnings("ignore")

def main():
    print("=" * 60)
    print("  TRIKAAL -- ETAS Forecast Validation")
    print("=" * 60)
    
    # ── Load catalog ──────────────────────────────────────────────
    print("[1] Loading catalog ...")
    df = pd.read_csv(DATA_PATH)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc", "magnitude", "latitude", "longitude"])
    df = df.sort_values("time_utc").reset_index(drop=True)
    
    MC = 3.0
    df_mc = df[df["magnitude"] >= MC].reset_index(drop=True)
    t0 = df_mc["time_utc"].iloc[0]
    
    # Times in days from t0
    df_mc["t_days"] = (df_mc["time_utc"] - t0).dt.total_seconds() / 86400.0
    times = df_mc["t_days"].values
    mags  = df_mc["magnitude"].values
    
    # Split into Train (1991 - 2017) and Test (2018 - 2025)
    split_date = pd.Timestamp("2018-01-01", tz="UTC")
    train_mask = df_mc["time_utc"] < split_date
    test_mask  = df_mc["time_utc"] >= split_date
    
    times_train = times[train_mask]
    mags_train  = mags[train_mask]
    
    times_test  = times[test_mask]
    mags_test   = mags[test_mask]
    
    print(f"    Total M>=3 events: {len(df_mc):,}")
    print(f"    Training events  : {len(times_train):,} ({df_mc['time_utc'][train_mask].min().date()} to {df_mc['time_utc'][train_mask].max().date()})")
    print(f"    Testing events   : {len(times_test):,} ({df_mc['time_utc'][test_mask].min().date()} to {df_mc['time_utc'][test_mask].max().date()})")
    
    # ── Fit training model ────────────────────────────────────────
    print("\n[2] Fitting ETAS model on training period ...")
    model_train = ETASModel(times_train, mags_train, Mc=MC)
    model_train.fit(n_restarts=3, seed=42)
    tp = model_train.params_
    print(f"    Fitted params: mu={tp['mu']:.6f}, K={tp['K']:.5f}, alpha={tp['alpha']:.4f}, c={tp['c']:.6f}, p={tp['p']:.4f}")
    
    # ── Run forecast evaluations ─────────────────────────────────
    print("\n[3] Running rolling-origin retrospective forecasting ...")
    # We will step through the test period in 30-day increments
    t_start_test = float(times_train[-1])
    t_end_test   = float(times[-1])
    
    # Forecast horizons to evaluate
    horizons = [7, 14, 30]
    eval_origins = np.arange(t_start_test, t_end_test - max(horizons), 14.0)
    
    # Baseline Poisson rate from training
    train_duration = float(times_train[-1] - times_train[0])
    poisson_rate = len(times_train) / train_duration # events/day
    print(f"    Poisson baseline rate: {poisson_rate:.5f} events/day")
    
    # Accumulators for results
    fc_results = {h: [] for h in horizons}
    
    for t_orig in eval_origins:
        # Filter history up to t_orig
        hist_idx = times <= t_orig
        t_hist = times[hist_idx]
        m_hist = mags[hist_idx]
        
        # Create model representing the state at t_orig
        model_orig = ETASModel(t_hist, m_hist, Mc=MC)
        model_orig.params_ = tp.copy() # inject training parameters
        fc_orig = ETASForecast(model_orig)
        
        for h in horizons:
            t_end_h = t_orig + h
            # Count actual events in [t_orig, t_orig + h]
            actual_count = np.sum((times > t_orig) & (times <= t_end_h))
            actual_binary = 1 if actual_count > 0 else 0
            
            # Forecasts
            lam_etas = fc_orig.expected_count(t_orig, t_end_h)
            p_etas = 1.0 - np.exp(-lam_etas)
            
            lam_poisson = poisson_rate * h
            p_poisson = 1.0 - np.exp(-lam_poisson)
            
            fc_results[h].append({
                "origin": t_orig,
                "actual_count": actual_count,
                "actual_binary": actual_binary,
                "lam_etas": lam_etas,
                "p_etas": p_etas,
                "lam_poisson": lam_poisson,
                "p_poisson": p_poisson
            })
            
    # Convert list of dicts to DataFrames
    dfs = {h: pd.DataFrame(fc_results[h]) for h in horizons}
    
    # ── Calculate performance metrics ────────────────────────────
    print("\n[4] Computing forecast validation metrics ...")
    metrics_summary = {}
    
    for h in horizons:
        df_h = dfs[h]
        y_true_bin = df_h["actual_binary"].values
        y_true_cnt = df_h["actual_count"].values
        
        p_etas = df_h["p_etas"].values
        p_poisson = df_h["p_poisson"].values
        
        lam_etas = df_h["lam_etas"].values
        lam_poisson = df_h["lam_poisson"].values
        
        # 1. Brier Score
        bs_etas = np.mean((p_etas - y_true_bin) ** 2)
        bs_poisson = np.mean((p_poisson - y_true_bin) ** 2)
        bss = 1.0 - (bs_etas / bs_poisson) if bs_poisson > 0 else 0.0
        
        # 2. Log-likelihood Information Gain
        # ln L = k * ln(lam) - lam - ln(k!)
        # We sum over all windows.
        log_l_etas = np.sum(poisson.logpmf(y_true_cnt, lam_etas))
        log_l_poisson = np.sum(poisson.logpmf(y_true_cnt, lam_poisson))
        
        total_events_in_windows = np.sum(y_true_cnt)
        if total_events_in_windows > 0:
            # Information gain in bits per event
            inf_gain = (log_l_etas - log_l_poisson) / (np.log(2.0) * total_events_in_windows)
        else:
            inf_gain = 0.0
            
        # 3. AUC-ROC
        try:
            auc = compute_roc_auc(y_true_bin, p_etas)
        except Exception:
            auc = np.nan
            
        metrics_summary[h] = {
            "Brier_ETAS": float(bs_etas),
            "Brier_Poisson": float(bs_poisson),
            "Brier_Skill_Score": float(bss),
            "LogL_ETAS": float(log_l_etas),
            "LogL_Poisson": float(log_l_poisson),
            "Information_Gain_Bits_Per_Event": float(inf_gain),
            "AUC_ROC": float(auc)
        }
        
        print(f"  Horizon: {h} days")
        print(f"    Brier Score ETAS   : {bs_etas:.4f}")
        print(f"    Brier Score Poisson: {bs_poisson:.4f}")
        print(f"    Brier Skill Score  : {bss:.2%}")
        print(f"    Info Gain/Event    : {inf_gain:.4f} bits/event")
        print(f"    AUC-ROC            : {auc:.4f}")
        print()
        
    # Save metrics to JSON
    with open(OUT_DIR / "etas_validation_metrics.json", "w") as f:
        json.dump(metrics_summary, f, indent=2)
        
    # ── Generate Plots ───────────────────────────────────────────
    print("[5] Generating validation plots ...")
    
    # 1. ROC Curves (14-day horizon as representative)
    h_rep = 14
    df_rep = dfs[h_rep]
    y_true_rep = df_rep["actual_binary"].values
    p_etas_rep = df_rep["p_etas"].values
    
    fpr, tpr = compute_roc_curve(y_true_rep, p_etas_rep)
    auc_val = metrics_summary[h_rep]["AUC_ROC"]
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Left Panel: ROC Curve
    ax = axes[0]
    ax.plot(fpr, tpr, "-", color="#2563EB", linewidth=2.5, label=f"ETAS (AUC = {auc_val:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="#6B7280", label="Random Guess (AUC = 0.50)")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve: {h_rep}-Day Event Probability Forecast")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    
    # Right Panel: Reliability Diagram (Calibration Curve)
    ax = axes[1]
    # Bin forecasted probabilities
    bins = np.linspace(0.0, 1.0, 6)
    bin_centers = 0.5 * (bins[:-1] + bins[1:])
    emp_freqs = []
    mean_forecasts = []
    
    for i in range(len(bins)-1):
        mask = (p_etas_rep >= bins[i]) & (p_etas_rep < bins[i+1])
        if np.any(mask):
            emp_freqs.append(np.mean(y_true_rep[mask]))
            mean_forecasts.append(np.mean(p_etas_rep[mask]))
        else:
            emp_freqs.append(np.nan)
            mean_forecasts.append(bin_centers[i])
            
    ax.plot([0, 1], [0, 1], "--", color="#6B7280", label="Perfect Calibration")
    ax.plot(mean_forecasts, emp_freqs, "o-", color="#EA580C", linewidth=2, markersize=8, label="ETAS Forecast")
    ax.set_xlabel("Mean Forecasted Probability")
    ax.set_ylabel("Empirical Frequency")
    ax.set_title(f"Reliability Diagram: {h_rep}-Day Event Forecast")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    
    plt.suptitle("ETAS Forecast Retrospective Validation (Test Period: 2018–2025)", fontsize=14, fontweight="bold", y=0.98)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "etas_validation_plots.png", dpi=150)
    plt.close(fig)
    print("    Saved validation plots --> outputs/etas_validation_plots.png")
    
    print("\n[SUCCESS] Validation complete.")

if __name__ == "__main__":
    main()
