"""
psha.py
-------
Trikaal — Probabilistic Seismic Hazard Analysis (PSHA) Engine.
Implements ground motion prediction equations (GMPEs), seismic source geometry models,
and vectorized hazard curve calculation.
"""

import numpy as np
from scipy.stats import norm
from scipy.interpolate import interp1d

# ===========================================================================
# 1. Ground Motion Prediction Equations (GMPEs)
# ===========================================================================

def raghukanth_iyengar_2007(mag: np.ndarray, dist: np.ndarray, site_class: str = "rock") -> tuple[np.ndarray, float]:
    """
    Raghukanth & Iyengar (2007) GMPE for Peninsular India Stable Continental Region.
    Predicts Peak Ground Acceleration (PGA) in units of g.

    Parameters
    ----------
    mag : np.ndarray
        Moment magnitudes, shape (M,)
    dist : np.ndarray
        Hypocentral distances in km, shape (D,)
    site_class : str
        Site condition: 'rock' (Vs30 ~ 760 m/s), 'soil' (Vs30 ~ 300 m/s), 
        'hardrock' (Vs30 ~ 1500 m/s).

    Returns
    -------
    mean_ln_pga : np.ndarray
        Mean of natural log PGA, shape (M, D)
    sigma : float
        Standard deviation in natural log units
    """
    # Grid of M and D (broadcasting)
    M = mag[:, None]
    R = dist[None, :]

    # Bedrock PGA (units of g)
    # ln(y_br) = c1 + c2*(M - 6) + c3*(M - 6)^2 - ln(R) - c4*R
    c1, c2, c3, c4 = 1.6858, 0.9241, -0.0760, 0.0057
    ln_pga_br = c1 + c2 * (M - 6.0) + c3 * (M - 6.0) ** 2 - np.log(R) - c4 * R

    # Site amplification factor Fs
    if site_class == "hardrock":
        ln_fs = -0.22
    elif site_class == "soil":
        ln_fs = 0.41
    else:  # 'rock'
        ln_fs = 0.0

    mean_ln_pga = ln_pga_br + ln_fs
    sigma = 0.4648

    return mean_ln_pga, sigma


def atkinson_boore_2006(mag: np.ndarray, dist: np.ndarray, site_class: str = "rock") -> tuple[np.ndarray, float]:
    """
    Atkinson & Boore (2006) GMPE for Eastern North America (ENA) Stable Continental Region.
    Simplified PGA implementation on hard rock (Vs30 = 2000 m/s) and NEHRP BC boundary (Vs30 = 760 m/s).
    Predicts Peak Ground Acceleration (PGA) in units of g.
    """
    M = mag[:, None]
    R = dist[None, :]

    # Effective distance term to prevent singularity at zero distance
    R_eff = np.sqrt(R**2 + 4.5**2)

    # Simplified representative polynomial fit for PGA on stable continental crust
    # log10(PGA) = c1 + c2*M + c3*M^2 + (c4 + c5*M)*log10(R_eff) + c6*R_eff
    c1, c2, c3, c4, c5, c6 = -0.65, 0.25, 0.010, -1.25, 0.045, -0.0015
    log10_pga_br = c1 + c2 * M + c3 * M**2 + (c4 + c5 * M) * np.log10(R_eff) + c6 * R_eff

    # Convert to natural log
    ln_pga_br = log10_pga_br * np.log(10.0)

    # Site correction relative to NEHRP BC (Vs30 ~ 760 m/s)
    if site_class == "hardrock":
        ln_fs = -0.3
    elif site_class == "soil":
        ln_fs = 0.35
    else:
        ln_fs = 0.0

    mean_ln_pga = ln_pga_br + ln_fs
    sigma = 0.55  # typical ENA sigma in ln units

    return mean_ln_pga, sigma


def boore_et_al_2014(mag: np.ndarray, dist: np.ndarray, site_class: str = "rock") -> tuple[np.ndarray, float]:
    """
    Boore et al. (2014) NGA-West2 GMPE for Active Shallow Crustal Regions.
    Predicts Peak Ground Acceleration (PGA) in units of g.
    Used as an active tectonic boundary reference for comparison.
    """
    M = mag[:, None]
    R = dist[None, :]

    # Joyner-Boore distance equivalent R_eff
    R_eff = np.sqrt(R**2 + 7.3**2)

    # ln(PGA) = e0 + e1*(M - 6) + e2*(M - 6)^2 + e3*ln(R_eff) + e4*R_eff
    # Active tectonic regions exhibit higher attenuation (faster decay) than stable cratons
    e0, e1, e2, e3, e4 = -0.15, 0.90, -0.08, -1.15, -0.003
    ln_pga_br = e0 + e1 * (M - 6.0) + e2 * (M - 6.0) ** 2 + e3 * np.log(R_eff) + e4 * R_eff

    if site_class == "hardrock":
        ln_fs = -0.25
    elif site_class == "soil":
        ln_fs = 0.45
    else:
        ln_fs = 0.0

    mean_ln_pga = ln_pga_br + ln_fs
    sigma = 0.48

    return mean_ln_pga, sigma


# ===========================================================================
# 2. Source Geometry & Discretization Models
# ===========================================================================

class AreaSource:
    """Area seismic source zone. Discretizes a polygon into a grid of point sources."""

    def __init__(self, name: str, min_lat: float, max_lat: float, min_lon: float, max_lon: float, 
                 depth: float = 15.0):
        self.name = name
        self.min_lat = min_lat
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.max_lon = max_lon
        self.depth = depth

    def discretize(self, resolution: float = 0.1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Discretizes the area into a set of points.

        Returns
        -------
        lats : np.ndarray
            Latitudes of points
        lons : np.ndarray
            Longitudes of points
        weights : np.ndarray
            Area weight of each point (sums to 1.0)
        """
        lat_grid = np.arange(self.min_lat + resolution/2, self.max_lat, resolution)
        lon_grid = np.arange(self.min_lon + resolution/2, self.max_lon, resolution)
        
        lats, lons = np.meshgrid(lat_grid, lon_grid)
        lats = lats.flatten()
        lons = lons.flatten()
        
        weights = np.ones_like(lats) / len(lats)
        return lats, lons, weights


class LineSource:
    """Line/Fault seismic source zone. Discretizes a line segment into point sources."""

    def __init__(self, name: str, start_lat: float, start_lon: float, end_lat: float, end_lon: float, 
                 depth: float = 15.0):
        self.name = name
        self.start_lat = start_lat
        self.start_lon = start_lon
        self.end_lat = end_lat
        self.end_lon = end_lon
        self.depth = depth

    def discretize(self, num_points: int = 10) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Discretizes the line into points.

        Returns
        -------
        lats : np.ndarray
            Latitudes of points
        lons : np.ndarray
            Longitudes of points
        weights : np.ndarray
            Weight of each point (sums to 1.0)
        """
        lats = np.linspace(self.start_lat, self.end_lat, num_points)
        lons = np.linspace(self.start_lon, self.end_lon, num_points)
        weights = np.ones_like(lats) / len(lats)
        return lats, lons, weights


# ===========================================================================
# 3. Hazard Curve Calculation Engine
# ===========================================================================

def haversine_distance(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Computes great-circle distance between two sets of coordinates in km."""
    R = 6371.0  # Earth's radius in km
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat / 2.0) ** 2 + 
         np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2)
    c = 2.0 * np.arcsin(np.sqrt(a))
    return R * c


class PSHAEngine:
    """Engine to perform Probabilistic Seismic Hazard Analysis."""

    def __init__(self, sources: list, gmpe_func=raghukanth_iyengar_2007, resolution: float = 0.15):
        self.sources = sources
        self.gmpe_func = gmpe_func
        self.resolution = resolution
        
        # Discretize all sources once during initialization
        all_lats, all_lons, all_weights, all_depths = [], [], [], []
        
        for source in self.sources:
            if isinstance(source, AreaSource):
                lats, lons, w = source.discretize(resolution=self.resolution)
                d = np.full_like(lats, source.depth)
            elif isinstance(source, LineSource):
                lats, lons, w = source.discretize(num_points=10)
                d = np.full_like(lats, source.depth)
            else:
                continue
            
            all_lats.extend(lats)
            all_lons.extend(lons)
            all_weights.extend(w / len(self.sources))  # split total rate equally among sources
            all_depths.extend(d)

        self.source_lats = np.array(all_lats, dtype=np.float64)
        self.source_lons = np.array(all_lons, dtype=np.float64)
        self.source_weights = np.array(all_weights, dtype=np.float64)
        self.source_depths = np.array(all_depths, dtype=np.float64)

    def compute_hazard_curve(self, 
                             site_lat: float, 
                             site_lon: float, 
                             pga_levels: np.ndarray,
                             annual_rate: float,
                             b_value: float,
                             Mc: float = 3.0,
                             Mmax: float = 7.7,
                             site_class: str = "rock") -> np.ndarray:
        """
        Computes the annual rate of exceedance lambda(PGA > x) at a site in a fully vectorized way.

        Parameters
        ----------
        site_lat, site_lon : float
            Site coordinates
        pga_levels : np.ndarray
            PGA acceleration levels to evaluate (in g)
        annual_rate : float
            Annual rate of earthquakes with M >= Mc in Kutch (N0)
        b_value : float
            Gutenberg-Richter b-value
        Mc : float
            Completeness magnitude (minimum magnitude in integration)
        Mmax : float
            Maximum magnitude
        site_class : str
            Site class for GMPE

        Returns
        -------
        annual_exceedance_rates : np.ndarray
            Annual rate of exceedance for each PGA level, shape (len(pga_levels),)
        """
        # 1. Magnitude distribution PDF
        mags = np.arange(Mc, Mmax + 0.05, 0.1)
        pdf_raw = 10.0 ** (-b_value * (mags - Mc))
        m_weights = pdf_raw / np.sum(pdf_raw)  # Normalized magnitude probabilities

        # 2. Compute hypocentral distances from site to all precalculated point sources
        epi_dists = haversine_distance(site_lat, site_lon, self.source_lats, self.source_lons)
        hypo_dists = np.sqrt(epi_dists**2 + self.source_depths**2)

        # 3. Evaluate GMPE for all magnitude bins and distance bins
        # mean_ln_pga shape (len(mags), len(hypo_dists))
        mean_ln_pga, sigma = self.gmpe_func(mags, hypo_dists, site_class=site_class)

        # 4. Vectorized integration over PGA levels, magnitudes, and distances
        # ln_x shape (len(pga_levels), 1, 1)
        ln_x = np.log(pga_levels)[:, None, None]
        
        # z shape (len(pga_levels), len(mags), len(hypo_dists))
        z = (ln_x - mean_ln_pga[None, :, :]) / sigma
        p_exceed_pga = norm.sf(z)  # Normal survival function (1 - CDF)

        # Integrate over distances (sum over axis 2 using weights)
        # shape: (len(pga_levels), len(mags))
        p_exceed_m = np.sum(p_exceed_pga * self.source_weights[None, None, :], axis=2)

        # Integrate over Gutenberg-Richter magnitude distribution (sum over axis 1)
        # shape: (len(pga_levels),)
        total_p_exceed = np.sum(p_exceed_m * m_weights[None, :], axis=1)

        # Annual rate of exceedance
        return annual_rate * total_p_exceed


# ===========================================================================
# 4. Interpolate PGA for specific Exceedance Probability in 50 years
# ===========================================================================

def interpolate_pga_hazard(pga_levels: np.ndarray, annual_rates: np.ndarray, 
                           target_prob: float = 0.10, exposure_years: float = 50.0) -> float:
    """
    Interpolates the PGA level corresponding to a target probability of exceedance.
    
    Parameters
    ----------
    pga_levels : np.ndarray
        PGA levels evaluated (in g)
    annual_rates : np.ndarray
        Computed annual rate of exceedance for each PGA level
    target_prob : float
        Target probability of exceedance (e.g. 0.10 for 10%, 0.02 for 2%)
    exposure_years : float
        Exposure window in years (default 50)

    Returns
    -------
    pga_val : float
        PGA in units of g
    """
    target_rate = -np.log(1.0 - target_prob) / exposure_years
    
    # Filter out zero rates
    valid = annual_rates > 1e-15
    if np.sum(valid) < 2:
        return 0.0
        
    log_rates = np.log10(annual_rates[valid])
    log_pga = np.log10(pga_levels[valid])
    
    sort_idx = np.argsort(log_rates)
    log_rates = log_rates[sort_idx]
    log_pga = log_pga[sort_idx]
    
    log_target_rate = np.log10(target_rate)
    
    try:
        f = interp1d(log_rates, log_pga, bounds_error=False, fill_value="extrapolate")
        pga_val = 10.0 ** float(f(log_target_rate))
    except Exception:
        pga_val = 0.0
        
    return pga_val
