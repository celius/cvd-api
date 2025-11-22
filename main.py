from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v7.5 - Data Beast", version="7.5")

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

async def get_oi_data(session, symbol):
    current_url = f"{BASE_URL_FUTURES}/openInterest?symbol={symbol}"
    current_data = await fetch_url(session, current_url)
    
    # Bruker 1h oppløsning for å øke sjansen for treff på historikk
    lookback = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
    hist_url = f"{BASE_URL_FUTURES}/openInterestHist?symbol={symbol}&period=1h&limit=1&startTime={lookback}"
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

async def get_kline_changes(session, symbol, interval, limit):
    url = f"{BASE_URL_SPOT}/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = await fetch_url(session, url)
    changes = []
    if data:
        # data: [time, open, high, low, close, ...]
        # Returnerer nyeste først
        for candle in reversed(data):
            ts = candle[0]
            open_p = float(candle[1])
            close_p = float(candle[4])
            change = ((close_p - open_p) / open_p) * 100
            changes.append({"ts": ts, "change": change})
    return changes

async def get_90d_change(session, symbol):
    # Henter 1d candles, 90 dager tilbake
    url = f"{BASE_URL_SPOT}/klines?symbol={symbol}&interval=1d&limit=91"
    data = await fetch_url(session, url)
    if data and len(data) > 0:
        current_close = float(data[-1][4])
        start_open = float(data[0][1])
        return ((current_close - start_open) / start_open) * 100
    return 0.0

def render_grid(changes, label_prefix=""):
    html = "<div style='display: grid; grid-template-columns: repeat(auto-fill, minmax(60px, 1fr)); gap: 5px; margin-top: 5px;'>"
    for i, item in enumerate(changes):
        val = item['change']
        color = "#00ff9d" if val >= 0 else "#ff4d4d"
        # Enkel visualisering: bare tallet
        html += f"<div style='background: #222; padding: 5px; text-align: center; border-radius: 4px; font-size: 0.8em;'><span style='color:{color}'>{val:+.1f}%</span></div>"
    html += "</div>"
    return html

def render_list(changes, labels):
    html = "<div style='display: flex; flex-direction: column; gap: 5px; margin-top: 5px;'>"
    for i, item in enumerate(changes):
        if i >= len(labels): break
        val = item['change']
        color = "#00ff9d" if val >= 0 else "#ff4d4d"
        html += f"<div style='display: flex; justify-content: space-between; font-size: 0.9em;'><span style='color: #888'>{labels[i]}</span><span style='color:{color}'>{val:+.2f}%</span></div>"
    html += "</div>"
    return html

def generate_html_card(symbol, price_data, oi_val, oi_change, ch_90d, monthly, weekly, daily, hourly):
    if not price_data:
        return f"<div class='card'><h2>{symbol}</h2><p>No Data</p></div>"

    price = float(price_data['lastPrice'])
    price_class = "green" if float(price_data['priceChangePercent']) >= 0 else "red"
    oi_class = "green" if oi_change >= 0 else "red"
    
    # Labels for lister
    months = ["Denne mnd", "Forrige mnd", "2 mnd siden"]
    weeks = ["Denne uken", "Forrige uke", "2 uker siden", "3 uker siden"]

    return f"""
    <div class="card">
        <div class="header">
            <span style="font-size: 1.4em; font-weight: bold;">{symbol.replace('USDT','')}</span>
            <span class="{price_class} price">${price:,.2f}</span>
        </div>

        <!-- TOP METRICS -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
            <div>
                <div class="label">90d Total</div>
                <div class="{'green' if ch_90d >=0 else 'red'}" style="font-size: 1.1em; font-weight:bold;">{ch_90d:+.2f}%</div>
            </div>
            <div>
                <div class="label">OI 24h Change</div>
                <div class="{oi_class}" style="font-size: 1.1em; font-weight:bold;">{oi_change:+.2f}%</div>
            </div>
        </div>

        <!-- HOURLY (LAST 24) -->
        <h3 style="margin: 15px 0 5px 0; font-size: 0.9em; color: #aaa;">Siste 24 Timer (Nyeste først)</h3>
        {render_grid(hourly[:24])}

        <!-- DAILY (LAST 14) -->
        <h3 style="margin: 15px 0 5px 0; font-size: 0.9em; color: #aaa;">Siste 14 Dager (Nyeste først)</h3>
        {render_grid(daily[:14])}

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
            <!-- WEEKLY -->
            <div>
                <h3 style="margin: 0 0 5px 0; font-size: 0.9em; color: #aaa;">Ukentlig</h3>
                {render_list(weekly, weeks)}
            </div>
            <!-- MONTHLY -->
            <div>
                <h3 style="margin: 0 0 5px 0; font-size: 0.9em; color: #aaa;">Månedlig</h3>
                {render_list(monthly, months)}
            </div>
        </div>
    </div>
    """

BASE_HTML = """
<html>
<head>
    <title>Mode 7: Deep Data</title>
    <style>
        body { font-family: 'Courier New', monospace; background: #0d0d0d; color: #ccc; padding: 20px; }
        .card { background: #161616; border: 1px solid #333; padding: 15px; margin-bottom: 20px; border-radius: 8px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .green { color: #00ff9d; }
        .red { color: #ff4d4d; }
        .label { font-size: 0.8em; color: #666; text-transform: uppercase; }
        h1 { font-size: 1.5em; margin-bottom: 20px; color: #fff; }
    </style>
</head>
<body>
    <h1>🎯 Mode 7: Data Beast</h1>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px;">
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    async with aiohttp.ClientSession() as session:
        tasks = []
        for sym in symbols:
            tasks.append(fetch_coin_data(session, sym))
        results = await asyncio.gather(*tasks)
    
    html = BASE_HTML
    for res in results:
        html += res
    html += "</div></body></html>"
    return html

@app.get("/html/{symbol}", response_class=HTMLResponse)
async def single_coin(symbol: str):
    clean_symbol = symbol.upper()
    if "USDT" not in clean_symbol: clean_symbol += "USDT"
    
    async with aiohttp.ClientSession() as session:
        html_card = await fetch_coin_data(session, clean_symbol)
    
    html = BASE_HTML + html_card + "</div></body></html>"
    return html

async def fetch_coin_data(session, symbol):
    # 1. Spot Price Stats
    spot_task = fetch_url(session, f"{BASE_URL_SPOT}/ticker/24hr?symbol={symbol}")
    # 2. OI Data
    oi_task = get_oi_data(session, symbol)
    # 3. 90d Change
    c90_task = get_90d_change(session, symbol)
    # 4. Monthly (last 3)
    mon_task = get_kline_changes(session, symbol, "1M", 3)
    # 5. Weekly (last 4)
    wek_task = get_kline_changes(session, symbol, "1w", 4)
    # 6. Daily (last 14)
    day_task = get_kline_changes(session, symbol, "1d", 14)
    # 7. Hourly (last 24)
    hor_task = get_kline_changes(session, symbol, "1h", 24)

    results = await asyncio.gather(spot_task, oi_task, c90_task, mon_task, wek_task, day_task, hor_task)
    
    spot, (oi_val, oi_ch), ch90, mon, wek, day, hor = results
    
    return generate_html_card(symbol, spot, oi_val, oi_ch, ch90, mon, wek, day, hor)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
