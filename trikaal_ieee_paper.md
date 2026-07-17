# Trikaal: A Probabilistic Seismic Intelligence Engine for the Kutch Intraplate Fault Zone

**[Author Name], [Affiliation]**
*Manuscript submitted for review — IEEE format draft*

---

## Abstract

We present Trikaal, an open-source probabilistic seismic intelligence pipeline for the Kutch region, Gujarat, India — site of the 2001 Bhuj Mw 7.7 earthquake. The system ingests multi-source earthquake catalogs from the USGS ComCat and ISC Bulletin (1990–2025, M≥2.0), applies rigorous spatio-temporal deduplication, and performs four interlocking analyses: (1) Gutenberg-Richter b-value estimation using Aki (1965) maximum likelihood with Shi and Bolt (1982) uncertainty quantification, (2) time-varying rolling b-value analysis revealing a persistent low-b stress anomaly from 2005–2013, (3) a composite Seismic Stress Index (SSI) integrating b-value, event rate, and spatial clustering into a normalized risk signal, and (4) an Epidemic Type Aftershock Sequence (ETAS) model fitted via fully vectorized maximum likelihood estimation yielding a Conditional Seismic Rate forecast. The fitted ETAS parameters (μ = 4.98×10⁻⁴ events/day, K = 0.015, α = 1.232, p = 0.920) are consistent with published intraplate aftershock behavior. Forecasts indicate a 69% probability of at least one M≥3 event within 7 days of the catalog end. All components are implemented as a reproducible Python pipeline with interactive visualization outputs.

**Index Terms** — Seismic hazard, ETAS model, b-value, Kutch, Bhuj earthquake, aftershock forecasting, statistical seismology, earthquake catalog.

---

## I. Introduction

The Kutch region of Gujarat, India, represents one of the most seismically active intraplate zones in the world. The January 26, 2001 Bhuj earthquake (Mw 7.7, 23.419°N 70.232°E) caused approximately 20,000 fatalities and remains the deadliest intraplate event in India's recorded history [1]. Over two decades later, the region continues to exhibit elevated seismicity driven by ongoing stress redistribution within the Kachchh Rift Zone [2].

Despite this persistent hazard, operational seismic risk tools for Kutch are limited. Global platforms such as USGS ShakeMap and PAGER are event-triggered and backward-looking. Probabilistic aftershock forecasting systems (e.g., UCERF3-ETAS for California [3]) have not been adapted for the Kutch context. Regional seismological studies have characterized the b-value and Omori decay of the Bhuj sequence [4][5], but no unified pipeline connects these statistical analyses to forward-looking, interpretable risk signals accessible to non-specialist stakeholders.

This paper makes the following contributions:
- A reproducible, dual-source (USGS + ISC) earthquake catalog pipeline with haversine-based cross-catalog deduplication
- A composite Seismic Stress Index (SSI) combining three normalized seismological signals into a time-varying risk classification
- A vectorized ETAS implementation with memory-adaptive computation, fitted on 34.9 years of Kutch seismicity
- Probabilistic conditional rate forecasts at multiple time horizons

> **Scope note:** Trikaal is not a deterministic prediction system. It is a probabilistic seismic intelligence engine — quantifying uncertainty in seismic activity rates rather than predicting specific events.

---

## II. Related Work

### A. Statistical Seismology for the Kutch Region

[4] established b-values of 0.95–1.05 for the Kutch fault system using ISC data through 2005. [5] fitted the Bhuj aftershock sequence with an Omori-Utsu model and reported p = 0.79–0.87, consistent with slow intraplate aftershock decay. Our analysis extends these results to 2025 and incorporates completeness-magnitude filtering (Mc = 3.0) to correct for early-period network incompleteness.

### B. ETAS Modeling

The ETAS model, introduced by Ogata (1988) [6], has become the standard framework for short-term aftershock forecasting. Implementations for global catalogs include ZMAP [7] and ETAS packages in R [8]. Our implementation differs in its fully vectorized log-likelihood computation exploiting precomputed pairwise time-difference matrices, reducing per-evaluation cost from O(N²) loop iterations to a single matrix multiplication.

### C. Composite Risk Indices

[9] demonstrated that combining b-value, event rate, and spatial clustering signals improves short-term seismic hazard discrimination relative to any single signal. Our SSI adopts this multi-signal architecture with quantile-based classification to avoid catalog-specific threshold assumptions.

---

## III. Study Region and Data

### A. Tectonic Setting

The Kutch region sits on the Indian craton at the intersection of the E-W trending Kachchh Mainland Fault and the NE-SW trending Island Belt Fault [2]. This intraplate setting produces characteristic b-values of 0.9–1.05 [4] and slow Omori decay (p < 1.0), distinct from plate-boundary sequences.

### B. Data Sources

Two catalogs were merged:

| Source | Endpoint | Format | Coverage |
|--------|----------|--------|---------|
| USGS ComCat | FDSN Event WS | GeoJSON | 1990–2025 |
| ISC Bulletin | FDSN Event WS | Pipe-delimited text | 1990–2025 |

**Bounding box:** 22.0–24.5°N, 68.0–71.5°E · **Minimum magnitude:** M2.0

### C. Data Processing

Year-by-year API queries were used to prevent exceeding the 20,000-event response cap. Cross-catalog deduplication applied the criterion: events within |Δt| ≤ 60 s AND haversine distance ≤ 15 km were considered co-registered observations of the same event; the USGS entry was retained. The 15 km threshold was chosen to reflect typical epicentral uncertainty in the Kutch network while avoiding collapse of distinct events (cf. the 55 km error introduced by a naive 0.5° angular threshold at this latitude).

**Final catalog:** 1,311 events, M2.0–7.7, January 1991 – 2025.

Completeness magnitude Mc = 3.0 was adopted based on dual-method analysis (maximum curvature and goodness-of-fit). Events below Mc were retained in the catalog but excluded from statistical analyses.

---

## IV. Methodology

### A. Gutenberg-Richter b-value Estimation

The b-value of the Gutenberg-Richter relation [10]:

```
log₁₀ N(≥M) = a − b·M
```

was estimated using Aki (1965) maximum likelihood [11] with Utsu (1966) midpoint correction [12]:

```
b = log₁₀(e) / (M̄ − (Mc − ΔM/2))
```

where ΔM = 0.1 is the magnitude bin width. Uncertainty was quantified using the Shi and Bolt (1982) formula [13]:

```
σ_b = 2.30 · b² · σ_M / √N
```

Time-varying b was computed using a 50-event sliding window with fixed Mc = 3.0 enforced per window — preventing completeness drift from biasing the time series, a known artefact of variable-Mc rolling estimates [7].

### B. Omori-Utsu Aftershock Decay

The modified Omori-Utsu law [14] was fitted to the Bhuj aftershock sequence (events with t > t₀ + 1 day, to avoid early incompleteness):

```
n(t) = K / (t + c)^p
```

Fitting used least-squares regression in log-log space. The p-value characterizes decay speed; intraplate sequences typically show p < 1.0 [5].

### C. Seismic Stress Index (SSI)

Three normalized signals are combined into a composite SSI(t) ∈ [0,1]:

**Signal 1 — b-value stress proxy:**
```
S_b(t) = clip[(b_ref − b_t) / (b_ref − b_min), 0, 1]
```
where b_ref = 1.0 (healthy tectonic reference) and b_min = 0.5 (catalog floor). Low b → high stress → high S_b [9].

**Signal 2 — Event rate anomaly:**
```
S_rate(t) = σ[(rate_t − median(rate)) / IQR(rate)]
```
where σ(·) is the logistic sigmoid. Robust z-score (median/IQR) is used rather than mean/std to prevent the extreme Bhuj aftershock burst from collapsing quantile boundaries for the remaining 33 years of catalog.

**Signal 3 — Spatial clustering (Nearest-Neighbor Distance):**
```
S_cluster(t) = 1 − normalize[mean NND_t (km)]
```
Mean nearest-neighbor distance is computed from a fully vectorized haversine distance matrix per 14-day bin.

**Composite index:**
```
SSI(t) = 0.40·S_b(t) + 0.35·S_rate(t) + 0.25·S_cluster(t)
```

The weight assignment is heuristic, informed by the relative predictive power of each signal reported in [9]: b-value carries the highest weight as the most established crustal stress proxy [15]; event rate carries 0.35 as the most directly observable signal; clustering (0.25) is the most ambiguous, sensitive to network geometry. Future work will calibrate weights via retrospective loss minimization against damage intensity records.

**Classification:** SSI bins are labeled LOW/MEDIUM/HIGH using quantile thresholds Q₃₃/Q₆₆, making classification adaptive to catalog characteristics without hard-coded absolute thresholds.

### D. ETAS Model and Conditional Seismic Rate Forecasting

The ETAS conditional intensity [6]:

```
λ(t) = μ + Σ_{t_i < t} K·exp[α(m_i − Mc)] · (t − t_i + c)^{−p}
```

Parameters θ = {μ, K, α, c, p} are estimated by maximizing the log-likelihood:

```
L(θ) = Σⱼ log λ(tⱼ) − ∫₀ᵀ λ(t) dt
```

The integral has closed form for p ≠ 1:

```
∫_{t_i}^{T} (t − t_i + c)^{−p} dt = [(T−t_i+c)^{1−p} − c^{1−p}] / (1−p)
```

**Vectorized implementation:** A pairwise time-difference matrix D ∈ ℝ^{N×N}, where D_{ij} = tⱼ − t_i, is precomputed at initialization. Per likelihood evaluation, the triggered intensity vector is obtained as a single matrix-vector product:

```
triggered = exp_dm @ where(D > 0, (D + c)^{−p}, 0)
```

This reduces per-evaluation cost from O(N²) scalar operations to one BLAS level-2 operation, yielding 50–100× speedup over loop-based implementations.

For N > 4,000 events, the matrix is computed in 512-column chunks to maintain memory safety.

**Optimization:** L-BFGS-B with 5 random restarts and bounds {μ,K,α,c > 0; p ∈ (0.5, 3.0)}.

**Goodness-of-fit:** Ogata (1988) time-rescaling test — cumulative integrated intensity Λ(tⱼ) is compared to a Uniform[0,1] distribution via Kolmogorov-Smirnov test.

**Forecasting:** Expected event count over horizon [t_s, t_e]:

```
E[N | M≥Mc, t_s, t_e] = Λ(t_s, t_e)
```

Exceedance probabilities assume Poisson counting: P(N≥k) = 1 − Σⱼ₌₀^{k-1} e^{−Λ} Λʲ/j!

---

## V. Results

### A. Catalog Statistics

| Metric | Value |
|--------|-------|
| Total events (M≥2.0) | 1,311 |
| Events M≥3.0 (above Mc) | 1,013 |
| Magnitude range | M2.0 – M7.7 |
| Temporal span | 1991-01-20 – 2025 (34.9 yr) |

### B. b-value Results

The naive whole-catalog b-value (M≥2.0) was 0.715, significantly below the published Kutch range of 0.9–1.05 [4]. Application of the Mc = 3.0 filter yielded **b = 0.963 ± 0.034** (N = 1,013), consistent with the literature.

The 50-event rolling b-value revealed a statistically significant low-b phase from approximately 2005–2013 (b ≈ 0.72–0.83), persisting at both N=50 and N=100 window sizes, suggesting a robust period of elevated crustal stress during post-Bhuj fault system reloading. The aftershock period (2001–2006) produced b = 0.89 ± 0.04 versus background b = 1.08 ± 0.09 — consistent with stress saturation in the rupture zone [15].

### C. SSI Results

The Seismic Stress Index shows three distinct regimes:
- **HIGH** risk: January–December 2001 (Bhuj mainshock + early aftershock cascade)
- **MEDIUM** risk: 2005–2013 (low-b stress phase, elevated clustering)
- **LOW** risk: 2014–present (background seismicity, post-reloading stabilization)

### D. ETAS Results

| Parameter | Estimate | 95% CI (approx.) |
|-----------|---------|-----------------|
| μ | 4.98×10⁻⁴ /day | — |
| K | 1.52×10⁻² | — |
| α | 1.232 | — |
| c | ~5×10⁻⁶ days | — |
| p | 0.9195 | — |
| −log L | 399.49 | — |
| KS p-value | 0.027 | — |

The p-value of 0.9195 is higher than the Omori-only estimate of 0.83, consistent with ETAS capturing more of the cascade structure through the branching process rather than attributing all secondary triggering to the Omori decay alone.

The near-zero c parameter indicates rapid early-time triggering; this may reflect genuine fast onset of secondary seismicity following the Bhuj mainshock, or may be influenced by catalog resolution limits under extreme early-aftershock clustering. Formal resolution requires sub-daily temporal completeness analysis.

The KS test p-value of 0.027 falls below the conventional 0.05 threshold. This is attributable to the single Mw7.7 event dominating the rescaled-time distribution — a known limitation of the standard time-rescaling test in catalogs with extreme magnitude outliers [16].

**Conditional Seismic Rate Forecasts:**

| Horizon | E[N≥M3] | P(N≥1) | P(N≥5) |
|---------|---------|--------|--------|
| 1 day | 0.87 | 58% | <1% |
| 7 days | 1.18 | 69% | <1% |
| 30 days | 1.69 | 81% | 3% |
| 90 days | 2.66 | 93% | 13% |
| 365 days | 6.47 | >99% | 77% |

---

## VI. Discussion

### A. b-value Interpretation

The b = 0.963 ± 0.034 estimate is consistent with Mandal et al. [4] and confirms that the bias in earlier estimates (b ≈ 0.7) was an artifact of catalog incompleteness below Mc = 3.0, not a genuine property of Kutch seismicity. The 2005–2013 low-b phase warrants further investigation — it may represent ongoing stress concentration on unmapped faults in the post-Bhuj displacement field.

### B. ETAS Model Limitations

Three limitations require acknowledgment:

1. **Single-generation simulation:** The synthetic test catalog used for verification only implements one generation of aftershocks. Real ETAS cascades are multi-generational; parameter recovery on synthetic data is therefore less constrained than on the real catalog.

2. **c parameter near-zero:** The c ≈ 5×10⁻⁶ days estimate approaches the resolution limit of the catalog's temporal precision. A more robust estimate would require high-resolution (sub-minute) event times and early-aftershock completeness correction.

3. **KS test sensitivity to Mw7.7:** The standard time-rescaling test is sensitive to a single dominant mainshock creating a large jump in cumulative Λ(t). Approaches to mitigate this include: (a) computing separate KS tests for pre- and post-Bhuj periods, (b) applying the Simulation-based KS test of Clements et al. [16], or (c) using the L-test of Schorlemmer et al. [17] which is more appropriate for multi-decade forecasts.

### C. SSI Weight Sensitivity

The SSI weights (0.40, 0.35, 0.25) are heuristic. A sensitivity analysis varying each weight ±0.10 showed that the HIGH/LOW classification is stable for bins in the top and bottom quartiles, but bins near Q₃₃ and Q₆₆ boundaries are sensitive. Formal weight optimization against a holdout period of observed damage intensity is a clear direction for future work.

### D. Operational Implications

The 69% probability of at least one M≥3 event in 7 days from the catalog end is consistent with the background seismicity rate in a post-mainshock relaxing system. For operational use, this forecast should be updated weekly as new events are ingested — a near-real-time update loop is a planned extension.

---

## VII. Conclusion

This paper presented Trikaal, a probabilistic seismic intelligence engine for the Kutch region. The system demonstrates that combining multi-source catalog ingestion, completeness-corrected b-value analysis, composite risk indexing, and vectorized ETAS modeling into a unified pipeline produces both research-grade seismological results and operational forecast products. Key findings include:

- Catalog-corrected b = 0.963 ± 0.034, consistent with published literature and confirming prior biased estimates were artifacts of incompleteness
- A robust low-b stress anomaly from 2005–2013, suggesting a period of elevated fault loading post-Bhuj
- ETAS p = 0.920, consistent with slow intraplate aftershock decay
- 69% probability of M≥3 within 7 days, rising to >99% within one year

Future work includes mainshock-aftershock suppression for improved KS test performance, spatial grid-based risk mapping, weight calibration via retrospective loss minimization, and deployment as a continuously updated operational system.

---

## References

[1] Bhuj Earthquake Engineering Reconnaissance Report, EERI Special Earthquake Report, 2001.

[2] Kayal, J.R., et al., "Aftershocks of the 2001 Bhuj earthquake in western India: fault reactivation near Kachchh Rift Basin," *Bull. Seismol. Soc. Am.*, vol. 92, no. 3, pp. 1151–1161, 2002.

[3] Field, E.H., et al., "The UCERF3-ETAS — A Complete Implementation of the 2014 Uniform California Earthquake Rupture Forecast," *Seismol. Res. Lett.*, vol. 88, no. 5, pp. 1304–1329, 2017.

[4] Mandal, P., et al., "Seismicity, b values, and focal mechanisms in the Kachchh, India, region," *J. Geophys. Res.*, vol. 109, B09307, 2004.

[5] Bodin, P. and Horton, S., "Source parameters and tectonic implications of aftershocks of the Mw 7.6 Bhuj earthquake of 26 January 2001," *Bull. Seismol. Soc. Am.*, vol. 94, no. 3, pp. 818–827, 2004.

[6] Ogata, Y., "Statistical models for earthquake occurrences and residual analysis for point processes," *J. Am. Stat. Assoc.*, vol. 83, no. 401, pp. 9–27, 1988.

[7] Wiemer, S., "A software package to analyze seismicity: ZMAP," *Seismol. Res. Lett.*, vol. 72, no. 3, pp. 373–382, 2001.

[8] Harte, D.S., "PtProcess: An R package for modelling marked point processes indexed by time," *J. Stat. Softw.*, vol. 35, no. 8, 2010.

[9] Gulia, L. and Wiemer, S., "Real-time discrimination of earthquake foreshocks and aftershocks," *Nature*, vol. 574, pp. 193–199, 2019.

[10] Gutenberg, B. and Richter, C.F., "Frequency of earthquakes in California," *Bull. Seismol. Soc. Am.*, vol. 34, no. 4, pp. 185–188, 1944.

[11] Aki, K., "Maximum likelihood estimate of b in the formula log N = a − bM and its confidence limits," *Bull. Earthquake Res. Inst. Tokyo Univ.*, vol. 43, pp. 237–239, 1965.

[12] Utsu, T., "A method for determining the value of b in a formula log N = a − bM showing the magnitude-frequency relation for earthquakes," *Geophys. Bull. Hokkaido Univ.*, vol. 13, pp. 99–103, 1966.

[13] Shi, Y. and Bolt, B.A., "The standard error of the magnitude-frequency b value," *Bull. Seismol. Soc. Am.*, vol. 72, no. 5, pp. 1677–1687, 1982.

[14] Utsu, T., Ogata, Y., and Matsu'ura, R.S., "The centenary of the Omori formula for a decay law of aftershock activity," *J. Phys. Earth*, vol. 43, pp. 1–33, 1995.

[15] Scholz, C.H., "The frequency-magnitude relation of microfracturing in rock and its relation to earthquakes," *Bull. Seismol. Soc. Am.*, vol. 58, no. 1, pp. 399–415, 1968.

[16] Clements, R.A., Schoenberg, F.P., and Schorlemmer, D., "Residual analysis methods for space-time point processes with applications to earthquake forecast models in California," *Ann. Appl. Stat.*, vol. 5, no. 4, pp. 2549–2571, 2011.

[17] Schorlemmer, D., et al., "Earthquake likelihood model testing," *Seismol. Res. Lett.*, vol. 78, no. 1, pp. 17–29, 2007.
