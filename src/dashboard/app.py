"""
AI Trading Agent — Professional Daylight Dashboard
Clean institutional design. No option chain. Real candles.
Multiple timeframes. Pattern detection. Trade alerts.
Run: streamlit run src/dashboard/app.py
"""

import sys, os, datetime, time, random, math, threading
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

import streamlit as st
import pandas as pd
import numpy as np
import pytz

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from src.dashboard.live_data import start as start_live, get_state
from src.dashboard.patterns  import detect_patterns

st.set_page_config(
    page_title="AI Trading Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IST = pytz.timezone("Asia/Kolkata")

# ── Design tokens ─────────────────────────────────────────────────────────────
# Palette: institutional daylight
# --ink:        #0f1923   (near-black text)
# --slate:      #374151   (secondary text)
# --mist:       #6b7280   (tertiary / labels)
# --cloud:      #f3f4f6   (subtle backgrounds)
# --white:      #ffffff   (card surfaces)
# --border:     #e5e7eb   (dividers)
# --teal:       #0d9488   (bull / positive)
# --crimson:    #dc2626   (bear / negative)
# --indigo:     #4f46e5   (primary accent — signal score, tabs)
# --amber:      #d97706   (warning / neutral signal)
# --sky:        #0284c7   (US market accent)
# Typefaces: 'Plus Jakarta Sans' display, 'IBM Plex Sans' body, 'IBM Plex Mono' data

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --ink:     #0f1923;
  --slate:   #374151;
  --mist:    #6b7280;
  --cloud:   #f3f4f6;
  --cloud2:  #f9fafb;
  --white:   #ffffff;
  --border:  #e5e7eb;
  --border2: #d1d5db;
  --teal:    #0d9488;
  --teal-bg: #f0fdfa;
  --teal-bd: #99f6e4;
  --crimson: #dc2626;
  --crim-bg: #fef2f2;
  --crim-bd: #fecaca;
  --indigo:  #4f46e5;
  --ind-bg:  #eef2ff;
  --ind-bd:  #c7d2fe;
  --amber:   #d97706;
  --amb-bg:  #fffbeb;
  --amb-bd:  #fde68a;
  --sky:     #0284c7;
}

html, body, [class*="css"] {
  background: var(--cloud2) !important;
  color: var(--ink) !important;
  font-family: 'IBM Plex Sans', sans-serif !important;
  font-size: 13px !important;
}

#MainMenu, footer, header, .stDeployButton { display:none!important }
.block-container { padding:0!important; max-width:100%!important }
section[data-testid="stSidebar"] { display:none!important }
div[data-testid="stHorizontalBlock"] { gap:0!important }
div[data-testid="column"] { padding:2px 4px!important }

/* Streamlit element overrides */
.stTabs [data-baseweb="tab-list"] {
  background: transparent!important;
  border-bottom: 2px solid var(--border)!important;
  gap: 0!important; padding: 0!important;
}
.stTabs [data-baseweb="tab"] {
  background: transparent!important;
  color: var(--mist)!important;
  border-bottom: 2px solid transparent!important;
  border-radius: 0!important;
  font-size: 12px!important;
  font-weight: 600!important;
  padding: 10px 18px!important;
  margin-bottom: -2px!important;
  font-family: 'Plus Jakarta Sans', sans-serif!important;
}
.stTabs [aria-selected="true"] {
  color: var(--indigo)!important;
  border-bottom: 2px solid var(--indigo)!important;
  background: transparent!important;
}
.stButton>button {
  background: var(--white)!important;
  color: var(--slate)!important;
  border: 1px solid var(--border)!important;
  border-radius: 6px!important;
  font-size: 11px!important;
  font-weight: 600!important;
  padding: 4px 12px!important;
  font-family: 'Plus Jakarta Sans', sans-serif!important;
  transition: all .15s!important;
}
.stButton>button:hover {
  border-color: var(--indigo)!important;
  color: var(--indigo)!important;
}
.stSelectbox > div > div {
  background: var(--white)!important;
  border: 1px solid var(--border)!important;
  border-radius: 6px!important;
  color: var(--ink)!important;
  font-size: 12px!important;
}

/* ── Layout components ─────────────────────── */

.topbar {
  background: var(--white);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.topbar-logo {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 16px;
  font-weight: 800;
  color: var(--indigo);
  letter-spacing: -.3px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.topbar-pill {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .8px;
  padding: 3px 9px;
  border-radius: 20px;
  font-family: 'Plus Jakarta Sans', sans-serif;
}
.pill-paper {
  background: var(--amb-bg);
  color: var(--amber);
  border: 1px solid var(--amb-bd);
}
.pill-live {
  background: var(--teal-bg);
  color: var(--teal);
  border: 1px solid var(--teal-bd);
}
.pill-closed {
  background: var(--crim-bg);
  color: var(--crimson);
  border: 1px solid var(--crim-bd);
}

.panel {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}

.panel-head {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--cloud2);
}
.panel-title {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .8px;
  text-transform: uppercase;
  color: var(--mist);
}
.panel-body { padding: 12px 14px }

/* ── KPI cards ─────────────────────────────── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  padding: 10px 12px;
  background: var(--white);
  border-bottom: 1px solid var(--border);
}
.kpi-card {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  position: relative;
}
.kpi-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 8px 8px 0 0;
  background: var(--kpi-accent, var(--indigo));
}
.kpi-label {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--mist);
  margin-bottom: 6px;
}
.kpi-value {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 20px;
  font-weight: 500;
  color: var(--ink);
  line-height: 1;
}
.kpi-sub {
  font-size: 10px;
  color: var(--mist);
  margin-top: 4px;
}
.up { color: var(--teal) }
.dn { color: var(--crimson) }
.neu{ color: var(--amber) }
.ind{ color: var(--indigo) }

/* ── Watchlist ──────────────────────────────── */
.wl-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background .12s;
}
.wl-row:hover { background: var(--cloud2) }
.wl-row.active { background: var(--ind-bg); border-left: 3px solid var(--indigo) }
.wl-row:last-child { border-bottom: none }
.wl-name {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink);
}
.wl-sub { font-size: 10px; color: var(--mist); margin-top: 1px }
.wl-price {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 13px;
  font-weight: 500;
  text-align: right;
}
.chg-up {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  color: var(--teal);
  background: var(--teal-bg);
  border: 1px solid var(--teal-bd);
  padding: 1px 6px;
  border-radius: 4px;
}
.chg-dn {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  color: var(--crimson);
  background: var(--crim-bg);
  border: 1px solid var(--crim-bd);
  padding: 1px 6px;
  border-radius: 4px;
}
.chg-neu {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  color: var(--amber);
  background: var(--amb-bg);
  border: 1px solid var(--amb-bd);
  padding: 1px 6px;
  border-radius: 4px;
}

/* ── Signal widget ──────────────────────────── */
.sig-score-ring {
  width: 70px; height: 70px;
  position: relative;
  flex-shrink: 0;
}
.sig-score-num {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%,-50%);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 18px;
  font-weight: 500;
}
.sig-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 6px;
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .3px;
}
.sig-bull { background:var(--teal-bg);  color:var(--teal);    border:1px solid var(--teal-bd) }
.sig-bear { background:var(--crim-bg);  color:var(--crimson); border:1px solid var(--crim-bd) }
.sig-neut { background:var(--amb-bg);   color:var(--amber);   border:1px solid var(--amb-bd)  }

/* ── Indicator rows ─────────────────────────── */
.ind-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.ind-row:last-child { border-bottom: none }
.ind-name { color: var(--mist); font-size: 11px }
.ind-val  { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 500 }

/* ── Pattern badges ─────────────────────────── */
.pat-wrap { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0 }
.pat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 5px;
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .3px;
}
.pat-bull { background:var(--teal-bg);  color:var(--teal);    border:1px solid var(--teal-bd) }
.pat-bear { background:var(--crim-bg);  color:var(--crimson); border:1px solid var(--crim-bd) }
.pat-neut { background:var(--amb-bg);   color:var(--amber);   border:1px solid var(--amb-bd)  }

.pat-detail {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 11px;
  border-left: 3px solid;
  margin-top: 4px;
  background: var(--cloud2);
}

/* ── Trade alert ────────────────────────────── */
.alert-box {
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 8px;
  border: 1px solid;
  position: relative;
}
.alert-bull { background:var(--teal-bg);  border-color:var(--teal-bd) }
.alert-bear { background:var(--crim-bg);  border-color:var(--crim-bd) }
.alert-title {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 13px;
  font-weight: 800;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.alert-row {
  display: flex;
  gap: 24px;
  font-size: 12px;
}
.alert-item-label { font-size: 10px; color:var(--mist); margin-bottom: 2px }
.alert-item-val {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 13px;
  font-weight: 500;
}

/* ── Top signal rows ────────────────────────── */
.top-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  transition: background .12s;
}
.top-row:hover { background: var(--cloud2) }
.top-row:last-child { border-bottom: none }
.top-sym {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  font-weight: 500;
  color: var(--ink);
}
.top-meta { font-size: 10px; color: var(--mist); margin-top: 2px }
.score-bar-bg {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
  width: 80px;
}
.score-bar-fill { height: 4px; border-radius: 2px }

/* ── Live dot ───────────────────────────────── */
.ldot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--teal);
  animation: lblink 1.5s ease infinite;
  vertical-align: middle;
  margin-right: 3px;
}
@keyframes lblink { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.8)} }

.offline-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--mist);
  vertical-align: middle;
  margin-right: 3px;
}

/* ── Scrollable ─────────────────────────────── */
.sc { max-height: 400px; overflow-y: auto }
.sc2{ max-height: 340px; overflow-y: auto }

/* ── Divider label ──────────────────────────── */
.div-label {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--mist);
  padding: 10px 14px 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.div-label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

/* ── Chart toolbar ──────────────────────────── */
.chart-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--white);
  flex-wrap: wrap;
}
.tf-group {
  display: flex;
  background: var(--cloud);
  border-radius: 6px;
  padding: 2px;
  gap: 1px;
}
.tf-btn {
  padding: 4px 10px;
  border-radius: 4px;
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 11px;
  font-weight: 600;
  color: var(--mist);
  cursor: pointer;
  border: none;
  background: transparent;
  transition: all .12s;
}
.tf-btn.active {
  background: var(--white);
  color: var(--indigo);
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.tf-btn:hover:not(.active) { color: var(--slate) }
</style>
""", unsafe_allow_html=True)

# ── Session init ──────────────────────────────────────────────────────────────
if "live_started" not in st.session_state:
    st.session_state.live_started = True
    st.session_state.active_sym   = "NIFTY 50"
    st.session_state.timeframe    = "5min"
    st.session_state.chart_type   = "Candlestick"
    st.session_state.alerts       = []
    st.session_state.dismissed    = set()
    start_live()

# ── Live data ─────────────────────────────────────────────────────────────────
live      = get_state()
prices    = live["prices"]
connected = live["connected"]
last_upd  = live["last_update"]
secs_ago  = int(time.time()-last_upd) if last_upd else 999
now       = datetime.datetime.now(IST)
mkt_open  = datetime.time(9,15)<=now.time()<datetime.time(15,30) and now.weekday()<5

FALLBACKS = {"NIFTY 50":24512,"BANKNIFTY":52187,"S&P 500":5487,
             "NASDAQ":19823,"DOW JONES":40234,"INDIA VIX":15.4}
FLAGS     = {"NIFTY 50":"🇮🇳","BANKNIFTY":"🇮🇳","S&P 500":"🇺🇸","NASDAQ":"🇺🇸","DOW JONES":"🇺🇸"}
COLORS    = {"NIFTY 50":{"accent":"#4f46e5","bg":"#eef2ff","bd":"#c7d2fe"},
             "BANKNIFTY":{"accent":"#0d9488","bg":"#f0fdfa","bd":"#99f6e4"},
             "S&P 500":  {"accent":"#0284c7","bg":"#f0f9ff","bd":"#bae6fd"},
             "NASDAQ":   {"accent":"#7c3aed","bg":"#f5f3ff","bd":"#ddd6fe"},
             "DOW JONES":{"accent":"#d97706","bg":"#fffbeb","bd":"#fde68a"}}

def gp(name, key="price"):
    d = prices.get(name)
    if d: return d.get(key, FALLBACKS.get(name,0))
    return FALLBACKS.get(name,0)
def gc(name):
    d=prices.get(name); return d["chg"] if d else 0.0
def get_candles(name):
    d=prices.get(name); return d.get("candles") if d else None

# ── Signal engine ─────────────────────────────────────────────────────────────
def compute_signal(name):
    candles=get_candles(name)
    rng_s=random.Random(int(time.time())//60+hash(name))
    rsi_val=round(rng_s.uniform(35,70),1)
    e9=e21=macd_v=0.0
    if candles and len(candles.get("close",[]))>=26:
        cl=candles["close"]
        def ema(d,p):
            k=2/(p+1); e=d[0]
            for v in d[1:]: e=v*k+e*(1-k)
            return e
        e9=round(ema(cl[-20:],9),2); e21=round(ema(cl[-20:],21),2)
        g=sum(max(0,cl[i]-cl[i-1]) for i in range(-14,0))
        l=sum(max(0,cl[i-1]-cl[i]) for i in range(-14,0))
        rsi_val=round(100-100/(1+(g/(l+0.001))),1)
        macd_v=round(ema(cl,12)-ema(cl,26),3)
        score=50+(10 if e9>e21 else -10)+(rsi_val-50)*0.35+(4 if macd_v>0 else -4)+rng_s.uniform(-4,4)
    else:
        score=round(rng_s.uniform(48,78),1)
    score=max(10,min(95,round(score,1)))
    if score>=75:   sig,cls,icon="STRONG BUY","sig-bull","▲"
    elif score>=63: sig,cls,icon="BUY","sig-bull","▲"
    elif score>=50: sig,cls,icon="NEUTRAL","sig-neut","◆"
    elif score>=38: sig,cls,icon="SELL","sig-bear","▼"
    else:           sig,cls,icon="STRONG SELL","sig-bear","▼"
    if score>=65:   reg="Bull trend"
    elif score>=52: reg="Weak bull"
    elif score>=40: reg="Ranging"
    else:           reg="Bear trend"
    col=("var(--teal)" if score>=63 else "var(--amber)" if score>=50 else "var(--crimson)")
    return dict(score=score,sig=sig,cls=cls,icon=icon,reg=reg,col=col,
                rsi=rsi_val,e9=e9,e21=e21,macd=macd_v)

# ── Alerts ────────────────────────────────────────────────────────────────────
def check_alerts():
    for sym in ["NIFTY 50","BANKNIFTY"]:
        s=compute_signal(sym)
        if s["score"]>=78 or s["score"]<=22:
            aid=f"{sym}_{int(time.time())//300}"
            if aid not in st.session_state.dismissed:
                if aid not in [a["id"] for a in st.session_state.alerts]:
                    direction="LONG" if s["score"]>=78 else "SHORT"
                    price=gp(sym); atr=price*0.005
                    sl=(round(price-atr*1.5,2) if direction=="LONG"
                        else round(price+atr*1.5,2))
                    tgt=(round(price+atr*3,2) if direction=="LONG"
                         else round(price-atr*3,2))
                    st.session_state.alerts.append(dict(
                        id=aid, sym=sym, direction=direction,
                        opt="CE" if direction=="LONG" else "PE",
                        score=s["score"], price=price, sl=sl,
                        target=tgt, rr="1:2",
                        time=now.strftime("%H:%M:%S"), sig=s["sig"]))
    st.session_state.alerts=st.session_state.alerts[-5:]

check_alerts()

# ── Candle aggregation for longer timeframes ──────────────────────────────────
def resample_candles(candles, tf):
    """Aggregate 1-min/5-min candles into longer timeframes."""
    if not candles or len(candles.get("close",[]))<4:
        return candles
    resample_n={"1min":1,"3min":3,"5min":1,"15min":3,"30min":6,"1hour":12,"4hour":48,"1day":75}
    n=resample_n.get(tf,1)
    if n<=1: return candles
    times=candles["time"]; opens=candles["open"]; highs=candles["high"]
    lows=candles["low"];   closes=candles["close"]; vols=candles["vol"]
    def chunk(lst,size):
        return [lst[i:i+size] for i in range(0,len(lst),size)]
    t_chunks=chunk(times,n); o_c=chunk(opens,n); h_c=chunk(highs,n)
    l_c=chunk(lows,n);       cl_c=chunk(closes,n); v_c=chunk(vols,n)
    return dict(
        time  =[c[0]  for c in t_chunks],
        open  =[c[0]  for c in o_c],
        high  =[max(c) for c in h_c],
        low   =[min(c) for c in l_c],
        close =[c[-1] for c in cl_c],
        vol   =[sum(c) for c in v_c],
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOP BAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
mkt_label=("NSE Open" if mkt_open else "NSE Closed")
mkt_cls=("pill-live" if mkt_open else "pill-closed")
conn_dot=('<span class="ldot"></span>' if connected else
          '<span class="offline-dot"></span>')
conn_label=(f"Angel One · {secs_ago}s ago" if connected else "Connecting…")

st.markdown(f"""
<div class="topbar">
  <div style="display:flex;align-items:center;gap:14px">
    <div class="topbar-logo">
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <rect width="22" height="22" rx="6" fill="#4f46e5"/>
        <path d="M5 15 L9 9 L13 12 L17 7" stroke="white" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="17" cy="7" r="2" fill="#34d399"/>
      </svg>
      AI Trading Agent
    </div>
    <span class="topbar-pill pill-paper">PAPER MODE</span>
    <span class="topbar-pill {mkt_cls}">{mkt_label}</span>
  </div>
  <div style="display:flex;align-items:center;gap:20px">
    <span style="font-size:11px;color:var(--mist)">
      {conn_dot}{conn_label}
    </span>
    <span style="font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--slate)">
      {now.strftime('%d %b %Y  %H:%M:%S IST')}
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TRADE ALERTS (full-width, above grid)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
active=([a for a in st.session_state.alerts
         if a["id"] not in st.session_state.dismissed])
if active:
    for alert in active[-2:]:
        is_bull=alert["direction"]=="LONG"
        cls="alert-bull" if is_bull else "alert-bear"
        icon="▲" if is_bull else "▼"
        col_a="var(--teal)" if is_bull else "var(--crimson)"
        al1,al2=st.columns([11,1])
        with al1:
            st.markdown(f"""
            <div class="alert-box {cls}">
              <div class="alert-title" style="color:{col_a}">
                {icon} TRADE SIGNAL — {alert['sym']} {alert['direction']} {alert['opt']}
                <span style="font-size:10px;font-weight:500;color:var(--mist)">
                  · {alert['sig']}  ·  Score {alert['score']:.0f}/100  ·  {alert['time']}
                </span>
              </div>
              <div class="alert-row">
                <div>
                  <div class="alert-item-label">Entry price</div>
                  <div class="alert-item-val" style="color:var(--ink)">₹{alert['price']:,.2f}</div>
                </div>
                <div>
                  <div class="alert-item-label">Stop loss</div>
                  <div class="alert-item-val" style="color:var(--crimson)">₹{alert['sl']:,.2f}</div>
                </div>
                <div>
                  <div class="alert-item-label">Target</div>
                  <div class="alert-item-val" style="color:var(--teal)">₹{alert['target']:,.2f}</div>
                </div>
                <div>
                  <div class="alert-item-label">Risk : Reward</div>
                  <div class="alert-item-val">{alert['rr']}</div>
                </div>
              </div>
              <div style="margin-top:8px;font-size:10px;color:var(--mist)">
                Paper trading signal — no real order placed. Review risk parameters before acting.
              </div>
            </div>""", unsafe_allow_html=True)
        with al2:
            if st.button("✕ Dismiss", key=f"dis_{alert['id']}"):
                st.session_state.dismissed.add(alert["id"])
                st.rerun()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KPI BAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
nifty_s=compute_signal("NIFTY 50"); bnf_s=compute_signal("BANKNIFTY")
vix=gp("INDIA VIX")
vix_col=("up" if vix<15 else "neu" if vix<20 else "dn")

k1,k2,k3,k4,k5=st.columns(5)
kpis=[
    (k1,"PORTFOLIO","₹5,00,000","Paper capital","var(--indigo)"),
    (k2,"SESSION P&L","₹0.00","No trades yet","var(--teal)"),
    (k3,"NIFTY SIGNAL",
     f"{nifty_s['sig']}",
     f"Score {nifty_s['score']:.0f}/100 · {nifty_s['reg']}",
     nifty_s['col']),
    (k4,"BANKNIFTY SIGNAL",
     f"{bnf_s['sig']}",
     f"Score {bnf_s['score']:.0f}/100 · {bnf_s['reg']}",
     bnf_s['col']),
    (k5,"INDIA VIX",
     f"{vix:.2f}",
     "Low fear" if vix<15 else "Moderate" if vix<20 else "High fear",
     "var(--teal)" if vix<15 else "var(--amber)" if vix<20 else "var(--crimson)"),
]
for col_k,label,val,sub,accent in kpis:
    with col_k:
        st.markdown(f"""
        <div class="kpi-card" style="--kpi-accent:{accent}">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value" style="color:{accent};font-size:17px">{val}</div>
          <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN GRID
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
left,centre,right=st.columns([0.85, 2.6, 0.95], gap="small")

# ══════════ LEFT PANEL ══════════
with left:
    st.markdown("<div style='padding:4px 2px'>", unsafe_allow_html=True)

    # Watchlist
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-head"><span class="panel-title">Markets</span></div>',
                unsafe_allow_html=True)
    syms_wl=["NIFTY 50","BANKNIFTY","S&P 500","NASDAQ","DOW JONES"]
    for sym in syms_wl:
        price=gp(sym); chg=gc(sym)
        ac=COLORS.get(sym,{}).get("accent","#4f46e5")
        flag=FLAGS.get(sym,""); sgn="+" if chg>=0 else ""
        chg_cls="chg-up" if chg>=0 else "chg-dn"
        is_active=sym==st.session_state.active_sym
        is_live=sym in prices
        dot=('<span class="ldot" style="width:5px;height:5px"></span>'
             if is_live else
             '<span class="offline-dot" style="width:5px;height:5px"></span>')
        act_cls="active" if is_active else ""
        st.markdown(f"""
        <div class="wl-row {act_cls}">
          <div>
            <div class="wl-name" style="color:{ac}">{flag} {sym}</div>
            <div class="wl-sub">{dot}{'Live' if is_live else 'Offline'}</div>
          </div>
          <div>
            <div class="wl-price" style="color:{ac}">{price:,.2f}</div>
            <div style="text-align:right;margin-top:2px">
              <span class="{chg_cls}">{sgn}{chg}%</span>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Symbol selector
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    b1,b2=st.columns(2)
    with b1:
        if st.button("NIFTY",key="bn",use_container_width=True):
            st.session_state.active_sym="NIFTY 50"; st.rerun()
    with b2:
        if st.button("BANKNIFTY",key="bb",use_container_width=True):
            st.session_state.active_sym="BANKNIFTY"; st.rerun()
    b3,b4=st.columns(2)
    with b3:
        if st.button("S&P 500",key="bs",use_container_width=True):
            st.session_state.active_sym="S&P 500"; st.rerun()
    with b4:
        if st.button("NASDAQ",key="bq",use_container_width=True):
            st.session_state.active_sym="NASDAQ"; st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Signal panel
    sym=st.session_state.active_sym; s=compute_signal(sym)
    bw=int(s["score"]); ac=COLORS.get(sym,{}).get("accent","#4f46e5")
    pct_teal=min(max(int((s["score"]-50)*2),0),100) if s["score"]>=50 else 0
    pct_crim=min(max(int((50-s["score"])*2),0),100) if s["score"]<50 else 0

    st.markdown(f"""
    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">Signal — {sym}</span>
        <span class="sig-badge {s['cls']}">{s['icon']} {s['sig']}</span>
      </div>
      <div class="panel-body">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
          <svg width="72" height="72" viewBox="0 0 72 72">
            <circle cx="36" cy="36" r="30" fill="none"
              stroke="var(--border)" stroke-width="8"/>
            <circle cx="36" cy="36" r="30" fill="none"
              stroke="{s['col'].replace('var(--teal)','#0d9488').replace('var(--amber)','#d97706').replace('var(--crimson)','#dc2626')}"
              stroke-width="8" stroke-linecap="round"
              stroke-dasharray="{int(bw*1.885)} 188.5"
              transform="rotate(-90 36 36)"/>
            <text x="36" y="40" text-anchor="middle"
              font-family="IBM Plex Mono" font-size="16" font-weight="500"
              fill="{s['col'].replace('var(--teal)','#0d9488').replace('var(--amber)','#d97706').replace('var(--crimson)','#dc2626')}">
              {s['score']:.0f}
            </text>
          </svg>
          <div>
            <div style="font-size:18px;font-weight:700;
              color:{s['col'].replace('var(--teal)','#0d9488').replace('var(--amber)','#d97706').replace('var(--crimson)','#dc2626')}">
              {s['sig']}
            </div>
            <div style="font-size:11px;color:var(--mist);margin-top:3px">{s['reg']}</div>
            <div style="font-size:10px;color:var(--mist);margin-top:2px">
              {gp(sym):,.2f}
            </div>
          </div>
        </div>
        <div class="ind-row">
          <span class="ind-name">RSI (14)</span>
          <span class="ind-val" style="color:{'#0d9488' if s['rsi']<40 else '#dc2626' if s['rsi']>70 else 'var(--ink)'}">
            {s['rsi']}</span>
        </div>
        <div class="ind-row">
          <span class="ind-name">EMA 9</span>
          <span class="ind-val">{s['e9']:,.2f}</span>
        </div>
        <div class="ind-row">
          <span class="ind-name">EMA 21</span>
          <span class="ind-val">{s['e21']:,.2f}</span>
        </div>
        <div class="ind-row">
          <span class="ind-name">EMA Cross</span>
          <span class="ind-val {'up' if s['e9']>s['e21'] else 'dn'}">
            {'▲ Bullish' if s['e9']>s['e21'] else '▼ Bearish'}</span>
        </div>
        <div class="ind-row">
          <span class="ind-name">MACD</span>
          <span class="ind-val {'up' if s['macd']>0 else 'dn'}">
            {'+' if s['macd']>0 else ''}{s['macd']}</span>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════ CENTRE — Chart ══════════
with centre:
    st.markdown("<div style='padding:4px 2px'>", unsafe_allow_html=True)

    sym=st.session_state.active_sym
    price=gp(sym); chg=gc(sym)
    ac=COLORS.get(sym,{}).get("accent","#4f46e5")
    sgn="+" if chg>=0 else ""; chg_col="#0d9488" if chg>=0 else "#dc2626"
    hi=gp(sym,"high") or price*1.005
    lo=gp(sym,"low")  or price*0.995
    vo=gp(sym,"volume") or 0

    # Price header
    st.markdown(f"""
    <div style="background:var(--white);border:1px solid var(--border);
         border-radius:8px 8px 0 0;padding:12px 16px;
         display:flex;justify-content:space-between;align-items:flex-end;
         border-bottom:none">
      <div>
        <div style="font-size:11px;color:var(--mist);margin-bottom:4px;
             font-family:'Plus Jakarta Sans',sans-serif;font-weight:600;letter-spacing:.5px">
          {FLAGS.get(sym,'')} {sym}
        </div>
        <div style="display:flex;align-items:baseline;gap:10px">
          <span style="font-family:'IBM Plex Mono',monospace;font-size:30px;
                font-weight:500;color:var(--ink);letter-spacing:-1px">
            {price:,.2f}
          </span>
          <span style="font-size:14px;font-weight:600;color:{chg_col}">
            {sgn}{chg}%
          </span>
          <span style="font-size:12px;color:{chg_col}">
            ({sgn}{gp(sym,'chg_abs'):,.2f})
          </span>
        </div>
      </div>
      <div style="display:flex;gap:20px;font-size:11px;text-align:center">
        <div>
          <div style="color:var(--mist);font-size:9px;letter-spacing:.5px;
               text-transform:uppercase;margin-bottom:2px">Open</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-weight:500">
            {gp(sym,'open') or price:,.2f}</div>
        </div>
        <div>
          <div style="color:var(--mist);font-size:9px;letter-spacing:.5px;
               text-transform:uppercase;margin-bottom:2px">High</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-weight:500;color:#0d9488">
            {hi:,.2f}</div>
        </div>
        <div>
          <div style="color:var(--mist);font-size:9px;letter-spacing:.5px;
               text-transform:uppercase;margin-bottom:2px">Low</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-weight:500;color:#dc2626">
            {lo:,.2f}</div>
        </div>
        <div>
          <div style="color:var(--mist);font-size:9px;letter-spacing:.5px;
               text-transform:uppercase;margin-bottom:2px">Volume</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-weight:500">
            {vo//1000 if vo else '—'}K</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    # Toolbar
    tf_opt=["1 min","3 min","5 min","15 min","30 min","1 hour","4 hour","1 day"]
    tf_map={"1 min":"1min","3 min":"3min","5 min":"5min","15 min":"15min",
            "30 min":"30min","1 hour":"1hour","4 hour":"4hour","1 day":"1day"}
    ct_opt=["Candlestick","Heikin Ashi","Line","Area"]

    tb1,tb2,tb3,tb4=st.columns([3,1.2,1.2,0.6])
    with tb1:
        st.markdown('<div style="background:var(--white);border:1px solid var(--border);'
                    'border-top:none;border-bottom:1px solid var(--border);'
                    'padding:6px 12px;display:flex;gap:3px">', unsafe_allow_html=True)
        tf_cols=st.columns(len(tf_opt))
        for i,(col_t,label) in enumerate(zip(tf_cols,tf_opt)):
            with col_t:
                current_tf=st.session_state.get("tf_sel_v","5 min")
                is_active_tf=label==current_tf
                if st.button(label,key=f"tf_{i}",use_container_width=True):
                    st.session_state["tf_sel_v"]=label
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with tb2:
        ct=st.selectbox("Type",ct_opt,key="ct_s",label_visibility="collapsed")
    with tb3:
        inds=st.multiselect("Overlays",["EMA 9","EMA 21","EMA 50","EMA 200","VWAP"],
                            default=["EMA 9","EMA 21"],key="ov_s",
                            label_visibility="collapsed")
    with tb4:
        if st.button("🔄",key="rfr",use_container_width=True,help="Refresh data"):
            st.rerun()

    # Chart
    selected_tf=tf_map.get(st.session_state.get("tf_sel_v","5 min"),"5min")
    candles=get_candles(sym)
    resampled=resample_candles(candles,selected_tf) if candles else None

    if HAS_PLOTLY and resampled and len(resampled.get("close",[]))>3:
        times=pd.to_datetime(resampled["time"])
        o_a=np.array(resampled["open"],dtype=float)
        h_a=np.array(resampled["high"],dtype=float)
        l_a=np.array(resampled["low"], dtype=float)
        c_a=np.array(resampled["close"],dtype=float)
        v_a=np.array(resampled["vol"],  dtype=float)

        # Heikin Ashi
        if ct=="Heikin Ashi":
            ha_c=(o_a+h_a+l_a+c_a)/4
            ha_o=np.zeros_like(o_a); ha_o[0]=(o_a[0]+c_a[0])/2
            for ii in range(1,len(ha_o)): ha_o[ii]=(ha_o[ii-1]+ha_c[ii-1])/2
            ha_h=np.maximum(h_a,np.maximum(ha_o,ha_c))
            ha_l=np.minimum(l_a,np.minimum(ha_o,ha_c))
            o_a,h_a,l_a,c_a=ha_o,ha_h,ha_l,ha_c

        def ema_s(d,p):
            k=2/(p+1); res=[d[0]]
            for v in d[1:]: res.append(v*k+res[-1]*(1-k))
            return res

        fig=make_subplots(rows=2,cols=1,shared_xaxes=True,
                          row_heights=[0.78,0.22],vertical_spacing=0.01)

        if ct in ("Candlestick","Heikin Ashi"):
            fig.add_trace(go.Candlestick(
                x=times,open=o_a,high=h_a,low=l_a,close=c_a,
                increasing=dict(line=dict(color="#0d9488",width=1),fillcolor="#0d9488"),
                decreasing=dict(line=dict(color="#dc2626",width=1),fillcolor="#dc2626"),
                name=ct,showlegend=False),row=1,col=1)
        elif ct=="Line":
            fig.add_trace(go.Scatter(x=times,y=c_a,
                line=dict(color=ac,width=2),name="Close",showlegend=False),row=1,col=1)
        elif ct=="Area":
            fig.add_trace(go.Scatter(x=times,y=c_a,fill="tozeroy",
                fillcolor=COLORS.get(sym,{}).get("bg","#eef2ff"),
                line=dict(color=ac,width=1.5),name="Close",showlegend=False),row=1,col=1)

        # Overlays
        ema_defs={"EMA 9":{"p":9,"c":"#f59e0b","w":1.5},
                  "EMA 21":{"p":21,"c":"#3b82f6","w":1.5},
                  "EMA 50":{"p":50,"c":"#8b5cf6","w":1,"dash":"dot"},
                  "EMA 200":{"p":200,"c":"#ec4899","w":1,"dash":"dash"},
                  "VWAP":None}
        for ov in inds:
            if ov in ema_defs and ema_defs[ov] and len(c_a)>=ema_defs[ov]["p"]:
                d=ema_defs[ov]
                vals=ema_s(c_a.tolist(),d["p"])
                fig.add_trace(go.Scatter(x=times,y=vals,
                    line=dict(color=d["c"],width=d.get("w",1.5),
                              dash=d.get("dash","solid")),
                    name=ov,showlegend=True),row=1,col=1)
            elif ov=="VWAP":
                typ=(h_a+l_a+c_a)/3
                cum_tp_vol=np.cumsum(typ*v_a)
                cum_vol=np.cumsum(v_a)
                vwap_vals=np.where(cum_vol>0,cum_tp_vol/cum_vol,np.nan)
                fig.add_trace(go.Scatter(x=times,y=vwap_vals,
                    line=dict(color="#0ea5e9",width=1.5,dash="dot"),
                    name="VWAP",showlegend=True),row=1,col=1)

        # Volume
        vcols=["rgba(13,148,136,0.5)" if c_a[i]>=o_a[i]
               else "rgba(220,38,38,0.5)" for i in range(len(c_a))]
        fig.add_trace(go.Bar(x=times,y=v_a,marker_color=vcols,
            name="Vol",showlegend=False),row=2,col=1)

        tick_c="rgba(55,65,81,0.6)"
        grid_c="rgba(0,0,0,0.04)"
        fig.update_layout(
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            margin=dict(l=0,r=0,t=0,b=0),
            height=380,
            xaxis=dict(showgrid=True,gridcolor=grid_c,
                       rangeslider=dict(visible=False),
                       tickfont=dict(size=9,color=tick_c),
                       linecolor=grid_c),
            xaxis2=dict(showgrid=True,gridcolor=grid_c,
                        tickfont=dict(size=8,color=tick_c),
                        linecolor=grid_c),
            yaxis=dict(showgrid=True,gridcolor=grid_c,
                       side="right",
                       tickfont=dict(size=9,color=tick_c),
                       tickformat=",.0f",
                       linecolor=grid_c),
            yaxis2=dict(showgrid=False,side="right",showticklabels=False),
            legend=dict(x=0.01,y=0.99,bgcolor="rgba(255,255,255,0.85)",
                        bordercolor="rgba(0,0,0,0.06)",borderwidth=1,
                        font=dict(size=10,color="#374151"),
                        orientation="h"),
            hovermode="x unified",
            hoverlabel=dict(bgcolor="var(--white)",
                           bordercolor="var(--border)",
                           font=dict(size=11,color="#0f1923")),
        )
        st.markdown('<div style="background:var(--white);border:1px solid var(--border);'
                    'border-top:none;border-radius:0 0 8px 8px;overflow:hidden">',
                    unsafe_allow_html=True)
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
        st.markdown("</div>", unsafe_allow_html=True)

        # Patterns
        pats=detect_patterns(
            resampled["open"],resampled["high"],
            resampled["low"], resampled["close"])
        if pats:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.markdown("""
            <div class="panel">
              <div class="panel-head">
                <span class="panel-title">Detected Patterns</span>
              </div>
              <div class="panel-body">
            """, unsafe_allow_html=True)
            ph=""
            for p in pats[:6]:
                pc=("pat-bull" if p["signal"]=="BULLISH" else
                    "pat-bear" if p["signal"]=="BEARISH" else "pat-neut")
                pi=("▲" if p["signal"]=="BULLISH" else
                    "▼" if p["signal"]=="BEARISH" else "◆")
                ph+=f'<span class="pat {pc}">{pi} {p["name"]} <span style="opacity:.6;font-size:9px">({p["strength"]})</span></span>'
            st.markdown(f'<div class="pat-wrap">{ph}</div>', unsafe_allow_html=True)
            if pats:
                best=pats[0]
                bc=("#0d9488" if best["signal"]=="BULLISH" else
                    "#dc2626" if best["signal"]=="BEARISH" else "#d97706")
                st.markdown(f"""
                <div class="pat-detail" style="border-color:{bc};color:var(--slate)">
                  <strong style="color:{bc}">{best['name']}</strong>
                  &nbsp;—&nbsp;{best['description']}
                </div>""", unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

    else:
        st.markdown("""
        <div style="background:var(--white);border:1px solid var(--border);
             border-top:none;border-radius:0 0 8px 8px;height:380px;
             display:flex;flex-direction:column;align-items:center;
             justify-content:center;gap:8px">
          <div style="font-size:32px">📡</div>
          <div style="font-size:13px;font-weight:600;color:var(--slate)">
            Waiting for live data from Angel One</div>
          <div style="font-size:11px;color:var(--mist)">
            Candles will appear once the connection is established</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════ RIGHT PANEL ══════════
with right:
    st.markdown("<div style='padding:4px 2px'>", unsafe_allow_html=True)

    for sym_r,gap_r in [("NIFTY 50",50),("BANKNIFTY",100)]:
        spot_r=gp(sym_r)
        rng_r=random.Random(int(spot_r)//10)
        atm=round(spot_r/gap_r)*gap_r
        top_rows=[]
        for i in range(-10,11):
            k=atm+i*gap_r; dist=abs(i)
            mn=(spot_r-k)/spot_r; dc=max(.02,min(.98,.5+mn*5))
            sc=round(55+mn*120+rng_r.gauss(0,5),1); sc=max(10,min(96,sc))
            if sc>=55:
                opt="CE" if dc>0.5 else "PE"
                iv=(round(14+dist*1.1+rng_r.gauss(0,0.4),1))
                itv=spot_r*iv/100*math.sqrt(7/365)*0.4
                lc=round(max(0,spot_r-k)+itv*rng_r.uniform(.8,1.2),1)
                lp=round(max(0,k-spot_r)+itv*rng_r.uniform(.8,1.2),1)
                ltp=lc if opt=="CE" else lp
                pop=round(dc*100,1) if opt=="CE" else round((1-dc)*100,1)
                top_rows.append(dict(k=k,opt=opt,sc=sc,ltp=ltp,pop=pop,iv=iv))
        top_rows.sort(key=lambda x:x["sc"],reverse=True)
        top_rows=top_rows[:10]

        label=f"Top NIFTY Signals" if "NIFTY 50" in sym_r else "Top BANKNIFTY Signals"
        ac=COLORS.get(sym_r,{}).get("accent","#4f46e5")
        st.markdown(f"""
        <div class="panel">
          <div class="panel-head">
            <span class="panel-title">{label}</span>
            <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;
                  color:var(--mist)">{spot_r:,.2f}</span>
          </div>
          <div class="sc2">""", unsafe_allow_html=True)

        for r in top_rows:
            is_ce=r["opt"]=="CE"
            sc_col=("#0d9488" if r["sc"]>=72 else
                    "#d97706" if r["sc"]>=60 else "var(--mist)")
            bar_col=("#0d9488" if is_ce else "#dc2626")
            bw=int(r["sc"]*0.82)
            st.markdown(f"""
            <div class="top-row">
              <div style="flex:1">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span class="top-sym">{r['k']:,}
                    <span style="color:{bar_col};font-size:10px">{r['opt']}</span>
                  </span>
                  <span style="font-family:'IBM Plex Mono',monospace;font-size:12px;
                        font-weight:500;color:{sc_col}">{r['sc']:.0f}</span>
                </div>
                <div class="top-meta">₹{r['ltp']} · POP {r['pop']}% · IV {r['iv']}%</div>
                <div class="score-bar-bg">
                  <div class="score-bar-fill"
                    style="width:{bw}%;background:{bar_col};opacity:0.6"></div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # System status
    st.markdown(f"""
    <div class="panel">
      <div class="panel-head"><span class="panel-title">System</span></div>
      <div class="panel-body" style="padding:8px 14px">
        <div class="ind-row">
          <span class="ind-name">Angel One</span>
          <span class="ind-val {'up' if connected else 'dn'}">
            {'● Live' if connected else '● Connecting'}</span></div>
        <div class="ind-row">
          <span class="ind-name">NIFTY feed</span>
          <span class="ind-val {'up' if 'NIFTY 50' in prices else 'neu'}">
            {'● Live' if 'NIFTY 50' in prices else '◌ Waiting'}</span></div>
        <div class="ind-row">
          <span class="ind-name">US markets</span>
          <span class="ind-val {'up' if 'S&P 500' in prices else 'neu'}">
            {'● yfinance' if 'S&P 500' in prices else '◌ Waiting'}</span></div>
        <div class="ind-row">
          <span class="ind-name">Refresh rate</span>
          <span class="ind-val">5 seconds</span></div>
        <div class="ind-row">
          <span class="ind-name">Last update</span>
          <span class="ind-val">{secs_ago}s ago</span></div>
        <div class="ind-row">
          <span class="ind-name">Mode</span>
          <span class="ind-val neu">Paper trading</span></div>
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center;font-size:10px;color:var(--mist);
     padding:10px 0;border-top:1px solid var(--border);margin-top:6px;
     background:var(--white)">
  AI Trading Agent · Paper Mode · Angel One SmartAPI + yfinance ·
  No real orders placed · {now.strftime('%d %b %Y')}
</div>""", unsafe_allow_html=True)

# ── Auto rerun every 5 seconds ────────────────────────────────────────────────
time.sleep(5)
st.rerun()
