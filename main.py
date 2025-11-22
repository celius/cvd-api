from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v7.9 - Table + OI", version="7.9")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL_SPOT = "https://api.binance.com/api/v3"
BASE_URL_FUTURES = "https://fapi.binance.com/fapi/v1"

async def fetch_url(session, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

# --- CORE LOGIC ---
def get_signal(price_ch, cvd_val, oi_ch=0):
    # Avansert signal-logikk
    # 1. Divergens Pris vs CVD (Spot drivkraft)
    # 2. OI bekrefter styrke (Leverage)
    
    signal = "⚖️ Neutral"
    color = "#888"

    if cvd_val > 0: # Spot Kjøper
        if price_ch < -0.5: 
            signal = "🦅 Accumulation" # Pris ned, Spot kjøper
            color = "#00ccff"
        elif price_ch > 0.5:
            if oi_ch > 0:
                signal = "🚀 Bullish" # Alt opp
                color = "#00ff9d"
            else:
                signal = "⚠️ Weak Rally" # Spot kjøper, men OI faller (short cover?)
                color = "#ffa500"
    elif cvd_val < 0: # Spot Selger
        if price_ch > 0.5:
            signal = "🩸 Distribution" # Pris opp, Spot selger
            color = "#ff4d4d"
        elif price_ch < -0.5:
            if oi_ch > 0:
                signal = "📉 Bearish" # Alt ned, aggressive shorts
                color = "#ff0000"
            else:
                signal = "🔻 Selling"
                color = "#ffcccc"
                
    return signal, color

async def get_oi_history_map(session, symbol, period, limit):
    # Henter OI historikk og lager et map {timestamp_ms: oi_value_usdt}
    # Binance støtter perioder: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
    # Map kline intervals to OI intervals
    oi_period = period
    if period == '1w' or period == '1M': oi_period = '1d' # Fallback to daily for long terms
    
    url = f"{BASE_URL_FUTURES}/openInterestHist?symbol={symbol}&period={oi_period}&limit={limit}"
    data = await fetch_url(session, url)
    
    oi_map = {}
    if data:
        for item in data:
            # item: {'symbol': 'BTCUSDT', 'sumOpenInterest': '...', 'sumOpenInterestValue': '...', 'timestamp': ...}
            ts = int(item['timestamp'])
            val = float(item['sumOpenInterestValue']) # Value in USDT
            oi_map[ts] = val
            
            # For weekly/monthly, we might get daily data points. 
            # We'll settle for exact match lookup for now, or nearest.
            
    return oi_map

async def get_kline_analysis(session, symbol, interval, limit):
    # Hent Klines (Pris + CVD)
    kline_url = f"{BASE_URL_SPOT}/klines?symbol={symbol}&interval={interval}&limit={limit}"
    klines = await fetch_url(session, kline_url)
    
    # Hent OI (Prøver å matche lengde)
    # Merk: OI limit max er ofte 30 for Binance, men vi prøver 'limit' parameteren
    oi_map = await get_oi_history_map(session, symbol, interval, limit)
    
    rows = []
    
    if klines:
        # Behandle nyeste først
        prev_oi = 0
        
        # Vi itererer forlengs først for å regne OI diff korrekt, så snur vi for visning
        processed_rows = []
        
        for i, k in enumerate(klines):
            ts = int(k[0])
            dt_obj = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            
            open_p = float(k[1])
            close_p = float(k[4])
            vol_usdt = float(k[7])
            buy_vol_usdt = float(k[10])
            sell_vol_usdt = vol_usdt - buy_vol_usdt
            
            # Metrics
            price_ch = ((close_p - open_p) / open_p) * 100
            cvd = buy_vol_usdt - sell_vol_usdt
            
            # OI Lookup
            # Klines ts is open time. OI Hist ts is also open time (usually)
            # Vi prøver å finne nærmeste OI punkt
            oi_val = oi_map.get(ts, 0.0)
            
            # Hvis vi ikke fant exact match (f.eks. weekly candles vs daily OI), ta siste tilgjengelige
            if oi_val == 0.0 and interval in ['1w', '1M']:
                 # Søk i map etter nærmeste
                 pass # Foreløpig 0

            oi_ch_percent = 0.0
            if prev_oi > 0 and oi_val > 0:
                oi_ch_percent = ((oi_val - prev_oi) / prev_oi) * 100
            
            prev_oi = oi_val

            # Format Date Label
            if interval == '1h': label = dt_obj.strftime("%H:00")
            elif interval == '1d': label = dt_obj.strftime("%Y-%m-%d")
            elif interval == '1w': label = f"Uke {dt_obj.strftime('%W')}"
            elif interval == '1M': label = dt_obj.strftime("%B")
            else: label = str(ts)

            signal_txt, signal_col = get_signal(price_ch, cvd, oi_ch_percent)
            
            processed_rows.append({
                "label": label,
                "price_ch": price_ch,
                "cvd": cvd,
                "oi": oi_val,
                "oi_ch": oi_ch_percent,
                "signal": signal_txt,
                "color": signal_col
            })
            
        rows = list(reversed(processed_rows)) # Nyeste øverst
        
    return rows

def render_table_rows(rows):
    html = ""
    for r in rows:
        p_col = "#00ff9d" if r['price_ch'] >= 0 else "#ff4d4d"
        
        # CVD Format
        if abs(r['cvd']) > 1_000_000: cvd_fmt = f"${r['cvd']/1_000_000:+.1f}M"
        else: cvd_fmt = f"${r['cvd']/1_000:+.0f}k"
        cvd_col = "#00ff9d" if r['cvd'] >= 0 else "#ff4d4d"
        
        # OI Format
        if r['oi'] > 0:
            if r['oi'] > 1_000_000_000: oi_fmt = f"${r['oi']/1_000_000_000:.1f}B"
            else: oi_fmt = f"${r['oi']/1_000_000:.1f}M"
            oi_ch_fmt = f"({r['oi_ch']:+.1f}%)"
            oi_col = "#00ff9d" if r['oi_ch'] >= 0 else "#ff4d4d"
        else:
            oi_fmt = "N/A"
            oi_ch_fmt = ""
            oi_col = "#666"

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
            <div style="font-size: 0.8em; color: #666;">v7.9 Table of Truth</div>
        </div>
        
        <style>
            table  width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 30px; 
            th  text-align: left; padding: 8px; border-bottom: 2px solid #444; color: #aaa; text-transform: uppercase; font-size: 0.8em; 
        </style>

        <!-- TIMES (24H) -->
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⏱️ Siste 24 Timer (Hourly)</h3>
        <table>
            <tr><th width="15%">Tid</th><th width="15%">Pris %</th><th width="20%">Spot CVD</th><th width="25%">Open Interest</th><th width="25%">Signal</th></tr>
            {render_table_rows(hourly)}
        </table>

        <!-- DAGLIG (14D) -->
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px; margin-top: 30px;">📅 Siste 14 Dager (Daily)</h3>
        <table>
            <tr><th>Dato</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Signal</th></tr>
            {render_table_rows(daily)}
        </table>

        <!-- UKENTLIG (12W) -->
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px; margin-top: 30px;">📆 Siste 12 Uker (Weekly)</h3>
        <table>
            <tr><th>Uke</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Signal</th></tr>
            {render_table_rows(weekly)}
        </table>

        <!-- MÅNEDLIG (3M) -->
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px; margin-top: 30px;">🌕 Siste 3 Måneder (Monthly)</h3>
        <table>
            <tr><th>Måned</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Signal</th></tr>
            {render_table_rows(monthly)}
        </table>
    </div>
    """

BASE_HTML = """
<html>
<head>
    <title>Mode 7: Table of Truth</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #050505; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }
    </style>
</head>
<body>
"""

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
    # Fetch all granularities
    t_mon = get_kline_analysis(session, sym, "1M", 3)
    t_wek = get_kline_analysis(session, sym, "1w", 12)
    t_day = get_kline_analysis(session, sym, "1d", 14)
    t_hor = get_kline_analysis(session, sym, "1h", 24)
    
    mon, wek, day, hor = await asyncio.gather(t_mon, t_wek, t_day, t_hor)
    
    return generate_html_page(sym, mon, wek, day, hor)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
