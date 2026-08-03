# Trikaal — Seismic Intelligence & Hazard Engine

An open-source, reproducible seismic hazard and forecasting pipeline for the **Kutch region, Gujarat, India** (bbox: 22°–24.5°N, 68°–71.5°E). 

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
│   ├── run_psha.py               # Grid hazard calculation and contour mapper
│   └── realtime_pipeline.py      # Phase 3 Real-time operational monitoring pipeline
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

### 4. Run Real-Time Operational Pipeline (Phase 3)
```bash
# Ingest near real-time events, update catalog, update forecasts, and output alert bulletin
python src/realtime_pipeline.py
```

### 5. Interactive Diagnostics
Launch Jupyter Notebook to explore the diagnostics:
```bash
jupyter notebook
# Open notebooks/01_eda.ipynb, notebooks/02_etas.ipynb, or notebooks/03_psha.ipynb
```

---

## Technical Summaries

### Phase 1: Epidemic Type Aftershock Sequence (ETAS)
Fits the Ogata (1988) point-process model utilizing a vectorized maximum likelihood estimation (MLE) solver.
- **Fitted Parameters:** $\mu = (4.98 \pm 3.38) \times 10^{-4}$ events/day, $K = 0.0152 \pm 0.0015$, $\alpha = 1.2323 \pm 0.0621$, $c = (4.68 \pm 2.00) \times 10^{-6}$ days, $p = 0.9195 \pm 0.0067$ (indicating slow intraplate decay).
- **Goodness-of-Fit:** Validated using the Papangelou time-rescaling theorem and Kolmogorov-Smirnov test ($p = 0.027$).
- **Retrospective Validation:** Achieves out-of-sample Brier Skill Scores of **68.9%–77.6%** and information gains of **9.3–10.1 bits/event** over a constant-rate Poisson baseline.

### Phase 2: Probabilistic Seismic Hazard Analysis (PSHA)
Integrates regional seismicity parameters to produce hazard curves and spatial maps showing Peak Ground Acceleration (PGA) at design return periods.
- **GMPE:** Employs the **Raghukanth & Iyengar (2007)** ground motion model calibrated for stable peninsular India bedrock.
- **Source Zones:** Models the Kutch Rift Zone as an area source combined with four discrete active fault traces: the Kachchh Mainland Fault (KMF), Island Belt Fault (IBF), Katrol Hill Fault (KHF), and Wagad Fault (WF).
- **Hazard Map Output:** Major cities (Bhuj, Anjar, Gandhidham) show a 475-year return period (10% exceedance in 50 years) PGA of **0.23–0.24g**, aligning with the Indian Seismic Code (IS 1893: 2016) Zone V hazard thresholds.

### Phase 3: Real-Time Operational Seismic Pipeline
Links the historical analyses, present tectonic states, and future forecasts into an operational monitoring loop.
- **Real-Time Data Ingestion:** Fetches near real-time USGS ComCat events since the last catalog entry and appends them to the processed dataset.
- **Tectonic State Tracking:** Recalculates the current composite Seismic Stress Index (SSI) using backward-looking windows and evaluates alert levels.
- **Risk Alert Level System:** Classifies the current risk level (LOW/MEDIUM/HIGH) based on the unique quantile boundaries of historical data and 7-day ETAS probabilities.
- **Baseline PSHA Comparison:** Quantifies current short-term triggering activity as an amplification factor relative to the long-term PSHA background tectonic loading rate ($\mu$).
- **Automated Bulletin Output:** Generates an official advisory report `outputs/seismic_bulletin.md` with action recommendations.