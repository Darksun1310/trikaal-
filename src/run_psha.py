"""
run_psha.py
-----------
Trikaal — Pipeline script to execute Probabilistic Seismic Hazard Analysis (PSHA).
Sets up Kutch grid, runs hazard integral, outputs static maps, curves for key cities,
and generates an interactive HTML map.
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # headless mode for plotting stability
import matplotlib.pyplot as plt
import folium
from folium.plugins import HeatMap
from scipy.interpolate import griddata

from psha import (
    raghukanth_iyengar_2007,
    atkinson_boore_2006,
    boore_et_al_2014,
    AreaSource,
    LineSource,
    PSHAEngine,
    interpolate_pga_hazard
)

# Setup directories
DATA_DIR = Path("data")
PROCESSED_DIR = DATA_DIR / "processed"
OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)

# Grid Settings
MIN_LAT, MAX_LAT = 22.0, 24.5
MIN_LON, MAX_LON = 68.0, 71.5
GRID_RESOLUTION = 0.1  # ~10 km spacing

# Cities for site-specific hazard analysis
CITIES = {
    "Bhuj": (23.24, 69.67),
    "Anjar": (23.11, 70.03),
    "Gandhidham": (23.08, 70.13),
    "Mandvi": (22.84, 69.36),
    "Lakhpat": (23.83, 68.78),
}

def main():
    print("=== Launching Trikaal PSHA Pipeline ===")
    
    # 1. Load catalog & calculate seismicity rate
    clean_cat_path = PROCESSED_DIR / "kutch_clean.csv"
    if not clean_cat_path.exists():
        raise FileNotFoundError(f"Clean catalog not found at {clean_cat_path}. Run fetch and preprocess first.")
    
    df_cat = pd.read_csv(clean_cat_path, parse_dates=["time_utc"])
    df_m3 = df_cat[df_cat["magnitude"] >= 3.0].sort_values("time_utc")
    
    N_events = len(df_m3)
    t_start = df_m3["time_utc"].iloc[0]
    t_end = df_m3["time_utc"].iloc[-1]
    catalog_years = (t_end - t_start).total_seconds() / (365.25 * 86400.0)
    
    overall_annual_rate = N_events / catalog_years
    print(f"Loaded catalog: {N_events} events M>=3.0 over {catalog_years:.2f} years")
    print(f"Overall catalog annual rate (M>=3.0): {overall_annual_rate:.4f} events/year")
    
    # Standard ETAS background rate:
    # From etas_params.json (mu ~ 0.0004977 events/day -> 0.1817 events/year)
    etas_params_path = OUT_DIR / "etas_params.json"
    if etas_params_path.exists():
        import json
        with open(etas_params_path) as f:
            params = json.load(f)
        mu_day = params.get("mu", 0.0004977)
        background_annual_rate = mu_day * 365.25
        print(f"ETAS Background annual rate: {background_annual_rate:.4f} events/year")
    else:
        background_annual_rate = 0.1817
        print(f"ETAS background parameters not found. Using default background rate: {background_annual_rate:.4f} events/year")

    # Use background b-value from refit_analysis (1.08)
    b_value = 1.08
    print(f"Selected b-value: {b_value}")
    
    # 2. Define Seismic Source Zones for Kutch
    # We combine both area and line sources to represent the faults and background zone
    area_kutch = AreaSource("Kutch Rift Zone", MIN_LAT, MAX_LAT, MIN_LON, MAX_LON, depth=15.0)
    
    # Fault traces (Line Sources)
    kmf = LineSource("Kachchh Mainland Fault (KMF)", 23.40, 68.50, 23.40, 71.00, depth=15.0)
    ibf = LineSource("Island Belt Fault (IBF)", 24.20, 68.50, 24.20, 71.00, depth=15.0)
    khf = LineSource("Katrol Hill Fault (KHF)", 23.15, 68.80, 23.15, 70.80, depth=15.0)
    wf  = LineSource("Wagad Fault (WF)", 23.55, 70.00, 23.55, 70.60, depth=12.0)
    
    sources = [area_kutch, kmf, ibf, khf, wf]
    print(f"Initialized sources: {[s.name for s in sources]}")

    # Set up engine with Raghukanth & Iyengar (2007) GMPE
    engine_ri = PSHAEngine(sources, gmpe_func=raghukanth_iyengar_2007)
    # Set up engine with Boore et al. (2014) reference
    engine_ba = PSHAEngine(sources, gmpe_func=boore_et_al_2014)

    # 3. Compute Site-Specific Hazard Curves for Key Cities
    print("\nCalculating hazard curves for key cities...")
    pga_levels = np.logspace(-3, 0.5, 80)  # PGA from 0.001g to 3.16g
    city_curves = {}
    
    for city, coords in CITIES.items():
        lat, lon = coords
        # Overall catalog rate
        rates_ri_overall = engine_ri.compute_hazard_curve(
            lat, lon, pga_levels, overall_annual_rate, b_value, Mc=3.0, Mmax=7.7
        )
        # Background tectonic rate
        rates_ri_bg = engine_ri.compute_hazard_curve(
            lat, lon, pga_levels, background_annual_rate, b_value, Mc=3.0, Mmax=7.7
        )
        # Boore et al. 2014 for reference (overall rate)
        rates_ba_overall = engine_ba.compute_hazard_curve(
            lat, lon, pga_levels, overall_annual_rate, b_value, Mc=3.0, Mmax=7.7
        )
        
        city_curves[city] = {
            "rates_ri_overall": rates_ri_overall,
            "rates_ri_bg": rates_ri_bg,
            "rates_ba_overall": rates_ba_overall,
            "pga_475_ri": interpolate_pga_hazard(pga_levels, rates_ri_overall, 0.10, 50.0),
            "pga_2475_ri": interpolate_pga_hazard(pga_levels, rates_ri_overall, 0.02, 50.0),
            "pga_475_bg": interpolate_pga_hazard(pga_levels, rates_ri_bg, 0.10, 50.0),
            "pga_2475_bg": interpolate_pga_hazard(pga_levels, rates_ri_bg, 0.02, 50.0),
        }
        
        print(f"  {city} (lat={lat}, lon={lon}):")
        print(f"    Raghukanth & Iyengar (Overall Rate) -> PGA(10%/50y) = {city_curves[city]['pga_475_ri']:.4f}g, PGA(2%/50y) = {city_curves[city]['pga_2475_ri']:.4f}g")
        print(f"    Raghukanth & Iyengar (Background)   -> PGA(10%/50y) = {city_curves[city]['pga_475_bg']:.4f}g, PGA(2%/50y) = {city_curves[city]['pga_2475_bg']:.4f}g")

    # Plot curves for Cities
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    
    # Left Panel: Raghukanth & Iyengar (Overall vs Background)
    ax = axes[0]
    colors = ["#2563EB", "#DC2626", "#EA580C", "#16A34A", "#7C3AED"]
    for i, (city, data) in enumerate(city_curves.items()):
        ax.loglog(pga_levels, data["rates_ri_overall"], "-", color=colors[i], label=f"{city} (Overall)")
        ax.loglog(pga_levels, data["rates_ri_bg"], "--", color=colors[i], label=f"{city} (Background)")
        
    ax.axhline(0.00211, color="black", linestyle=":", alpha=0.7, label="10% in 50 yr (475 yr return)")
    ax.axhline(0.00040, color="red", linestyle=":", alpha=0.7, label="2% in 50 yr (2475 yr return)")
    ax.set_xlabel("Peak Ground Acceleration PGA (g)")
    ax.set_ylabel("Annual Exceedance Rate (1/year)")
    ax.set_title("Hazard Curves: Raghukanth & Iyengar (2007)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    
    # Right Panel: GMPE Comparison (Overall Rate)
    ax = axes[1]
    for i, (city, data) in enumerate(city_curves.items()):
        ax.loglog(pga_levels, data["rates_ri_overall"], "-", color=colors[i], label=f"{city} (R&I 2007)")
        ax.loglog(pga_levels, data["rates_ba_overall"], ":", color=colors[i], label=f"{city} (BSSA 14)")
        
    ax.axhline(0.00211, color="black", linestyle=":", alpha=0.7, label="10% in 50 yr")
    ax.axhline(0.00040, color="red", linestyle=":", alpha=0.7, label="2% in 50 yr")
    ax.set_xlabel("Peak Ground Acceleration PGA (g)")
    ax.set_title("Hazard Curves: Stable (R&I) vs. Active (BSSA14)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    
    plt.suptitle("Probabilistic Seismic Hazard Analysis (PSHA) City Comparison", fontsize=14, y=0.98)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "hazard_curves_cities.png", dpi=150)
    plt.close(fig)
    print("Saved: outputs/hazard_curves_cities.png")

    # 4. Compute Grid Hazard Map
    print("\nCalculating spatial hazard map over Kutch grid...")
    lats = np.arange(MIN_LAT, MAX_LAT + 0.01, GRID_RESOLUTION)
    lons = np.arange(MIN_LON, MAX_LON + 0.01, GRID_RESOLUTION)
    
    grid_coords = []
    pga_475_list = []
    pga_2475_list = []
    pga_475_bg_list = []
    
    total_grid_points = len(lats) * len(lons)
    idx_pt = 0
    
    for lat in lats:
        for lon in lons:
            idx_pt += 1
            if idx_pt % 100 == 0:
                print(f"  Computed {idx_pt}/{total_grid_points} grid points...")
                
            rates_overall = engine_ri.compute_hazard_curve(
                lat, lon, pga_levels, overall_annual_rate, b_value, Mc=3.0, Mmax=7.7
            )
            rates_bg = engine_ri.compute_hazard_curve(
                lat, lon, pga_levels, background_annual_rate, b_value, Mc=3.0, Mmax=7.7
            )
            
            pga_475 = interpolate_pga_hazard(pga_levels, rates_overall, 0.10, 50.0)
            pga_2475 = interpolate_pga_hazard(pga_levels, rates_overall, 0.02, 50.0)
            pga_475_bg = interpolate_pga_hazard(pga_levels, rates_bg, 0.10, 50.0)
            
            grid_coords.append((lat, lon))
            pga_475_list.append(pga_475)
            pga_2475_list.append(pga_2475)
            pga_475_bg_list.append(pga_475_bg)
            
    # Save Grid Data
    df_grid = pd.DataFrame({
        "latitude": [c[0] for c in grid_coords],
        "longitude": [c[1] for c in grid_coords],
        "pga_475_overall": pga_475_list,
        "pga_2475_overall": pga_2475_list,
        "pga_475_bg": pga_475_bg_list,
    })
    df_grid.to_csv(OUT_DIR / "kutch_hazard_grid.csv", index=False)
    print("Saved: outputs/kutch_hazard_grid.csv")

    # Interpolate for contour plotting
    grid_x, grid_y = np.meshgrid(
        np.linspace(MIN_LON, MAX_LON, 300),
        np.linspace(MIN_LAT, MAX_LAT, 300)
    )
    
    # 5. Plot Spatial Hazard Map: 10% exceedance in 50 years (475 yr return period)
    fig, ax = plt.subplots(figsize=(10, 7))
    grid_z1 = griddata(
        (df_grid["longitude"], df_grid["latitude"]),
        df_grid["pga_475_overall"],
        (grid_x, grid_y),
        method="cubic"
    )
    
    contour = ax.contourf(grid_x, grid_y, grid_z1, levels=15, cmap="magma_r")
    cbar = fig.colorbar(contour, label="PGA (g)")
    
    # Add faults for context
    ax.plot([68.5, 71.0], [23.4, 23.4], "r-", linewidth=2.0, label="Kachchh Mainland Fault")
    ax.plot([68.5, 71.0], [24.2, 24.2], "b-", linewidth=1.5, label="Island Belt Fault")
    ax.plot([68.8, 70.8], [23.15, 23.15], "g-", linewidth=1.5, label="Katrol Hill Fault")
    ax.plot([70.0, 70.6], [23.55, 23.55], "m-", linewidth=2.0, label="Wagad Fault")
    
    # Plot key cities
    for city, coords in CITIES.items():
        ax.plot(coords[1], coords[0], "ks")
        ax.annotate(f"  {city}", (coords[1], coords[0]), fontsize=9, fontweight="bold")
        
    ax.set_xlim(MIN_LON, MAX_LON)
    ax.set_ylim(MIN_LAT, MAX_LAT)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Kutch Seismic Hazard Map: PGA at 10% Exceedance in 50 years\n(475-Year Return Period, Raghukanth & Iyengar 2007)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "hazard_map_475.png", dpi=150)
    plt.close(fig)
    print("Saved: outputs/hazard_map_475.png")

    # 6. Plot Spatial Hazard Map: 2% exceedance in 50 years (2475 yr return period)
    fig, ax = plt.subplots(figsize=(10, 7))
    grid_z2 = griddata(
        (df_grid["longitude"], df_grid["latitude"]),
        df_grid["pga_2475_overall"],
        (grid_x, grid_y),
        method="cubic"
    )
    
    contour2 = ax.contourf(grid_x, grid_y, grid_z2, levels=15, cmap="magma_r")
    cbar2 = fig.colorbar(contour2, label="PGA (g)")
    
    # Add faults
    ax.plot([68.5, 71.0], [23.4, 23.4], "r-", linewidth=2.0, label="KMF")
    ax.plot([68.5, 71.0], [24.2, 24.2], "b-", linewidth=1.5, label="IBF")
    ax.plot([68.8, 70.8], [23.15, 23.15], "g-", linewidth=1.5, label="KHF")
    ax.plot([70.0, 70.6], [23.55, 23.55], "m-", linewidth=2.0, label="WF")
    
    for city, coords in CITIES.items():
        ax.plot(coords[1], coords[0], "ks")
        ax.annotate(f"  {city}", (coords[1], coords[0]), fontsize=9, fontweight="bold")
        
    ax.set_xlim(MIN_LON, MAX_LON)
    ax.set_ylim(MIN_LAT, MAX_LAT)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Kutch Seismic Hazard Map: PGA at 2% Exceedance in 50 years\n(2475-Year Return Period, Raghukanth & Iyengar 2007)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "hazard_map_2475.png", dpi=150)
    plt.close(fig)
    print("Saved: outputs/hazard_map_2475.png")

    # 7. Create Interactive Folium Map
    print("\nGenerating interactive Folium map...")
    m = folium.Map(location=[23.3, 69.8], zoom_start=8, tiles="CartoDB positron")
    
    # Draw major faults as lines
    folium.PolyLine(
        locations=[[23.40, 68.50], [23.40, 71.00]],
        color="red", weight=4, opacity=0.8,
        tooltip="Kachchh Mainland Fault (KMF)"
    ).add_to(m)
    
    folium.PolyLine(
        locations=[[24.20, 68.50], [24.20, 71.00]],
        color="blue", weight=3, opacity=0.8,
        tooltip="Island Belt Fault (IBF)"
    ).add_to(m)
    
    folium.PolyLine(
        locations=[[23.15, 68.80], [23.15, 70.80]],
        color="green", weight=3, opacity=0.8,
        tooltip="Katrol Hill Fault (KHF)"
    ).add_to(m)
    
    folium.PolyLine(
        locations=[[23.55, 70.00], [23.55, 70.60]],
        color="purple", weight=4, opacity=0.8,
        tooltip="Wagad Fault (WF)"
    ).add_to(m)

    # 2001 Bhuj Epicenter Marker
    folium.Marker(
        location=[23.419, 70.232],
        popup="<b>2001 Bhuj Epicenter (Mw 7.7)</b><br>Date: 26 Jan 2001<br>Depth: 16 km",
        icon=folium.Icon(color="darkred", icon="star")
    ).add_to(m)

    # Add City Markers with Site-Specific PGA Hazard
    for city, coords in CITIES.items():
        data = city_curves[city]
        popup_html = f"""
        <div style="font-family: Arial; width: 220px;">
            <h4>{city} Seismic Hazard</h4>
            <table style="width:100%; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #ddd;">
                    <th style="text-align: left; padding: 4px;">Return Period</th>
                    <th style="text-align: right; padding: 4px;">PGA (g)</th>
                </tr>
                <tr>
                    <td style="padding: 4px;">475 Years (10% in 50y)</td>
                    <td style="text-align: right; padding: 4px; font-weight: bold; color: #E67E22;">{data['pga_475_ri']:.3f}g</td>
                </tr>
                <tr>
                    <td style="padding: 4px;">2475 Years (2% in 50y)</td>
                    <td style="text-align: right; padding: 4px; font-weight: bold; color: #C0392B;">{data['pga_2475_ri']:.3f}g</td>
                </tr>
                <tr style="border-top: 1px solid #ddd; font-style: italic; font-size: 0.9em;">
                    <td style="padding: 4px;" colspan="2">GMPE: Raghukanth & Iyengar (2007)</td>
                </tr>
            </table>
        </div>
        """
        folium.CircleMarker(
            location=coords,
            radius=8,
            color="black",
            fill=True,
            fill_color="#F39C12",
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{city} Hazard Info"
        ).add_to(m)

    # Add PGA HeatMap or circular overlay representing the spatial hazard grid
    # Filter grid to show PGA > 0.05g to keep map clean
    heat_data = []
    for _, row in df_grid.iterrows():
        # folium HeatMap takes [lat, lon, weight]
        heat_data.append([row["latitude"], row["longitude"], row["pga_475_overall"]])
        
    HeatMap(
        heat_data,
        radius=15,
        blur=20,
        gradient={0.1: "blue", 0.3: "lime", 0.5: "orange", 0.8: "red"},
        min_opacity=0.2,
        name="Seismic Hazard Heatmap (PGA 475yr)"
    ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save(OUT_DIR / "kutch_hazard_interactive.html")
    print("Saved: outputs/kutch_hazard_interactive.html")
    
    print("\n=== PSHA Pipeline Run Complete ===")

if __name__ == "__main__":
    main()
