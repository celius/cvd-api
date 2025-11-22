from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
import json

app = FastAPI(title="CVD API v7.3 - Multi-Route Support", version="7.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# URLer for Binance API
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

async def get_oi_data(session, symbol):
    # Hent nåværende Open Interest
    current_url = f"{BASE_URL_FUTURES}/openInterest?symbol={symbol}"
    current_data = await fetch_url(session, current_url)
    
    lookback = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
    hist_url = f"{BASE_URL_FUTURES}/openInterestHist?symbol={symbol}&period=5m&limit=1&startTime={lookback}"
    hist_data = await fetch_url(session, hist_url)

    oi_val = 0.0
    oi_change = 0.0

    if current_data and 'openInterest' in current_data:
        oi_val = float(current_data['openInterest'])
        
        if hist_data and len(hist_data) > 0:
            past_oi = float(hist_data[0]['sumOpenInterest'])
            if past_oi > 0:
                oi_change = ((oi_val - past_oi) / past_oi) * 100
    
    return oi_val, oi_change

def generate_html_card(symbol, spot_data, oi_val, oi_change):
    if not spot_data:
        return f"<div class='card'><h2>{symbol}</h2><p>Ingen data funnet.</p></div>"

    price = float(spot_data['lastPrice'])
    change_24h = float(spot_data['priceChangePercent'])
    volume = float(spot_data['quoteVolume']) / 1_000_000 
    
    price_class = "green" if change_24h >= 0 else "red"
    oi_class = "green" if oi_change >= 0 else "red"

    return f"""
    <div class="card">
        <div class="header">
            <span style="font-weight: bold; font-size: 1.2em;">{symbol.replace('USDT','')}</span>
            <span class="{price_class} price">${price:,.2f}</span>
        </div>
        
        <!-- SNIPER SECTION (FIRST) -->
        <h2>1. Sniper (24h)</h2>
        <div class="metric">
            <span class="label">Price Change 24h</span>
            <span class="{price_class}">{change_24h:+.2f}%</span>
        </div>
        <div class="metric">
            <span class="label">OI Change 24h</span>
            <span class="{oi_class}">{oi_change:+.2f}%</span>
        </div>
        <div class="metric">
            <span class="label">Volume 24h</span>
            <span>${volume:,.1f}M</span>
        </div>
        
        <!-- SWING SECTION -->
        <h2 style="margin-top: 20px;">2. Swing (7d)</h2>
        <div class="metric">
            <span class="label">Trend Status</span>
            <span>Coming soon...</span>
        </div>
    </div>
    """

BASE_HTML_START = """
<html>
<head>
    <title>Mode 7: Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 20px; }
        .card { background: #1a1a1a; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #333; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .price { font-size: 1.5em; font-weight: bold; }
        .green { color: #00ff9d; }
        .red { color: #ff4d4d; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        h2 { color: #888; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; }
        .metric { display: flex; justify-content: space-between; margin: 8px 0; border-bottom: 1px solid #2a2a2a; padding-bottom: 8px; }
        .label { color: #666; }
    </style>
</head>
<body>
    <h1>🎯 Mode 7 Dashboard</h1>
    <div class="grid">
"""

BASE_HTML_END = """
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    async with aiohttp.ClientSession() as session:
        tasks = []
        for sym in symbols:
            tasks.append(fetch_url(session, f"{BASE_URL_SPOT}/ticker/24hr?symbol={sym}"))
            tasks.append(get_oi_data(session, sym))
        results = await asyncio.gather(*tasks)
    
    html_content = BASE_HTML_START
    for i in range(0, len(results), 2):
        sym = symbols[int(i/2)]
        html_content += generate_html_card(sym, results[i], results[i+1][0], results[i+1][1])
    html_content += BASE_HTML_END
    return html_content

@app.get("/html/{symbol}", response_class=HTMLResponse)
async def single_coin(symbol: str):
    clean_symbol = symbol.upper()
    if "USDT" not in clean_symbol:
        clean_symbol += "USDT"
        
    async with aiohttp.ClientSession() as session:
        spot_data = await fetch_url(session, f"{BASE_URL_SPOT}/ticker/24hr?symbol={clean_symbol}")
        oi_val, oi_change = await get_oi_data(session, clean_symbol)
        
    html_content = BASE_HTML_START
    html_content += generate_html_card(clean_symbol, spot_data, oi_val, oi_change)
    html_content += BASE_HTML_END
    return html_content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
