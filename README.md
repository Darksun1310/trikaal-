# Trikaal — Seismic Intelligence & Hazard Engine

An open-source research-grade seismic hazard and forecasting pipeline for the **Kutch region, Gujarat, India** (bbox: 22°–24.5°N, 68°–71.5°E). 

Covers the full aftershock sequence of the **2001 Bhuj earthquake (Mw 7.7)** and broader regional seismicity from 1990 to the present using dual-source catalog merging, epidemic aftershock sequence modeling, and probabilistic hazard analysis.

---

## Data Sources

| Source | Coverage | Access |
|--------|----------|--------|
| [USGS ComCat (FDSN)](https://earthquake.usgs.gov/fdsnws/event/1/) | Global, 1990–present | Free API |
| [ISC Bulletin](https://www.isc.ac.uk/iscbulletin/) | Global, historical | Free bulk download |
| [NCS / seismo.gov.in](https://seismo.gov.in) | India-specific | Registration / institutional |

---

## Project Layout

```
trikaal-/
├── data/
│   ├── raw/                      # Downloaded catalogs (USGS + ISC CSVs)
│   └── processed/                # Cleaned, deduped, and enriched catalog
├── notebooks/
│   ├── 01_eda.ipynb              # Catalog EDA & b-value sensitivity analysis
│   ├── 02_etas.ipynb             # ETAS fitting diagnostics & rescaled-time QQ plots
│   └── 03_psha.ipynb             # PSHA hazard curves & GMPE comparisons
├── outputs/                      # Saved plots (PNG) + interactive maps (HTML) + parameters (JSON)
│   ├── etas_params.json          # Fitted ETAS parameters
│   ├── etas_forecast.csv         # Multi-horizon expected counts
│   ├── kutch_hazard_grid.csv     # Spatial grid hazard values (PGA)
│   ├── kutch_hazard_interactive.html  # Interactive Folium hazard map
│   └── *.png                     # Generated static figures and maps
├── src/
│   ├── fetch_usgs.py             # USGS FDSN catalog downloader
│   ├── fetch_isc.py              # ISC Bulletin catalog downloader
│   ├── preprocess.py             # Haversine-based catalog merge & deduplication
│   ├── refit_analysis.py         # Gutenberg-Richter Aki MLE & aftershock split
│   ├── risk_score.py             # Composite Seismic Stress Index (SSI) engine
│   ├── risk_dashboard.py         # Interactive HTML risk dashboard generator
│   ├── etas_model.py             # Vectorized Ogata (1988) ETAS MLE solver
│   ├── etas_forecast.py          # Horizonal forecasting and Poisson exceedance calculator
│   ├── run_etas.py               # Runner script for ETAS fit and forecasting
│   ├── psha.py                   # PSHA integration engine and regional GMPEs
│   └── run_psha.py               # Grid hazard calculation and contour mapper
└── requirements.txt              # Project dependencies
```

---

## Quick Start

### 1. Environment Setup
```bash
# Create and activate python virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Data Pipeline
```bash
# Fetch and merge catalogs
python src/fetch_usgs.py
python src/fetch_isc.py
python src/preprocess.py

# Run descriptive and composite risk analyses
python src/refit_analysis.py
python src/risk_score.py
python src/risk_dashboard.py
```

### 3. Run ETAS & PSHA Forecasting Engines
```bash
# Fit ETAS model and generate forecasts
python src/run_etas.py

# Run Probabilistic Seismic Hazard Analysis and plot hazard maps
python src/run_psha.py
```

### 4. Interactive Diagnostics
Launch Jupyter Notebook to explore the diagnostics:
```bash
jupyter notebook
# Open notebooks/01_eda.ipynb, notebooks/02_etas.ipynb, or notebooks/03_psha.ipynb
```

---

## Technical Summaries

### Phase 1: Epidemic Type Aftershock Sequence (ETAS)
Fits the Ogata (1988) point-process model utilizing a vectorized maximum likelihood estimation (MLE) solver.
- **Fitted Parameters:** $\mu = 4.98 \times 10^{-4}$ events/day (low background rate, Kutch is triggering-dominated), $K = 0.015$, $\alpha = 1.232$, $p = 0.920$ (slow intraplate aftershock decay).
- **Goodness-of-Fit:** Validated using the Papangelou time-rescaling theorem and Kolmogorov-Smirnov test.
- **Short-Term Forecast:** 69% probability of at least one $M \ge 3.0$ event within a 7-day window.

### Phase 2: Probabilistic Seismic Hazard Analysis (PSHA)
Integrates regional seismicity parameters to produce hazard curves and spatial maps showing Peak Ground Acceleration (PGA) at design return periods.
- **GMPE:** Employs the **Raghukanth & Iyengar (2007)** ground motion model calibrated for stable peninsular India bedrock.
- **Source Zones:** Models the Kutch Rift Zone as an area source combined with four discrete active fault traces: the Kachchh Mainland Fault (KMF), Island Belt Fault (IBF), Katrol Hill Fault (KHF), and Wagad Fault (WF).
- **Hazard Map Output:** Major cities (Bhuj, Anjar, Gandhidham) show a 475-year return period (10% exceedance in 50 years) PGA of **0.23–0.24g**, aligning with the Indian Seismic Code (IS 1893: 2016) Zone V hazard thresholds.