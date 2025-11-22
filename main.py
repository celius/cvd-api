from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v7.11 - Nuanced Signals", version="7.11")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Base URLs
DOMAIN_SPOT = "https://api.binance.com"
DOMAIN_FUTURES = "https://fapi.binance.com"

async def fetch_url(session, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Status {response.status} for {url}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

# --- CORE LOGIC (8 States) ---
def get_signal(price_ch, cvd_val, oi_ch=0):
    signal = "⚖️ Neutral"
    color = "#888"

    # PRICE UP (> 0.5%)
    if price_ch > 0.5:
        if cvd_val > 0: # Spot Buying
            if oi_ch > 0:
                signal = "🚀 Bullish (Strong)"
                color = "#00ff9d" # Green
            else:
                signal = "⚠️ Bullish (Short Cover)" # Spot buys, but OI drops
                color = "#ccffcc" # Pale Green
        else: # Spot Selling (Divergence)
            if oi_ch > 0:
                signal = "🩸 Distribution (Into FOMO)" # Spot sells to new longs
                color = "#ff4d4d" # Red
            else:
                signal = "🩸 Distribution (Short Cover)" # Spot sells while shorts close
                color = "#ffa500" # Orange

    # PRICE DOWN (< -0.5%)
    elif price_ch < -0.5:
        if cvd_val > 0: # Spot Buying (Divergence)
            if oi_ch > 0:
                signal = "🦅 Accumulation (Absorbing)" # Spot buys against new shorts
                color = "#00ccff" # Blue
            else:
                signal = "🦅 Accumulation (Capitulation)" # Spot buys liquidation wick
                color = "#0099ff" # Darker Blue
        else: # Spot Selling
            if oi_ch > 0:
                signal = "📉 Bearish (Aggressive)" # Spot sells + new shorts
                color = "#ff0000" # Deep Red
            else:
                signal = "🔻 Bearish (Long Liq)" # Spot sells + longs closing
                color = "#ffcccc" # Pale Red
    
    # CHOP / NEUTRAL
    else:
        if cvd_val > 0: 
            signal = "🌱 Passive Buying"
            color = "#ccffcc"
        elif cvd_val < 0:
            signal = "🍂 Passive Selling"
            color = "#ffcccc"

    return signal, color

async def get_oi_history_map(session, symbol, period, limit):
    oi_period = period
    req_limit = limit
    if period == '1w': 
        oi_period = '1d'
        req_limit = limit * 7 
    elif period == '1M': 
        oi_period = '1d'
        req_limit = limit * 30 
    if req_limit > 499: req_limit = 499
    
    url = f"{DOMAIN_FUTURES}/futures/data/openInterestHist?symbol={symbol}&period={oi_period}&limit={req_limit}"
    data = await fetch_url(session, url)
    oi_map = {}
    if data:
        for item in data:
            ts = int(item['timestamp'])
            val = float(item['sumOpenInterestValue'])
            oi_map[ts] = val
    return oi_map

def get_closest_oi(ts, oi_map):
    if not oi_map: return 0.0
    if ts in oi_map: return oi_map[ts]
    keys = list(oi_map.keys())
    if not keys: return 0.0
    closest_ts = min(keys, key=lambda k: abs(k - ts))
    return oi_map[closest_ts]

async def get_kline_analysis(session, symbol, interval, limit):
    kline_url = f"{DOMAIN_SPOT}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    klines = await fetch_url(session, kline_url)
    oi_map = await get_oi_history_map(session, symbol, interval, limit)
    rows = []
    
    if klines:
        prev_oi = 0
        processed_rows = []
        for i, k in enumerate(klines):
            ts = int(k[0])
            dt_obj = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            open_p = float(k[1])
            close_p = float(k[4])
            buy_vol = float(k[10])
            sell_vol = float(k[7]) - buy_vol
            
            price_ch = ((close_p - open_p) / open_p) * 100
            cvd = buy_vol - sell_vol
            oi_val = get_closest_oi(ts, oi_map)
            
            oi_ch_percent = 0.0
            if prev_oi > 0 and oi_val > 0:
                oi_ch_percent = ((oi_val - prev_oi) / prev_oi) * 100
            prev_oi = oi_val

            # Labels
            if interval == '1h': label = dt_obj.strftime("%H:00")
            elif interval == '1d': label = dt_obj.strftime("%Y-%m-%d")
            elif interval == '1w': label = f"Uke {dt_obj.strftime('%W')}"
            elif interval == '1M': label = dt_obj.strftime("%B")
            else: label = str(ts)

            signal_txt, signal_col = get_signal(price_ch, cvd, oi_ch_percent)
            
            processed_rows.append({
                "label": label, "price_ch": price_ch, "cvd": cvd,
                "oi": oi_val, "oi_ch": oi_ch_percent,
                "signal": signal_txt, "color": signal_col
            })
        rows = list(reversed(processed_rows))
    return rows

def render_table_rows(rows):
    html = ""
    for r in rows:
        p_col = "#00ff9d" if r['price_ch'] >= 0 else "#ff4d4d"
        if abs(r['cvd']) > 1_000_000: cvd_fmt = f"${r['cvd']/1_000_000:+.1f}M"
        else: cvd_fmt = f"${r['cvd']/1_000:+.0f}k"
        cvd_col = "#00ff9d" if r['cvd'] >= 0 else "#ff4d4d"
        
        if r['oi'] > 0:
            if r['oi'] > 1_000_000_000: oi_fmt = f"${r['oi']/1_000_000_000:.1f}B"
            else: oi_fmt = f"${r['oi']/1_000_000:.1f}M"
            oi_ch_fmt = f"({r['oi_ch']:+.1f}%)"
            oi_col = "#00ff9d" if r['oi_ch'] >= 0 else "#ff4d4d"
        else:
            oi_fmt = "N/A"; oi_ch_fmt = ""; oi_col = "#666"

        html += f"""
        <tr style="border-bottom: 1px solid #222;">
            <td style="padding: 8px; color: #aaa; font-size: 0.9em;">{r['label']}</td>
            <td style="padding: 8px; color: {p_col};">{r['price_ch']:+.2f}%</td>
            <td style="padding: 8px; color: {cvd_col}; font-family: monospace;">{cvd_fmt}</td>
            <td style="padding: 8px; font-family: monospace;">
                <span style="color: #eee;">{oi_fmt}</span> 
                <span style="color: {oi_col}; font-size: 0.8em;">{oi_ch_fmt}</span>
            </td>
            <td style="padding: 8px; color: {r['color']}; font-weight: bold; font-size: 0.9em;">{r['signal']}</td>
        </tr>
        """
    return html

def generate_html_page(symbol, monthly, weekly, daily, hourly):
    return f"""
    <div class="coin-container" style="margin-bottom: 60px; background: #111; padding: 20px; border-radius: 8px; border: 1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 2em;">{symbol.replace('USDT','')} Analysis</h1>
            <div style="font-size: 0.8em; color: #666;">v7.11 Nuanced Signals</div>
        </div>
        <style>table  width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 30px;  th  text-align: left; padding: 8px; border-bottom: 2px solid #444; color: #aaa; text-transform: uppercase; font-size: 0.8em; </style>
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⏱️ Siste 24 Timer (Hourly)</h3>
        <table><tr><th width="15%">Tid</th><th width="15%">Pris %</th><th width="20%">Spot CVD</th><th width="25%">Open Interest</th><th width="25%">Signal</th></tr>{render_table_rows(hourly)}</table>
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px; margin-top: 30px;">📅 Siste 14 Dager (Daily)</h3>
        <table><tr><th>Dato</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Signal</th></tr>{render_table_rows(daily)}</table>
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px; margin-top: 30px;">📆 Siste 12 Uker (Weekly)</h3>
        <table><tr><th>Uke</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Signal</th></tr>{render_table_rows(weekly)}</table>
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px; margin-top: 30px;">🌕 Siste 3 Måneder (Monthly)</h3>
        <table><tr><th>Måned</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Signal</th></tr>{render_table_rows(monthly)}</table>
    </div>
    """

BASE_HTML = """<html><head><title>Mode 7: Table of Truth</title><style>body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #050505; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }</style></head><body>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    async with aiohttp.ClientSession() as session:
        tasks = []
        for sym in symbols: tasks.append(fetch_coin_data(session, sym))
        results = await asyncio.gather(*tasks)
    html = BASE_HTML + "".join(results) + "</body></html>"
    return html

@app.get("/html/{symbol}", response_class=HTMLResponse)
async def single_coin(symbol: str):
    clean = symbol.upper()
    if "USDT" not in clean: clean += "USDT"
    async with aiohttp.ClientSession() as session:
        html = BASE_HTML + await fetch_coin_data(session, clean) + "</body></html>"
    return html

async def fetch_coin_data(session, sym):
    t_mon = get_kline_analysis(session, sym, "1M", 3)
    t_wek = get_kline_analysis(session, sym, "1w", 12)
    t_day = get_kline_analysis(session, sym, "1d", 14)
    t_hor = get_kline_analysis(session, sym, "1h", 24)
    mon, wek, day, hor = await asyncio.gather(t_mon, t_wek, t_day, t_hor)
    return generate_html_page(sym, mon, wek, day, hor)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
