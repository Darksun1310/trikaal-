"""
risk_score.py
-------------
Trikaal — Seismic Risk Score Engine

Composite risk index Risk(t) ∈ [0,1] over 14-day bins via three signals:

  S_b(t)       : stress proxy — (b_ref − b_t) / (b_ref − b_min), clipped [0,1]
  S_rate(t)    : activity proxy — sigmoid of event-rate z-score
  S_cluster(t) : instability proxy — 1 − normalize(mean NND km)

  Risk = 0.40·S_b + 0.35·S_rate + 0.25·S_cluster

Classification: quantile-based (Q33 / Q66) — adapts to the catalog.

Outputs
-------
  outputs/risk_score.csv     — per-bin risk table
  outputs/risk_timeline.png  — static matplotlib figure (paper-ready)
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_PATH = Path(__file__).parent.parent / "data" / "processed" / "kutch_clean.csv"
OUT_DIR   = Path(__file__).parent.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

# ── Parameters ─────────────────────────────────────────────────────────────
MC           = 3.0    # operational completeness magnitude
BIN_DAYS     = 14     # time-bin width (days)
B_REF        = 1.0    # healthy tectonic b-value reference
B_MIN        = 0.5    # catalog-floor b-value (from data)
B_WINDOW_D   = 90     # ±45-day centered window for b estimation
B_MIN_N      = 15     # min events in b-window for valid estimate
CLUSTER_MIN  = 3      # min events per bin for NND
WEIGHTS      = (0.40, 0.35, 0.25)   # w_b, w_rate, w_cluster
BHUJ_DATE    = pd.Timestamp("2001-01-26", tz="UTC")

EARTH_R = 6371.0

sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 150})


# ── Helpers ────────────────────────────────────────────────────────────────
def haversine_matrix(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Fully vectorized pairwise haversine distance matrix (km)."""
    lr  = np.radians(lats)
    lor = np.radians(lons)
    dlat = lr[:, None] - lr[None, :]
    dlon = lor[:, None] - lor[None, :]
    a = (np.sin(dlat / 2) ** 2
         + np.cos(lr[:, None]) * np.cos(lr[None, :]) * np.sin(dlon / 2) ** 2)
    return EARTH_R * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bvalue_mle_aki(mags: np.ndarray, mc: float, dM: float = 0.1):
    """Aki 1965 MLE + Shi & Bolt 1982 sigma. Returns (b, sigma_b)."""
    above = mags[mags >= mc]
    n = len(above)
    if n < 2:
        return np.nan, np.nan
    b = np.log10(np.e) / (above.mean() - (mc - dM / 2))
    s = 2.30 * b ** 2 * np.std(above, ddof=1) / np.sqrt(n)
    return b, s


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


# ── Signal 1 — b-value stress ──────────────────────────────────────────────
def compute_b_signal(df: pd.DataFrame, bin_edges: pd.DatetimeIndex) -> np.ndarray:
    """
    Centered 90-day window b-value per bin.
    S_b = clip( (b_ref − b_t) / (b_ref − b_min), 0, 1 )
    Low b → high stress → high S_b.
    """
    df_mc  = df[df["magnitude"] >= MC]
    mags   = df_mc["magnitude"].values
    times  = df_mc["time_utc"].values.astype("datetime64[ns]")
    half_w = pd.Timedelta(days=B_WINDOW_D // 2)

    n_bins = len(bin_edges) - 1
    s_b = np.full(n_bins, np.nan)

    for i in range(n_bins):
        t_ctr = bin_edges[i] + (bin_edges[i + 1] - bin_edges[i]) / 2
        lo    = (t_ctr - half_w).to_datetime64()
        hi    = (t_ctr + half_w).to_datetime64()
        win   = mags[(times >= lo) & (times < hi)]
        if len(win) < B_MIN_N:
            continue
        b_t, _ = bvalue_mle_aki(win, MC)
        if np.isnan(b_t):
            continue
        s_b[i] = np.clip((B_REF - b_t) / (B_REF - B_MIN), 0.0, 1.0)

    return s_b


# ── Signal 2 — event-rate activity ────────────────────────────────────────
def compute_rate_signal(df: pd.DataFrame, bin_edges: pd.DatetimeIndex) -> np.ndarray:
    """
    Count M≥Mc events per bin → robust z-score (median/IQR) → sigmoid.
    Uses median + IQR instead of mean/std so the extreme Bhuj aftershock
    period does not collapse the quantile boundaries for the rest of the catalog.
    """
    df_mc  = df[df["magnitude"] >= MC]
    times  = df_mc["time_utc"].values.astype("datetime64[ns]")
    n_bins = len(bin_edges) - 1

    counts = np.array([
        ((times >= bin_edges[i].to_datetime64()) &
         (times <  bin_edges[i + 1].to_datetime64())).sum()
        for i in range(n_bins)
    ], dtype=float)

    med  = np.median(counts)
    iqr  = np.percentile(counts, 75) - np.percentile(counts, 25)
    if iqr == 0:
        iqr = counts.std(ddof=1) or 1.0
    return sigmoid((counts - med) / iqr)


# ── Signal 3 — spatial clustering (NND) ───────────────────────────────────
def compute_cluster_signal(df: pd.DataFrame, bin_edges: pd.DatetimeIndex) -> np.ndarray:
    """
    Mean Nearest-Neighbor Distance per bin. Small NND → tight cluster → high risk.
    S_cluster = 1 − normalize(mean_NND)   [global min-max over valid bins]
    """
    df_mc  = df[df["magnitude"] >= MC]
    times  = df_mc["time_utc"].values.astype("datetime64[ns]")
    lats   = df_mc["latitude"].values
    lons   = df_mc["longitude"].values
    n_bins = len(bin_edges) - 1

    mean_nnds = np.full(n_bins, np.nan)

    for i in range(n_bins):
        mask = ((times >= bin_edges[i].to_datetime64()) &
                (times <  bin_edges[i + 1].to_datetime64()))
        if mask.sum() < CLUSTER_MIN:
            continue
        D = haversine_matrix(lats[mask], lons[mask])
        np.fill_diagonal(D, np.inf)
        mean_nnds[i] = D.min(axis=1).mean()

    valid = ~np.isnan(mean_nnds)
    if valid.sum() < 2:
        return np.full(n_bins, np.nan)

    lo, hi = mean_nnds[valid].min(), mean_nnds[valid].max()
    rng    = hi - lo if hi > lo else 1.0
    return np.where(valid, 1.0 - (mean_nnds - lo) / rng, np.nan)


# ── Composite score ────────────────────────────────────────────────────────
def compute_risk_score(df: pd.DataFrame) -> pd.DataFrame:
    """Assemble all three signals into a composite risk DataFrame."""
    t_min    = df["time_utc"].min().floor("D")
    t_max    = df["time_utc"].max().ceil("D")
    bin_edges = pd.date_range(t_min, t_max, freq=f"{BIN_DAYS}D", tz="UTC")
    n_bins   = len(bin_edges) - 1

    print(f"  Bins: {n_bins} × {BIN_DAYS}-day  |  Mc={MC}")

    s_b       = compute_b_signal(df, bin_edges)
    s_rate    = compute_rate_signal(df, bin_edges)
    s_cluster = compute_cluster_signal(df, bin_edges)

    w_b, w_r, w_c = WEIGHTS
    risk = np.full(n_bins, np.nan)

    for i in range(n_bins):
        sigs, wts = [], []
        if not np.isnan(s_b[i]):       sigs.append(s_b[i]);       wts.append(w_b)
        if not np.isnan(s_rate[i]):    sigs.append(s_rate[i]);    wts.append(w_r)
        if not np.isnan(s_cluster[i]): sigs.append(s_cluster[i]); wts.append(w_c)
        if sigs:
            tw = sum(wts)
            risk[i] = sum(s * w / tw for s, w in zip(sigs, wts))

    result = pd.DataFrame({
        "period_start"   : bin_edges[:-1],
        "period_end"     : bin_edges[1:],
        "b_signal"       : s_b,
        "rate_signal"    : s_rate,
        "cluster_signal" : s_cluster,
        "risk_score"     : risk,
    })

    # Quantile-based classification
    valid = result["risk_score"].dropna()
    q33, q66 = valid.quantile(0.33), valid.quantile(0.66)

    def _label(v):
        if pd.isna(v): return "UNKNOWN"
        return "HIGH" if v >= q66 else ("MEDIUM" if v >= q33 else "LOW")

    result["risk_label"] = result["risk_score"].map(_label)
    result["q33"] = q33
    result["q66"] = q66

    return result


# ── Static matplotlib figure (paper-ready) ────────────────────────────────
def plot_risk_timeline(risk_df: pd.DataFrame, df_raw: pd.DataFrame):
    q33   = risk_df["q33"].iloc[0]
    q66   = risk_df["q66"].iloc[0]
    t_mid = (risk_df["period_start"]
             + (risk_df["period_end"] - risk_df["period_start"]) / 2).values
    scores = risk_df["risk_score"].values
    large  = df_raw[df_raw["magnitude"] >= 4.0].dropna(subset=["time_utc", "magnitude"])

    fig, axes = plt.subplots(4, 1, figsize=(15, 14), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1, 1, 1]})
    ax = axes[0]

    # Risk filled areas — use masked arrays so NaN bins don't interpolate
    s = np.ma.masked_invalid(scores)
    ax.fill_between(t_mid, 0, np.where(s < q33,              s, q33),
                    color="#2ecc71", alpha=0.55, label="LOW",    step="mid")
    ax.fill_between(t_mid, 0, np.where((s >= q33) & (s < q66), s, 0),
                    color="#f39c12", alpha=0.60, label="MEDIUM", step="mid")
    ax.fill_between(t_mid, 0, np.where(s >= q66,              s, 0),
                    color="#e74c3c", alpha=0.70, label="HIGH",   step="mid")

    ax.axhline(q33, color="#27ae60", ls="--", lw=1.0, alpha=0.7)
    ax.axhline(q66, color="#c0392b", ls="--", lw=1.0, alpha=0.7)
    ax.axvline(BHUJ_DATE, color="#e74c3c", lw=1.8, ls="-", alpha=0.9)
    ax.text(BHUJ_DATE, 0.98, "  Bhuj Mw7.7",
            color="#e74c3c", fontsize=9, fontweight="bold",
            transform=ax.get_xaxis_transform(), va="top")

    ax2 = ax.twinx()
    ax2.scatter(large["time_utc"].values, large["magnitude"].values,
                s=large["magnitude"] ** 2 * 3,
                color="white", edgecolor="black", alpha=0.8, zorder=5, label="M≥4 events")
    ax2.set_ylabel("Magnitude", fontsize=9)
    ax2.set_ylim(3.5, 9)

    lines1, l1 = ax.get_legend_handles_labels()
    lines2, l2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, l1 + l2, loc="upper right", fontsize=8)
    ax.set_ylabel("Risk Score [0–1]", fontsize=10)
    ax.set_ylim(0, 1.1)
    ax.set_title(
        f"Kutch Seismic Risk Score — Trikaal Intelligence Engine\n"
        f"Risk = 0.40·S_b + 0.35·S_rate + 0.25·S_cluster  |  {BIN_DAYS}-day bins  |  Mc={MC}",
        fontsize=11, fontweight="bold")

    COMP = [
        ("b_signal",       "#8e44ad", "S_b  (Stress)"),
        ("rate_signal",    "#2980b9", "S_rate  (Activity)"),
        ("cluster_signal", "#16a085", "S_cluster  (Clustering)"),
    ]
    for ax_c, (col, clr, lbl) in zip(axes[1:], COMP):
        vals = risk_df[col].values
        ax_c.fill_between(t_mid, 0, vals, color=clr, alpha=0.40, step="mid")
        ax_c.plot(t_mid, vals, color=clr, lw=1.2)
        ax_c.axvline(BHUJ_DATE, color="#e74c3c", lw=1.5, alpha=0.75)
        ax_c.set_ylabel(lbl, fontsize=8)
        ax_c.set_ylim(-0.05, 1.15)
        ax_c.grid(alpha=0.3)

    axes[-1].set_xlabel("Date", fontsize=10)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[-1].xaxis.set_major_locator(mdates.YearLocator(2))
    fig.autofmt_xdate()
    for a in axes:
        a.grid(alpha=0.25)
    fig.tight_layout()
    out = OUT_DIR / "risk_timeline.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → risk_timeline.png")


# ── Main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  TRIKAAL — Seismic Risk Score Engine")
    print("=" * 60)

    df = pd.read_csv(DATA_PATH)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc", "magnitude", "latitude", "longitude"])
    print(f"Loaded {len(df):,} events  |  M {df.magnitude.min():.1f}–{df.magnitude.max():.1f}")

    risk_df = compute_risk_score(df)

    csv_out = OUT_DIR / "risk_score.csv"
    risk_df.to_csv(csv_out, index=False)
    print(f"  Saved → risk_score.csv  ({len(risk_df)} bins)")

    valid = risk_df.dropna(subset=["risk_score"])
    q33   = valid["q33"].iloc[0]
    q66   = valid["q66"].iloc[0]
    print(f"\nRisk summary ({len(valid)} valid bins):")
    print(f"  min / mean / max : "
          f"{valid['risk_score'].min():.3f} / "
          f"{valid['risk_score'].mean():.3f} / "
          f"{valid['risk_score'].max():.3f}")
    print(f"  Q33 / Q66        : {q33:.3f} / {q66:.3f}")
    print("\nLabel distribution:")
    print(risk_df["risk_label"].value_counts().to_string())

    top5 = risk_df.nlargest(5, "risk_score")[
        ["period_start", "risk_score", "risk_label",
         "b_signal", "rate_signal", "cluster_signal"]]
    print("\nTop 5 highest-risk periods:")
    print(top5.to_string(index=False))

    plot_risk_timeline(risk_df, df)
    print("\n✓ Done. Run risk_dashboard.py for the interactive HTML.")
