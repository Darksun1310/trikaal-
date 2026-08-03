"""
benchmark_etas.py
-----------------
Benchmark script to compare the performance of vectorized vs. loop-based
ETAS log-likelihood evaluations. Generates a comparison plot.
"""

import sys
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
from etas_model import ETASModel

# Paths
OUT_DIR = Path(__file__).parent.parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

def loop_neg_loglik(times, mags, Mc, theta):
    """Traditional loop-based ETAS log-likelihood (scalar operations)."""
    mu, K, alpha, c, p = theta
    if mu <= 0 or K <= 0 or alpha <= 0 or c <= 0 or p <= 0.5:
        return 1e12
    
    n = len(times)
    log_lik = 0.0
    T = float(times[-1] - times[0])
    
    # Calculate triggered intensity at each event time
    for j in range(n):
        t_j = times[j]
        triggered = 0.0
        for i in range(j):
            t_i = times[i]
            m_i = mags[i]
            triggered += K * np.exp(alpha * (m_i - Mc)) * ((t_j - t_i + c) ** (-p))
        intensity = mu + triggered
        log_lik += np.log(intensity)
        
    # Integral
    total_integral = mu * T
    for i in range(n):
        t_i = times[i]
        m_i = mags[i]
        exp_dm = K * np.exp(alpha * (m_i - Mc))
        if abs(p - 1.0) < 1e-8:
            integ = np.log((T - t_i + c) / c)
        else:
            integ = ((T - t_i + c) ** (1.0 - p) - c ** (1.0 - p)) / (1.0 - p)
        total_integral += exp_dm * integ
        
    return -(log_lik - total_integral)

def main():
    print("=" * 60)
    print("  TRIKAAL -- ETAS Vectorization Benchmark")
    print("=" * 60)
    
    # Generate synthetic catalog data
    np.random.seed(42)
    max_N = 2000
    times_all = np.sort(np.random.uniform(0, 1000, max_N))
    mags_all = np.random.exponential(1.0, max_N) + 3.0
    
    theta = np.array([0.01, 0.05, 1.2, 0.05, 1.1])
    Mc = 3.0
    
    sizes = [100, 200, 500, 1000, 1500, 2000]
    results = []
    
    for N in sizes:
        print(f"\nBenchmarking N = {N} ...")
        t_sub = times_all[:N]
        m_sub = mags_all[:N]
        
        # 1. Loop-based (pure Python loops)
        # Skip loop-based for very large N to avoid excessive waiting
        if N <= 1500:
            t0 = time.perf_counter()
            val_loop = loop_neg_loglik(t_sub, m_sub, Mc, theta)
            t_loop = time.perf_counter() - t0
            print(f"  Loop-based:         {t_loop:.5f} s  (val={val_loop:.2f})")
        else:
            t_loop = np.nan
            print("  Loop-based:         SKIPPED (too slow)")
            
        # 2. Vectorized Full Matrix
        model_vec = ETASModel(t_sub, m_sub, Mc=Mc)
        model_vec._large = False  # force full matrix path
        t0 = time.perf_counter()
        val_vec = model_vec._neg_loglik(theta)
        t_vec = time.perf_counter() - t0
        print(f"  Vectorized (Full):  {t_vec:.5f} s  (val={val_vec:.2f})")
        
        # 3. Vectorized Chunked Matrix (CHUNK=512)
        model_chunk = ETASModel(t_sub, m_sub, Mc=Mc)
        model_chunk._large = True  # force chunked path
        t0 = time.perf_counter()
        val_chunk = model_chunk._neg_loglik(theta)
        t_chunk = time.perf_counter() - t0
        print(f"  Vectorized (Chunk): {t_chunk:.5f} s  (val={val_chunk:.2f})")
        
        results.append({
            "N": N,
            "t_loop": t_loop,
            "t_vec": t_vec,
            "t_chunk": t_chunk,
            "speedup": t_loop / t_vec if not np.isnan(t_loop) else np.nan
        })
        
    df_res = pd.DataFrame(results)
    print("\nBenchmark Results Summary Table:")
    print(df_res.to_string(index=False))
    
    # Save results to CSV
    df_res.to_csv(OUT_DIR / "etas_benchmark_results.csv", index=False)
    
    # Plotting
    plt.figure(figsize=(10, 6))
    
    # Plot execution times (Log scale)
    valid_loop = df_res.dropna(subset=["t_loop"])
    plt.plot(valid_loop["N"], valid_loop["t_loop"], "o-", color="#DC2626", linewidth=2, label="Loop-based (Pure Python)")
    plt.plot(df_res["N"], df_res["t_vec"], "s-", color="#2563EB", linewidth=2, label="Vectorized (Full Matrix)")
    plt.plot(df_res["N"], df_res["t_chunk"], "^--", color="#16A34A", linewidth=2, label="Vectorized (Chunked, size=512)")
    
    plt.yscale("log")
    plt.xlabel("Catalog Size (Number of Events, N)")
    plt.ylabel("Execution Time (seconds) - Log Scale")
    plt.title("ETAS Log-Likelihood Evaluation Performance Benchmark")
    plt.grid(True, which="both", alpha=0.3)
    plt.legend()
    
    # Add speedup labels on top of the bars/points if available
    for idx, row in df_res.iterrows():
        if not np.isnan(row["speedup"]):
            plt.annotate(f"{row['speedup']:.1f}x", 
                         (row["N"], row["t_vec"]),
                         textcoords="offset points", 
                         xytext=(0,10), 
                         ha="center", 
                         fontsize=9, 
                         fontweight="bold", 
                         color="#1E40AF")
            
    plt.tight_layout()
    plt.savefig(OUT_DIR / "etas_benchmark.png", dpi=150)
    plt.close()
    print(f"\nSaved benchmark plot to outputs/etas_benchmark.png")

if __name__ == "__main__":
    main()
