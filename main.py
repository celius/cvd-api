from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v7.7 - True CVD Triad", version="7.7")

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

# --- 1. TRUE SPOT CVD CALCULATION ---
async def get_spot_cvd_24h(session, symbol):
    # Vi henter 24 timer med 1h candles for å beregne Cumulative Volume Delta
    url = f"{BASE_URL_SPOT}/klines?symbol={symbol}&interval=1h&limit=24"
    data = await fetch_url(session, url)
    
    cumulative_delta = 0.0
    deltas = []
    
    if data:
        for candle in data:
            # Binance Kline format:
            # [7]: Quote asset volume (Total Volum i USDT)
            # [10]: Taker buy quote asset volume (Kjøpsvolum i USDT)
            total_vol = float(candle[7])
            buy_vol = float(candle[10])
            sell_vol = total_vol - buy_vol
            
            # Delta = Kjøp - Salg
            delta = buy_vol - sell_vol
            cumulative_delta += delta
            deltas.append(delta)
            
    return cumulative_delta, deltas

# --- 2. OPEN INTEREST & FUNDING ---
async def get_futures_data(session, symbol):
    # Funding Rate
    funding_url = f"{BASE_URL_FUTURES}/premiumIndex?symbol={symbol}"
    funding_data = await fetch_url(session, funding_url)
    funding_rate = float(funding_data['lastFundingRate']) if funding_data else 0.0

    # Open Interest Current
    oi_url = f"{BASE_URL_FUTURES}/openInterest?symbol={symbol}"
    oi_data = await fetch_url(session, oi_url)
    oi_val = float(oi_data['openInterest']) if oi_data else 0.0

    # Open Interest 24h ago (for change calc)
    lookback = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
    hist_url = f"{BASE_URL_FUTURES}/openInterestHist?symbol={symbol}&period=1h&limit=1&startTime={lookback}"
    hist_data = await fetch_url(session, hist_url)
    
    oi_change = 0.0
    if hist_data and len(hist_data) > 0:
        past_oi = float(hist_data[0]['sumOpenInterest'])
        if past_oi > 0:
            oi_change = ((oi_val - past_oi) / past_oi) * 100
            
    return funding_rate, oi_val, oi_change

async def get_price_24h(session, symbol):
    url = f"{BASE_URL_SPOT}/ticker/24hr?symbol={symbol}"
    return await fetch_url(session, url)

# --- RENDER HELPER ---
def render_cvd_bars(deltas, limit=24):
    # Visualiserer kjøp (grønn) vs salg (rød) time for time
    html = "<div style='display: flex; align-items: flex-end; height: 40px; gap: 2px; margin-top: 10px; border-bottom: 1px solid #333;'>"
    if not deltas: return ""
    
    max_val = max([abs(d) for d in deltas]) if deltas else 1
    
    for d in deltas:
        height = (abs(d) / max_val) * 100 # Prosent av høyde
        color = "#00ff9d" if d >= 0 else "#ff4d4d"
        html += f"<div style='flex: 1; height: {height}%; background: {color}; opacity: 0.8;' title='Delta: ${d/1_000_000:.1f}M'></div>"
    html += "</div>"
    return html

def generate_html_card(symbol, price_data, cvd_24h, cvd_deltas, funding, oi_val, oi_change):
    if not price_data: return f"<div class='card'><h2>{symbol}</h2><p>No Data</p></div>"

    price = float(price_data['lastPrice'])
    price_ch = float(price_data['priceChangePercent'])
    
    # Konverter CVD til Millioner
    cvd_m = cvd_24h / 1_000_000
    
    # Tolkning av Triad
    bias = "NEUTRAL"
    bias_color = "#888"
    
    # Enkel logikk for overskrift
    if cvd_m > 0 and oi_change > 0:
        bias = "🚀 STRONG BULL (Spot+OI)"
        bias_color = "#00ff9d"
    elif cvd_m > 0 and oi_change < 0:
        bias = "🦅 SPOT ACCUMULATION"
        bias_color = "#00ccff"
    elif cvd_m < 0 and oi_change > 0:
        bias = "⚠️ WEAK RALLY / SHORTING"
        bias_color = "#ffa500"
    elif cvd_m < 0 and oi_change < 0:
        bias = "🐻 BEARISH OUTFLOW"
        bias_color = "#ff4d4d"

    return f"""
    <div class="card" style="border-left: 4px solid {bias_color};">
        <div class="header">
            <div>
                <div style="font-size: 1.4em; font-weight: bold;">{symbol.replace('USDT','')}</div>
                <div style="font-size: 0.9em; color: #ccc;">${price:,.2f} <span style="color: {'#00ff9d' if price_ch>=0 else '#ff4d4d'}">({price_ch:+.2f}%)</span></div>
            </div>
            <div style="text-align: right;">
                <div style="color: {bias_color}; font-weight: bold; font-size: 0.8em;">{bias}</div>
                <div style="font-size: 0.7em; color: #666;">Funding: <span style="color: {'#ffa500' if funding > 0.01 else '#ccc'}">{funding*100:.4f}%</span></div>
            </div>
        </div>

        <!-- MAIN TRIAD METRICS -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 10px;">
            <div style="background: #111; padding: 10px; border-radius: 4px;">
                <div class="label">Spot CVD (24h)</div>
                <div style="font-size: 1.2em; font-weight: bold; color: {'#00ff9d' if cvd_m>=0 else '#ff4d4d'}">${cvd_m:+.1f}M</div>
                <div style="font-size: 0.7em; color: #666;">Net Market Buying</div>
            </div>
            <div style="background: #111; padding: 10px; border-radius: 4px;">
                <div class="label">OI Change (24h)</div>
                <div style="font-size: 1.2em; font-weight: bold; color: {'#00ff9d' if oi_change>=0 else '#ff4d4d'}">{oi_change:+.2f}%</div>
                <div style="font-size: 0.7em; color: #666;">Leverage Trend</div>
            </div>
        </div>

        <!-- CVD VISUALIZATION -->
        <div style="margin-top: 15px;">
            <div class="label">Spot Delta History (Last 24h)</div>
            {render_cvd_bars(cvd_deltas)}
            <div style="display: flex; justify-content: space-between; font-size: 0.7em; color: #555; margin-top: 2px;">
                <span>24h ago</span>
                <span>Now</span>
            </div>
        </div>
    </div>
    """

BASE_HTML = """
<html>
<head>
    <title>Mode 7: True CVD Triad</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
        .card { background: #161616; border: 1px solid #2a2a2a; padding: 15px; margin-bottom: 20px; border-radius: 8px; }
        .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; }
        .label { font-size: 0.7em; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
    </style>
</head>
<body>
    <h1 style="color: #fff; font-weight: 300; margin-bottom: 30px;">🎯 Mode 7 <span style="color: #00ff9d; font-weight: bold;">True CVD Triad</span></h1>
    <div class="grid">
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    async with aiohttp.ClientSession() as session:
        tasks = []
        for sym in symbols: tasks.append(fetch_coin_data(session, sym))
        results = await asyncio.gather(*tasks)
    html = BASE_HTML + "".join(results) + "</div></body></html>"
    return html

@app.get("/html/{symbol}", response_class=HTMLResponse)
async def single_coin(symbol: str):
    clean = symbol.upper()
    if "USDT" not in clean: clean += "USDT"
    async with aiohttp.ClientSession() as session:
        html = BASE_HTML + await fetch_coin_data(session, clean) + "</div></body></html>"
    return html

async def fetch_coin_data(session, sym):
    # 1. Price
    t1 = get_price_24h(session, sym)
    # 2. Spot CVD
    t2 = get_spot_cvd_24h(session, sym)
    # 3. Futures Data (OI + Funding)
    t3 = get_futures_data(session, sym)
    
    price_data, (cvd, deltas), (fund, oi, oi_ch) = await asyncio.gather(t1, t2, t3)
    
    return generate_html_card(sym, price_data, cvd, deltas, fund, oi, oi_ch)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
