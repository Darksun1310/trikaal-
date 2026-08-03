# Trikaal Operational Seismic Bulletin
**Issued at (UTC):** 2026-08-03 21:06:36  
**Region:** Kutch Intraplate Zone (22.0–24.5°N, 68.0–71.5°E)  
**Authority:** Trikaal Real-Time Operational Pipeline  

---

> [!NOTE]
> No new M>=2.0 events since last update. Forecast unchanged.

## 1. Executive Summary
* **Current Operational Alert Level:** **LOW (Last known state: LOW (2025-12-21))**
* **Short-Term Forecast (Next 7 Days):** **9.2%** probability of at least one $M \ge 3.0$ event.
* **Hazard Amplification Factor:** **0.17x** elevation over long-term PSHA baseline rate.
* **Stress Recovery Index (SRI):** **3.61%** (The ratio of pure tectonic background loading $\mu$ to the current seismicity rate $\lambda(t_{now})$. An SRI of 100% means the system is fully quiet; a low SRI indicates active triggering cascades. Currently, Kutch remains in a long-term post-Bhuj decay phase with 3.61% recovery).

---

## 2. Present Tectonic State (SSI Module)
The Seismic Stress Index (SSI) is calculated using a 14-day sliding window ending at the present hour. It monitors tectonic reloading and instability.

* **Status:** Insufficient recent seismicity — last known state: LOW (2025-12-21)
* **SSI Parameter Breakdown:**
  * **b-value Stress Proxy ($S_{b}$):** nan (Fitted rolling b: nan)
  * **Event Rate Anomaly ($S_{rate}$):** 0.5000 (0 events $M \ge 3.0$ in last 14 days)
  * **Spatial Clustering ($S_{cluster}$):** nan (Mean nearest-neighbor distance: nan km)

---

## 3. Short-Term Conditional Forecast (ETAS Module)
The Epidemic Type Aftershock Sequence (ETAS) model simulates secondary triggering cascades (aftershocks triggering aftershocks) out-of-sample based on Kutch tectonic parameters.

| Horizon | Expected Count ($E[N \mid M \ge 3.0]$) | Probability of $\ge 1$ Event ($P(N \ge 1)$) | Probability of $\ge 5$ Events ($P(N \ge 5)$) |
|---|---|---|---|
| **7 Days** | 0.0964 | 9.19% | 0.00% |
| **14 Days** | 0.1926 | 17.51% | 0.00% |
| **30 Days** | 0.4114 | 33.73% | 0.01% |

*Parameters used: $\mu = 0.000498$/day, $K = 0.01522$, $\alpha = 1.2323$, $c = 0.000005$ days, $p = 0.9195$.*

---

## 4. Long-Term Hazard Baseline (PSHA Module)
Our long-term Probabilistic Seismic Hazard Analysis (PSHA) predicts Peak Ground Acceleration (PGA) values on bedrock:
* **Background Tectonic Loading Rate ($\mu$):** 0.000498/day ($\approx 0.1818$ events/year).
* **Long-Term Catalog Seismicity Rate:** 0.079400/day ($\approx 29.00$ events/year).
* **475-year PGA DBE (Bhuj):** **0.236g** (representing a 10% exceedance probability in 50 years; matches Zone V standard DBE of 0.18g).
* **2475-year PGA MCE (Bhuj):** **0.424g** (representing a 2% exceedance probability in 50 years; matches Zone V standard MCE of 0.36g).

*Comparing the current daily forecast rate ($r = 0.01377$ events/day) to the long-term PSHA catalog baseline rate ($R = 0.07940$/day) reveals that current triggering activity represents **0.17 times** the average historical catalog rate.*

---

## 5. Recommended Actions
* **Alert Status:** **LOW GREEN**
* **Actions:**
  1. Tectonic stress and event rates are within normal background limits.
  2. Continue standard open-source catalog harvesting and monitoring.
  3. No immediate emergency pre-positioning required.
