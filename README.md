# Trikaal — Kutch Seismic Data EDA

Exploratory analysis of earthquake catalog data for the **Kutch region, Gujarat, India** (bbox: 22°–24.5°N, 68°–71.5°E). Covers the full aftershock sequence of the **2001 Bhuj earthquake (Mw 7.7)** and broader seismicity from 1990 onward.

## Data Sources

| Source | Coverage | Access |
|--------|----------|--------|
| [USGS ComCat (FDSN)](https://earthquake.usgs.gov/fdsnws/event/1/) | Global, 1990–present | Free API |
| [ISC Bulletin](https://www.isc.ac.uk/iscbulletin/) | Global, historical | Free bulk download |
| [NCS / seismo.gov.in](https://seismo.gov.in) | India-specific | Registration / institutional |

## Project Layout

```
trikaal-/
├── data/
│   ├── raw/            # Downloaded catalogs (CSV)
│   └── processed/      # Cleaned & enriched catalog
├── notebooks/
│   └── 01_eda.ipynb    # Primary EDA notebook
├── outputs/            # Saved figures (PNG) + interactive map (HTML)
├── src/
│   ├── fetch_usgs.py   # Download USGS ComCat → data/raw/
│   └── preprocess.py   # Clean & enrich raw catalog
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Fetch Kutch earthquake catalog from USGS (1990–present, M≥2.0)
python src/fetch_usgs.py

# 3. Clean and enrich the raw catalog
python src/preprocess.py

# 4. Launch Jupyter and open the EDA notebook
jupyter notebook notebooks/01_eda.ipynb
```

## Key Analyses (notebook sections)

1. **Data Overview** — shape, date range, missing values
2. **Magnitude Distribution** — histogram + empirical CDF
3. **Depth Distribution** — shallow / intermediate / deep breakdown
4. **Temporal Trends** — annual counts, rolling seismicity rate
5. **Spatial Map** — scatter map + interactive Folium export with Bhuj epicenter marker
6. **Gutenberg-Richter** — MLE b-value estimation, completeness magnitude Mc
7. **Bhuj 2001 Aftershock Sequence** — Omori-Utsu decay fit (starting day 2 post-mainshock)

## Seismological Notes

- **depth_cat thresholds**: shallow < 70 km, intermediate 70–300 km, deep > 300 km (ISC/USGS convention)
- **b-value expectation for Kutch**: ~0.9–1.05 (published literature)
- **Bhuj mainshock**: 26 Jan 2001, Mw 7.7, epicenter 23.419°N 70.232°E
- **MLE b-value formula**: `b = log10(e) / (mean_M - Mc)` — preferred over least-squares regression