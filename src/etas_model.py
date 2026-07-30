"""
etas_model.py
-------------
Trikaal — Vectorized ETAS (Epidemic Type Aftershock Sequence) Model
Ogata (1988) formulation with fully vectorized log-likelihood.

Conditional intensity:
  λ(t) = μ + Σ_{t_i < t} K·exp(α(m_i − Mc)) · (t − t_i + c)^{−p}

Parameters: μ, K, α, c, p
"""

from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from scipy.optimize import minimize
from scipy.stats import kstest


class ETASModel:
    """Vectorized ETAS model.  O(N²) memory, O(N²) per likelihood eval."""

    # Threshold for precomputing the full (N×N) matrix.
    # Above this, _neg_loglik uses a row-by-row chunked loop (slower but memory-safe).
    _PRECOMPUTE_LIMIT = 4_000

    def __init__(self, times: np.ndarray, mags: np.ndarray, Mc: float = 3.0):
        """
        Parameters
        ----------
        times : array of event times in *days*, sorted ascending, starting at 0
        mags  : array of magnitudes (same length)
        Mc    : completeness magnitude
        """
        self.t   = np.asarray(times, dtype=np.float64)
        self.m   = np.asarray(mags,  dtype=np.float64)
        self.Mc  = float(Mc)
        self.N   = len(self.t)
        self.T   = float(self.t[-1] - self.t[0])

        self.dm = self.m - self.Mc

        if self.N <= self._PRECOMPUTE_LIMIT:
            # Precompute full (N×N) time-difference matrix once
            self.dt_mat  = self.t[None, :] - self.t[:, None]   # (N, N)
            self.causal  = self.dt_mat > 0
            self._large  = False
        else:
            self.dt_mat  = None
            self.causal  = None
            self._large  = True

        self.params_  = None
        self.result_  = None

    # ------------------------------------------------------------------
    # Log-likelihood
    # ------------------------------------------------------------------
    def _neg_loglik(self, theta: np.ndarray) -> float:
        mu, K, alpha, c, p = theta
        if mu <= 0 or K <= 0 or alpha <= 0 or c <= 0 or p <= 0.5:
            return 1e12

        exp_dm = K * np.exp(alpha * self.dm)   # (N,)
        T      = self.T
        ti     = self.t

        if not self._large:
            # ── Fast path: precomputed (N×N) matrix ──────────────────────
            dt = self.dt_mat
            with np.errstate(divide="ignore", invalid="ignore"):
                kernel = np.where(self.causal, (dt + c) ** (-p), 0.0)   # (N, N)
            triggered  = exp_dm @ kernel        # (N,)
        else:
            # ── Memory-safe path: process in row chunks ───────────────────
            CHUNK = 512
            triggered = np.zeros(self.N, dtype=np.float64)
            for j0 in range(0, self.N, CHUNK):
                j1    = min(j0 + CHUNK, self.N)
                dt_ch = ti[j0:j1][None, :] - ti[:, None]   # (N, j1-j0)
                mask  = dt_ch > 0
                with np.errstate(divide="ignore", invalid="ignore"):
                    k_ch = np.where(mask, (dt_ch + c) ** (-p), 0.0)
                triggered[j0:j1] = exp_dm @ k_ch

        intensity = mu + triggered
        if np.any(intensity <= 0):
            return 1e12

        log_lik = np.sum(np.log(intensity))

        # Integral ∫₀ᵀ λ(t) dt
        if abs(p - 1.0) < 1e-8:
            integ = np.log((T - ti + c) / c)
        else:
            integ = ((T - ti + c) ** (1.0 - p) - c ** (1.0 - p)) / (1.0 - p)

        total_integral = mu * T + np.dot(exp_dm, integ)
        return -(log_lik - total_integral)

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------
    def fit(self, n_restarts: int = 5, seed: int = 42) -> "ETASModel":
        rng    = np.random.default_rng(seed)
        rate0  = self.N / max(self.T, 1.0)
        bounds = [(1e-7, None), (1e-6, None), (1e-6, 5.0), (1e-6, 10.0), (0.51, 3.0)]

        # First guess: physically motivated
        x0_base = [rate0 * 0.1, 0.1, 1.0, 0.1, 1.0]
        starts  = [x0_base]
        for _ in range(n_restarts - 1):
            starts.append([
                rate0 * rng.uniform(0.05, 0.5),
                rng.uniform(0.01, 0.5),
                rng.uniform(0.5, 2.5),
                rng.uniform(0.01, 1.0),
                rng.uniform(0.7, 1.5),
            ])

        best_val, best_res = np.inf, None
        for x0 in starts:
            try:
                res = minimize(
                    self._neg_loglik, x0, method="L-BFGS-B", bounds=bounds,
                    options={"maxiter": 3000, "ftol": 1e-14, "gtol": 1e-9},
                )
                if res.fun < best_val:
                    best_val, best_res = res.fun, res
            except Exception:
                continue

        if best_res is None:
            raise RuntimeError("ETAS optimization failed across all restarts.")

        self.result_ = best_res
        mu, K, alpha, c, p = best_res.x
        self.params_ = {
            "mu": mu, "K": K, "alpha": alpha, "c": c, "p": p,
            "Mc": self.Mc, "N": self.N, "T": self.T,
            "neg_loglik": float(best_val),
        }
        return self

    # ------------------------------------------------------------------
    # Intensity evaluation (vectorized over query times)
    # ------------------------------------------------------------------
    def intensity(self, t_query: np.ndarray) -> np.ndarray:
        """λ(t) at arbitrary query times using fitted parameters."""
        if self.params_ is None:
            raise RuntimeError("Call .fit() first.")
        mu, K, alpha, c, p = [self.params_[k] for k in ("mu","K","alpha","c","p")]
        t_query = np.atleast_1d(np.asarray(t_query, dtype=np.float64))
        # dt[i, q] = t_query[q] − t[i]
        dt     = t_query[None, :] - self.t[:, None]          # (N, Q)
        causal = dt > 0
        exp_dm = K * np.exp(alpha * self.dm)                  # (N,)
        kernel = np.where(causal, (dt + c) ** (-p), 0.0)      # (N, Q)
        return mu + (exp_dm[:, None] * kernel).sum(axis=0)    # (Q,)

    # ------------------------------------------------------------------
    # Goodness-of-fit: time-rescaling KS test (vectorized)
    # ------------------------------------------------------------------
    def time_rescaling_test(self):
        """
        Ogata (1988) time-rescaling test.
        Vectorized cumulative Λ(t_j) = μ·t_j + Σ_{i<j} exp_dm_i · g(t_j − t_i)
        where g(Δ) = ((Δ+c)^{1-p} − c^{1-p}) / (1−p)

        Returns (ks_statistic, p_value).
        """
        if self.params_ is None:
            raise RuntimeError("Call .fit() first.")
        mu, K, alpha, c, p = [self.params_[k] for k in ("mu","K","alpha","c","p")]
        exp_dm = K * np.exp(alpha * self.dm)   # (N,)

        if not self._large:
            dt = self.dt_mat
            if abs(p - 1.0) < 1e-8:
                g_mat = np.where(self.causal, np.log((dt + c) / c), 0.0)
            else:
                g_mat = np.where(
                    self.causal,
                    ((dt + c) ** (1.0 - p) - c ** (1.0 - p)) / (1.0 - p),
                    0.0,
                )
            cum_lambda = mu * self.t + exp_dm @ g_mat
        else:
            # Chunked fallback
            CHUNK = 512
            cum_lambda = mu * self.t.copy()
            for j0 in range(0, self.N, CHUNK):
                j1    = min(j0 + CHUNK, self.N)
                dt_ch = self.t[j0:j1][None, :] - self.t[:, None]   # (N, j1-j0)
                mask  = dt_ch > 0
                if abs(p - 1.0) < 1e-8:
                    g_ch = np.where(mask, np.log((dt_ch + c) / c), 0.0)
                else:
                    g_ch = np.where(
                        mask,
                        ((dt_ch + c) ** (1.0 - p) - c ** (1.0 - p)) / (1.0 - p),
                        0.0,
                    )
                cum_lambda[j0:j1] += exp_dm @ g_ch

        inter = np.diff(cum_lambda, prepend=0.0)
        inter = inter[inter > 0]
        u     = 1.0 - np.exp(-inter)
        stat, pval = kstest(u, "uniform")
        return float(stat), float(pval)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------
    def save_params(self, path: str | Path):
        with open(path, "w") as f:
            json.dump(self.params_, f, indent=2)
        print(f"  Saved ETAS params --> {path}")

    @classmethod
    def load_params(cls, path: str | Path) -> dict:
        with open(path) as f:
            return json.load(f)

    def summary(self):
        if self.params_ is None:
            print("Model not fitted.")
            return
        p = self.params_
        print(f"  mu={p['mu']:.5f}  K={p['K']:.5f}  alpha={p['alpha']:.4f}"
              f"  c={p['c']:.5f}  p={p['p']:.4f}")
        print(f"  -logL = {p['neg_loglik']:.4f}   N={p['N']}   T={p['T']:.1f} days")


def intensity_at_events(times: np.ndarray, mags: np.ndarray, Mc: float, params: list) -> np.ndarray:
    """Computes the ETAS conditional intensity lambda(t_i) at each event time."""
    mu, K, alpha, c, p = params
    t = np.asarray(times, dtype=np.float64)
    m = np.asarray(mags, dtype=np.float64)
    dm = m - Mc
    
    # Precompute time difference matrix
    dt_mat = t[None, :] - t[:, None]
    causal = dt_mat > 0
    exp_dm = K * np.exp(alpha * dm)
    
    with np.errstate(divide="ignore", invalid="ignore"):
        kernel = np.where(causal, (dt_mat + c) ** (-p), 0.0)
    triggered = exp_dm @ kernel
    return mu + triggered


def integral_lambda(history_times: np.ndarray, history_mags: np.ndarray, Mc: float, params: list, t_end: float) -> float:
    """
    Computes cumulative integrated intensity Λ(0, t_end) given history of events before t_end.
    Λ(0, t_end) = μ·t_end + Σ_{t_j < t_end} K·exp(α(M_j − Mc)) · ∫_{t_j}^{t_end} (t − t_j + c)^{−p} dt
    """
    mu, K, alpha, c, p = params
    t_hist = np.asarray(history_times, dtype=np.float64)
    m_hist = np.asarray(history_mags, dtype=np.float64)
    dm = m_hist - Mc
    
    # We only integrate events that occurred before t_end
    active = t_hist < t_end
    if not np.any(active):
        return mu * t_end
        
    t_active = t_hist[active]
    dm_active = dm[active]
    exp_dm = K * np.exp(alpha * dm_active)
    
    # The duration each event has been decaying is t_end - t_j
    b = t_end - t_active
    
    if abs(p - 1.0) < 1e-8:
        integ = np.log((b + c) / c)
    else:
        integ = ((b + c) ** (1.0 - p) - c ** (1.0 - p)) / (1.0 - p)
        
    return mu * t_end + float(np.dot(exp_dm, integ))


