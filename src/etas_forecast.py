"""
etas_forecast.py
----------------
Trikaal — ETAS Forecast Engine

Given a fitted ETASModel, computes expected event counts and exceedance
probabilities over arbitrary future horizons.
Assumes Poisson (inhomogeneous) counting: P(N≥1) = 1 − exp(−Λ).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from etas_model import ETASModel


class ETASForecast:
    """Forecast wrapper around a fitted ETASModel."""

    def __init__(self, model: ETASModel):
        if model.params_ is None:
            raise ValueError("ETASModel must be fitted before forecasting.")
        self.model  = model
        self.params = model.params_

    # ------------------------------------------------------------------
    # Core: vectorized integrated intensity over [t_start, t_end]
    # ------------------------------------------------------------------
    def _integrated_intensity(self, t_start: float, t_end: float) -> float:
        """
        Λ(t_start, t_end) = ∫_{t_start}^{t_end} λ(t) dt
        Accounts for all events already in the catalog (t_i ≤ T_catalog).
        """
        mu    = self.params["mu"]
        K     = self.params["K"]
        alpha = self.params["alpha"]
        c     = self.params["c"]
        p     = self.params["p"]

        t_hist = self.model.t
        exp_dm = K * np.exp(alpha * self.model.dm)  # (N,)

        # For each historical event i, integrate (t − t_i + c)^{-p}
        # over [max(t_start, t_i), t_end].  Events after t_end contribute 0.
        a = np.maximum(t_start - t_hist, 0.0)
        b = t_end   - t_hist
        active = b > 0   # only events before t_end matter

        if abs(p - 1.0) < 1e-8:
            integ = np.where(active, np.log((b + c) / (a + c)), 0.0)
        else:
            integ = np.where(
                active,
                ((a + c) ** (1.0 - p) - (b + c) ** (1.0 - p)) / (p - 1.0),
                0.0,
            )

        return mu * (t_end - t_start) + float(np.dot(exp_dm, integ))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def expected_count(self, t_start: float, t_end: float) -> float:
        """Expected M≥Mc event count in [t_start, t_end] (days from catalog t0)."""
        return self._integrated_intensity(t_start, t_end)

    def prob_at_least_one(self, t_start: float, t_end: float) -> float:
        """P(N ≥ 1 | M ≥ Mc) in [t_start, t_end] under Poisson assumption."""
        return 1.0 - np.exp(-self.expected_count(t_start, t_end))

    def forecast_table(
        self,
        horizons_days: list[int] | None = None,
        ref_time: float | None = None,
    ) -> pd.DataFrame:
        """
        Return a DataFrame with expected counts & exceedance probs for
        each horizon, starting from `ref_time` (days from catalog t0).
        Default ref_time = end of catalog.
        """
        if horizons_days is None:
            horizons_days = [1, 7, 14, 30, 90, 180, 365]

        t_ref = float(self.model.t[-1]) if ref_time is None else float(ref_time)
        Mc    = self.params["Mc"]

        rows = []
        for h in horizons_days:
            t0 = t_ref
            t1 = t_ref + h
            lam = self.expected_count(t0, t1)
            rows.append(
                {
                    "horizon_days"   : h,
                    f"E[N|M>={Mc}]"  : round(lam, 4),
                    "P(N>=1)"        : round(1.0 - np.exp(-lam), 4),
                    "P(N>=5)"        : round(1.0 - sum(
                        np.exp(-lam) * lam**k / __import__("math").factorial(k)
                        for k in range(5)
                    ), 4),
                }
            )
        return pd.DataFrame(rows)

    def rolling_forecast(
        self,
        window_days: int = 14,
        step_days: int = 14,
    ) -> pd.DataFrame:
        """
        Slide a forecast window over the entire catalog span and return
        the expected count per window — mirrors the risk_score.py binning.
        """
        t_start = float(self.model.t[0])
        t_end   = float(self.model.t[-1])
        bins    = np.arange(t_start, t_end, step_days)
        rows    = []
        for b in bins:
            lam = self.expected_count(b, b + window_days)
            rows.append({
                "bin_start_day"  : round(b, 1),
                "bin_end_day"    : round(b + window_days, 1),
                f"E[N|M>={self.params['Mc']}]": round(lam, 4),
                "P(N>=1)"        : round(1.0 - np.exp(-lam), 4),
            })
        return pd.DataFrame(rows)
