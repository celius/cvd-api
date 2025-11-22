from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
import json

app = FastAPI(title="CVD API v7.2 - Sniper First", version="7.2")

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
    
    # Hent historisk OI (24h siden) for å regne endring
    # Vi bruker klines eller openInterestHist. 
    # Enklere metode: Vi bruker 24hr ticker statistics fra Futures hvis tilgjengelig, 
    # men Binance Futures 24hr ticker har ikke OI change direkte.
    # Vi henter 'openInterestHist' med period '5m' limit 1 fra 24h siden.
    
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

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # Default symbols
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for sym in symbols:
            # Hent Spot Ticker for pris/volum
            tasks.append(fetch_url(session, f"{BASE_URL_SPOT}/ticker/24hr?symbol={sym}"))
            # Hent Futures data for OI
            tasks.append(get_oi_data(session, sym))
        
        results = await asyncio.gather(*tasks)
    
    # Prosesser data
    html_content = """
    <html>
    <head>
        <title>Mode 7: Sniper Dashboard v7.2</title>
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
        <h1>🎯 Mode 7: Sniper Dashboard</h1>
        <p style='color: #666; margin-bottom: 30px;'>v7.2 | Sniper Rhythm First | Smart Money Triad</p>
        <div class="grid">
    """

    # Loop gjennom resultatene (parvis: spot data, oi data)
    for i in range(0, len(results), 2):
        spot_data = results[i]
        oi_val, oi_change = results[i+1]
        
        if not spot_data:
            continue
            
        symbol = symbols[int(i/2)]
        price = float(spot_data['lastPrice'])
        change_24h = float(spot_data['priceChangePercent'])
        volume = float(spot_data['quoteVolume']) / 1_000_000 # i millioner
        
        price_class = "green" if change_24h >= 0 else "red"
        oi_class = "green" if oi_change >= 0 else "red"
        
        html_content += f"""
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

            <!-- MACRO SECTION -->
            <h2 style="margin-top: 20px;">3. Macro (90d)</h2>
            <div class="metric">
                <span class="label">Regime</span>
                <span>Coming soon...</span>
            </div>
        </div>
        """
        
    html_content += """
        </div>
    </body>
    </html>
    """
    return html_content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
