"""
risk_dashboard.py
-----------------
Trikaal — Interactive Seismic Risk Dashboard Generator

Reads outputs/risk_score.csv and generates a self-contained HTML dashboard
using Plotly.js (CDN). Opens in any browser, no server required.

Also requires: data/processed/kutch_clean.csv  (for M≥4 event overlay)

Output
------
  outputs/risk_dashboard.html
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import webbrowser
import http.server
import socketserver
import threading
import time

DATA_PATH = Path(__file__).parent.parent / "data" / "processed" / "kutch_clean.csv"
RISK_PATH = Path(__file__).parent.parent / "outputs" / "risk_score.csv"
OUT_PATH  = Path(__file__).parent.parent / "outputs" / "risk_dashboard.html"
OPT_PATH  = Path(__file__).parent.parent / "outputs" / "optimal_weights.json"

# Load dynamic optimal weights if available
w_b, w_r, w_c = 0.40, 0.35, 0.25
if OPT_PATH.exists():
    try:
        with open(OPT_PATH, "r") as f:
            opt = json.load(f)
            w_b = opt["w_b"]
            w_r = opt["w_rate"]
            w_c = opt["w_cluster"]
    except Exception:
        pass


# ── Data helpers ───────────────────────────────────────────────────────────
def _safe(v):
    """Convert numpy/pandas scalars to JSON-serialisable Python types."""
    if isinstance(v, float) and np.isnan(v): return None
    if isinstance(v, (np.integer,)):          return int(v)
    if isinstance(v, (np.floating,)):         return float(v)
    if isinstance(v, pd.Timestamp):           return v.isoformat()
    return v


def load_and_package():
    risk = pd.read_csv(RISK_PATH, parse_dates=["period_start", "period_end"])
    df   = pd.read_csv(DATA_PATH)
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc", "magnitude"])

    t_mid = risk["period_start"] + (risk["period_end"] - risk["period_start"]) / 2

    color_map = {"HIGH": "#e74c3c", "MEDIUM": "#f39c12",
                 "LOW": "#2ecc71", "UNKNOWN": "#64748b"}

    labels = risk["risk_label"].fillna("UNKNOWN").tolist()

    risk_data = {
        "x"      : [str(t)[:10] for t in t_mid],
        "y"      : [_safe(v) for v in risk["risk_score"].values],
        "labels" : labels,
        "colors" : [color_map[l] for l in labels],
        "b_sig"  : [_safe(v) for v in risk["b_signal"].values],
        "r_sig"  : [_safe(v) for v in risk["rate_signal"].values],
        "c_sig"  : [_safe(v) for v in risk["cluster_signal"].values],
        "q33"    : float(risk["q33"].dropna().iloc[0]),
        "q66"    : float(risk["q66"].dropna().iloc[0]),
    }

    large = df[df["magnitude"] >= 4.0]
    events_data = {
        "x"   : [str(t)[:10] for t in large["time_utc"]],
        "mag" : [round(float(m), 1) for m in large["magnitude"]],
    }

    # Last valid bin for status badge
    last_label, last_score = "UNKNOWN", None
    for i in range(len(risk_data["y"]) - 1, -1, -1):
        if risk_data["y"][i] is not None:
            last_label = risk_data["labels"][i]
            last_score = risk_data["y"][i]
            break

    return risk_data, events_data, last_label, last_score


# ── HTML generator ─────────────────────────────────────────────────────────
def generate_html(risk_data, events_data, last_label, last_score) -> str:
    rj = json.dumps(risk_data)
    ej = json.dumps(events_data)
    sc = f"{last_score:.3f}" if last_score is not None else "N/A"
    status_colors = {"HIGH": "#e74c3c", "MEDIUM": "#f39c12",
                     "LOW": "#2ecc71", "UNKNOWN": "#64748b"}
    scol = status_colors.get(last_label, "#64748b")
    q33s = f"{risk_data['q33']:.3f}"
    q66s = f"{risk_data['q66']:.3f}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Trikaal — Kutch Seismic Risk Dashboard</title>
<meta name="description" content="Seismic intelligence dashboard for Kutch, Gujarat. Composite risk scoring using b-value, event rate, and spatial clustering."/>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg0:#070b14;--bg1:#0f1623;--bg2:#151e2d;--bg3:#1a2540;
  --border:rgba(255,255,255,0.07);
  --txt:#e2e8f0;--mute:#6b7a99;
  --blue:#3b82f6;--purple:#8b5cf6;--teal:#14b8a6;
  --low:#2ecc71;--med:#f39c12;--high:#e74c3c;
}}
html{{scroll-behavior:smooth}}
body{{font-family:'Inter',sans-serif;background:var(--bg0);color:var(--txt);min-height:100vh;overflow-x:hidden}}

/* NAV */
nav{{
  position:sticky;top:0;z-index:200;
  background:linear-gradient(135deg,#0b1120 0%,#1a1640 50%,#0b1120 100%);
  border-bottom:1px solid var(--border);
  padding:16px 40px;
  display:flex;align-items:center;justify-content:space-between;
  backdrop-filter:blur(12px);
}}
.brand{{display:flex;align-items:center;gap:14px}}
.brand-icon{{
  width:42px;height:42px;border-radius:12px;
  background:linear-gradient(135deg,#3b82f6,#8b5cf6);
  display:flex;align-items:center;justify-content:center;font-size:18px;
  box-shadow:0 4px 20px rgba(59,130,246,0.4);
}}
.brand-name{{
  font-size:20px;font-weight:800;letter-spacing:-0.5px;
  background:linear-gradient(90deg,#3b82f6,#8b5cf6,#14b8a6);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}}
.brand-sub{{font-size:10px;color:var(--mute);letter-spacing:2px;text-transform:uppercase;margin-top:2px}}

.status-badge{{
  display:flex;align-items:center;gap:12px;
  background:var(--bg2);border:1px solid var(--border);
  padding:10px 22px;border-radius:50px;
}}
.dot{{
  width:10px;height:10px;border-radius:50%;
  background:{scol};box-shadow:0 0 14px {scol};
  animation:pulse 2s ease-in-out infinite;
}}
@keyframes pulse{{0%,100%{{transform:scale(1);opacity:1}}50%{{transform:scale(1.5);opacity:.6}}}}
.status-lbl{{font-size:9px;color:var(--mute);letter-spacing:1.5px;text-transform:uppercase}}
.status-val{{font-size:15px;font-weight:700;color:{scol}}}

/* LAYOUT */
.wrap{{max-width:1380px;margin:0 auto;padding:32px 40px}}

/* KPI ROW */
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:28px}}
.kpi{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:22px 24px;position:relative;overflow:hidden;
  transition:transform .2s,border-color .2s;
}}
.kpi:hover{{transform:translateY(-4px);border-color:rgba(59,130,246,.3)}}
.kpi::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent,#3b82f6);border-radius:16px 16px 0 0}}
.kpi-lbl{{font-size:10px;text-transform:uppercase;letter-spacing:1.2px;color:var(--mute);margin-bottom:8px}}
.kpi-val{{font-size:30px;font-weight:800;font-family:'JetBrains Mono',monospace;color:var(--accent,#3b82f6)}}
.kpi-sub{{font-size:11px;color:var(--mute);margin-top:5px}}

/* CHART CARDS */
.card{{
  background:var(--bg1);border:1px solid var(--border);border-radius:20px;
  padding:26px;margin-bottom:24px;
  transition:border-color .25s;
}}
.card:hover{{border-color:rgba(59,130,246,.2)}}
.card-head{{display:flex;align-items:flex-start;gap:12px;margin-bottom:6px}}
.card-icon{{
  width:34px;height:34px;border-radius:9px;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;font-size:15px;
}}
.card-title{{font-size:14px;font-weight:600}}
.card-sub{{font-size:11px;color:var(--mute);margin-bottom:16px;padding-left:46px}}

/* PILLS */
.pill-row{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
.pill{{font-size:10px;padding:4px 12px;border-radius:20px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.pill-low{{background:rgba(46,204,113,.12);color:var(--low);border:1px solid rgba(46,204,113,.3)}}
.pill-med{{background:rgba(243,156,18,.12);color:var(--med);border:1px solid rgba(243,156,18,.3)}}
.pill-high{{background:rgba(231,76,60,.12);color:var(--high);border:1px solid rgba(231,76,60,.3)}}

.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}}

/* INFO GRID */
.info-tbl{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}}
.info-row{{
  display:flex;justify-content:space-between;align-items:center;
  padding:9px 14px;background:var(--bg2);border-radius:9px;font-size:11px;
}}
.info-k{{color:var(--mute)}}
.info-v{{font-weight:600;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--txt)}}

footer{{text-align:center;padding:28px;color:var(--mute);font-size:11px;border-top:1px solid var(--border)}}

@media(max-width:900px){{
  .grid2{{grid-template-columns:1fr}}
  .wrap{{padding:16px}}
  nav{{padding:14px 16px;flex-direction:column;gap:10px}}
}}
</style>
</head>
<body>

<nav>
  <div class="brand">
    <div class="brand-icon">⚡</div>
    <div>
      <div class="brand-name">TRIKAAL</div>
      <div class="brand-sub">Kutch · Seismic Intelligence Engine</div>
    </div>
  </div>
  <div class="status-badge">
    <div class="dot"></div>
    <div>
      <div class="status-lbl">Current Risk Status</div>
      <div class="status-val">{last_label} &nbsp;·&nbsp; {sc}</div>
    </div>
  </div>
</nav>

<main class="wrap">
  <div class="kpi-row" id="kpis"></div>

  <!-- MAIN RISK CHART -->
  <div class="card">
    <div class="card-head">
      <div class="card-icon" style="background:rgba(231,76,60,.15)">🌋</div>
      <div class="card-title">Composite Seismic Risk Timeline</div>
    </div>
    <div class="card-sub">Risk(t) = 0.40·S_b + 0.35·S_rate + 0.25·S_cluster &nbsp;|&nbsp; 14-day bins &nbsp;|&nbsp; M≥3.0 &nbsp;|&nbsp; Quantile classification</div>
    <div class="pill-row">
      <span class="pill pill-low">🟢 LOW &lt; Q33 = {q33s}</span>
      <span class="pill pill-med">🟡 MEDIUM</span>
      <span class="pill pill-high">🔴 HIGH ≥ Q66 = {q66s}</span>
    </div>
    <div id="chart-risk" style="height:400px"></div>
  </div>

  <!-- COMPONENTS & EVENTS -->
  <div class="grid2">
    <div class="card">
      <div class="card-head">
        <div class="card-icon" style="background:rgba(139,92,246,.15)">🔬</div>
        <div class="card-title">Signal Components</div>
      </div>
      <div class="card-sub">Normalized signals feeding the composite score</div>
      <div id="chart-comp" style="height:320px"></div>
    </div>
    <div class="card">
      <div class="card-head">
        <div class="card-icon" style="background:rgba(20,184,166,.15)">📍</div>
        <div class="card-title">M≥4 Seismic Events</div>
      </div>
      <div class="card-sub">Actual event magnitudes for risk validation overlay</div>
      <div id="chart-events" style="height:320px"></div>
    </div>
  </div>

  <!-- HISTOGRAM -->
  <div class="card">
    <div class="card-head">
      <div class="card-icon" style="background:rgba(59,130,246,.15)">📊</div>
      <div class="card-title">Risk Score Distribution</div>
    </div>
    <div class="card-sub">Histogram of all valid risk scores — dashed lines mark Q33/Q66 boundaries</div>
    <div id="chart-hist" style="height:240px"></div>
  </div>

  <!-- MODEL INFO -->
  <div class="card">
    <div class="card-head">
      <div class="card-icon" style="background:rgba(20,184,166,.15)">🧬</div>
      <div class="card-title">Model Parameters</div>
    </div>
    <div class="card-sub">Risk engine configuration and signal definitions</div>
    <div class="info-tbl" id="info-tbl"></div>
  </div>
</main>

<footer>
  Trikaal Seismic Intelligence Engine &nbsp;·&nbsp; Kutch, Gujarat, India &nbsp;·&nbsp;
  Data: USGS + ISC &nbsp;·&nbsp; Model: heuristic composite (b-value · event rate · NND clustering)
</footer>

<script>
const RISK   = {rj};
const EVENTS = {ej};
const BHUJ   = "2001-01-26";

const BASE = {{
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{{color:'#6b7a99',family:'Inter,sans-serif',size:11}},
  margin:{{t:16,r:20,b:40,l:52}},
  xaxis:{{gridcolor:'rgba(255,255,255,0.05)',zerolinecolor:'rgba(255,255,255,0.08)'}},
  yaxis:{{gridcolor:'rgba(255,255,255,0.05)',zerolinecolor:'rgba(255,255,255,0.08)'}},
}};
const CFG = {{responsive:true,displayModeBar:false}};

function bhujShape(yref='paper'){{
  return{{type:'line',x0:BHUJ,x1:BHUJ,y0:0,y1:1,yref,xref:'x',
          line:{{color:'#e74c3c',width:2,dash:'dot'}}}};
}}
function bhujAnnot(y=0.96){{
  return{{x:BHUJ,y,xref:'x',yref:'paper',text:'Bhuj Mw7.7',showarrow:false,
          xanchor:'left',font:{{color:'#e74c3c',size:10}}}};
}}

// KPIs
(function(){{
  const valid = RISK.y.filter(v=>v!==null);
  const lc    = l => RISK.labels.filter(x=>x===l).length;
  const data  = [
    {{lbl:'Current Risk',    val:'{last_label}',                              sub:'Score: {sc}',              accent:'{scol}'}},
    {{lbl:'Peak Risk Score', val:Math.max(...valid).toFixed(3),               sub:'All-time maximum',          accent:'#e74c3c'}},
    {{lbl:'Mean Risk Score', val:(valid.reduce((a,b)=>a+b,0)/valid.length).toFixed(3), sub:'Catalog average', accent:'#3b82f6'}},
    {{lbl:'HIGH-risk Bins',  val:lc('HIGH'),                                  sub:`of ${{valid.length}} bins`, accent:'#e74c3c'}},
    {{lbl:'M≥4 Events',      val:EVENTS.x.length,                             sub:'In full catalog',           accent:'#f39c12'}},
  ];
  document.getElementById('kpis').innerHTML = data.map(d=>
    `<div class="kpi" style="--accent:${{d.accent}}">
       <div class="kpi-lbl">${{d.lbl}}</div>
       <div class="kpi-val">${{d.val}}</div>
       <div class="kpi-sub">${{d.sub}}</div>
     </div>`).join('');
}})();

// Chart 1 — Composite risk
(function(){{
  const bar = {{
    x:RISK.x, y:RISK.y, type:'bar', name:'Risk Score',
    marker:{{color:RISK.colors, opacity:0.88}},
    customdata:RISK.labels,
    hovertemplate:'<b>%{{x}}</b><br>Risk: %{{y:.3f}}<br>%{{customdata}}<extra></extra>',
  }};
  const qLine = (q,col,nm)=>(({{
    x:[RISK.x[0],RISK.x[RISK.x.length-1]], y:[q,q],
    type:'scatter',mode:'lines',name:`${{nm}} (${{q.toFixed(3)}})`,
    line:{{color:col,dash:'dash',width:1.5}}, opacity:0.8,
  }}));
  const evts = {{
    x:EVENTS.x, y:EVENTS.mag, type:'scatter', mode:'markers',
    name:'M≥4 events', yaxis:'y2',
    marker:{{size:EVENTS.mag.map(m=>m*3), color:'white', opacity:0.85,
             line:{{color:'#475569',width:1}}}},
    hovertemplate:'<b>%{{x}}</b><br>M%{{y:.1f}}<extra></extra>',
  }};
  Plotly.newPlot('chart-risk',
    [bar, qLine(RISK.q33,'#2ecc71','Q33'), qLine(RISK.q66,'#e74c3c','Q66'), evts],
    {{...BASE, shapes:[bhujShape()], annotations:[bhujAnnot()],
      yaxis:{{...BASE.yaxis, title:'Risk Score', range:[0,1.12]}},
      yaxis2:{{title:'Magnitude', overlaying:'y', side:'right', range:[3.5,9], gridcolor:'transparent'}},
      barmode:'overlay', hovermode:'x unified',
      legend:{{orientation:'h',x:0,y:1.08,font:{{size:10}}}}}}, CFG);
}})();

// Chart 2 — Components
(function(){{
  const traces = [
    {{name:'S_b (Stress)',     y:RISK.b_sig, color:'#8b5cf6'}},
    {{name:'S_rate (Activity)',y:RISK.r_sig, color:'#3b82f6'}},
    {{name:'S_cluster (NND)',  y:RISK.c_sig, color:'#14b8a6'}},
  ].map(t=>(({{
    x:RISK.x, y:t.y, type:'scatter', mode:'lines', name:t.name,
    line:{{color:t.color,width:2}},
    fill:'tozeroy', fillcolor:t.color+'28',
    hovertemplate:`<b>%{{x}}</b><br>${{t.name}}: %{{y:.3f}}<extra></extra>`,
  }})));
  Plotly.newPlot('chart-comp', traces,
    {{...BASE, shapes:[bhujShape()], annotations:[bhujAnnot(0.95)],
      yaxis:{{...BASE.yaxis,title:'Signal [0–1]',range:[-0.05,1.18]}},
      hovermode:'x unified', legend:{{orientation:'h',x:0,y:1.1,font:{{size:10}}}}}}, CFG);
}})();

// Chart 3 — M≥4 events
(function(){{
  Plotly.newPlot('chart-events',[{{
    x:EVENTS.x, y:EVENTS.mag, type:'scatter', mode:'markers', name:'M≥4',
    marker:{{
      size:EVENTS.mag.map(m=>m*4-12), opacity:0.9,
      color:EVENTS.mag,
      colorscale:[[0,'#3b82f6'],[0.4,'#f39c12'],[0.7,'#e74c3c'],[1,'#7f1d1d']],
      showscale:true, colorbar:{{title:'Mag',thickness:12,len:0.8}},
      line:{{color:'rgba(255,255,255,0.25)',width:0.5}},
    }},
    hovertemplate:'<b>%{{x}}</b><br>M%{{y:.1f}}<extra></extra>',
  }}],
  {{...BASE, shapes:[bhujShape()],
    yaxis:{{...BASE.yaxis,title:'Magnitude'}}}}, CFG);
}})();

// Chart 4 — Histogram
(function(){{
  const valid = RISK.y.filter(v=>v!==null);
  Plotly.newPlot('chart-hist',[{{
    x:valid, type:'histogram', nbinsx:35, name:'Risk Score',
    marker:{{color:'#3b82f6',opacity:0.75,line:{{color:'#1d4ed8',width:0.5}}}},
  }}],
  {{...BASE,
    shapes:[
      {{type:'line',x0:RISK.q33,x1:RISK.q33,y0:0,y1:1,yref:'paper',line:{{color:'#2ecc71',dash:'dash',width:2}}}},
      {{type:'line',x0:RISK.q66,x1:RISK.q66,y0:0,y1:1,yref:'paper',line:{{color:'#e74c3c',dash:'dash',width:2}}}},
    ],
    annotations:[
      {{x:RISK.q33,y:1.04,xref:'x',yref:'paper',text:'Q33',showarrow:false,font:{{color:'#2ecc71',size:10}}}},
      {{x:RISK.q66,y:1.04,xref:'x',yref:'paper',text:'Q66',showarrow:false,font:{{color:'#e74c3c',size:10}}}},
    ],
    xaxis:{{...BASE.xaxis,title:'Risk Score'}},
    yaxis:{{...BASE.yaxis,title:'Bin Count'}},
    bargap:0.04}}, CFG);
}})();

// Model info table
(function(){{
  const rows = [
    ['Mc (completeness)','3.0'],
    ['Time bin','14 days'],
    ['b-value window','±45 day centered'],
    ['b algorithm','Aki 1965 MLE + Shi & Bolt σ'],
    ['b_ref / b_min','1.0 / 0.5'],
    ['S_b formula','clip((b_ref−b_t)/(b_ref−b_min),0,1)'],
    ['S_rate formula','sigmoid((rate−μ)/σ)'],
    ['S_cluster formula','1 − normalize(mean NND km)'],
    ['Weights','{w_b:.2f}·S_b + {w_r:.2f}·S_rate + {w_c:.2f}·S_cluster (Data-Driven Optimized)'],
    ['Classification','Quantile Q33 / Q66 (adaptive)'],
    ['Min events for b','15 per 90-day window'],
    ['Data sources','USGS + ISC merged catalog'],
  ];
  document.getElementById('info-tbl').innerHTML =
    rows.map(([k,v])=>
      `<div class="info-row"><span class="info-k">${{k}}</span><span class="info-v">${{v}}</span></div>`
    ).join('');
}})();
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────
class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress standard server logs to keep terminal clean

def serve_dashboard(port=8000):
    handler = DashboardHandler
    import os
    # Serve from the repository root
    os.chdir(str(Path(__file__).parent.parent))
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"  Local server started at http://localhost:{port}/outputs/risk_dashboard.html")
            httpd.serve_forever()
    except Exception as e:
        print(f"  Server error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("  TRIKAAL - Risk Dashboard Generator")
    print("=" * 60)

    if not RISK_PATH.exists():
        print("ERROR: risk_score.csv not found. Run risk_score.py first.")
        raise SystemExit(1)

    risk_data, events_data, last_label, last_score = load_and_package()
    html = generate_html(risk_data, events_data, last_label, last_score)
    OUT_PATH.write_text(html, encoding="utf-8")

    print(f"  Saved --> {OUT_PATH}")

    # Launch server in a daemon thread
    port = 8000
    t = threading.Thread(target=serve_dashboard, args=(port,), daemon=True)
    t.start()
    
    # Wait a moment for server to initialize
    time.sleep(0.5)
    
    url = f"http://localhost:{port}/outputs/risk_dashboard.html"
    print(f"  Launching browser to: {url} ...")
    webbrowser.open(url)
    
    print("\n[SUCCESS] Dashboard ready. Press Ctrl+C in this terminal to stop the server.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server.")
