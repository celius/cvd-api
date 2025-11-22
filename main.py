from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v7.6 - Smart Money Signals", version="7.6")

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
    
    # 1h lookback for robusthet
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
        for candle in reversed(data):
            ts = candle[0]
            open_p = float(candle[1])
            close_p = float(candle[4])
            change = ((close_p - open_p) / open_p) * 100
            changes.append({"ts": ts, "change": change})
    return changes

async def get_90d_change(session, symbol):
    url = f"{BASE_URL_SPOT}/klines?symbol={symbol}&interval=1d&limit=91"
    data = await fetch_url(session, url)
    if data and len(data) > 0:
        current_close = float(data[-1][4])
        start_open = float(data[0][1])
        return ((current_close - start_open) / start_open) * 100
    return 0.0

# --- ANALYSE MOTOR ---
def analyze_signal(price_ch, oi_ch):
    # Logic: Tolker forholdet mellom Pris og OI
    if oi_ch > 5.0:
        if price_ch > 2.0:
            return "🚀 BULLISH MOMENTUM", "Price UP + OI UP (Strong Trend)", "#00ff9d" # Green
        elif -2.0 <= price_ch <= 2.0:
            return "🦅 ACCUMULATION", "Price FLAT + OI UP (Whale Positioning)", "#00ccff" # Blue
        else:
            return "📉 AGGRESSIVE SHORTING", "Price DOWN + OI UP (Bearish)", "#ff4d4d" # Red
    elif oi_ch < -5.0:
        if price_ch > 2.0:
            return "⚠️ SHORT COVERING", "Price UP + OI DOWN (Weak Rally)", "#ffa500" # Orange
        else:
            return "🩸 LONG LIQUIDATION", "Price DOWN + OI DOWN (Capitulation)", "#ff0000" # Deep Red
    else:
        return "⚖️ NEUTRAL / CHOP", "Low Activity", "#888" # Grey

def render_mini_grid(changes, limit=12):
    # Mindre, renere grid
    html = "<div style='display: flex; gap: 2px; height: 20px; margin-top: 5px;'>"
    for i, item in enumerate(changes[:limit]):
        val = item['change']
        color = "#00ff9d" if val >= 0 else "#ff4d4d"
        opacity = min(abs(val)*10 + 0.3, 1.0) # Mer intens farge ved større utslag
        html += f"<div style='flex: 1; background: {color}; opacity: {opacity}; border-radius: 2px;' title='{val:+.2f}%'></div>"
    html += "</div>"
    return html

def generate_html_card(symbol, price_data, oi_val, oi_change, ch_90d, monthly, weekly, daily, hourly):
    if not price_data: return f"<div class='card'><h2>{symbol}</h2><p>No Data</p></div>"

    price = float(price_data['lastPrice'])
    price_ch_24h = float(price_data['priceChangePercent'])
    
    # Kjør analyse
    signal_title, signal_desc, signal_color = analyze_signal(price_ch_24h, oi_change)

    return f"""
    <div class="card" style="border-top: 4px solid {signal_color};">
        <!-- HEADER & SIGNAL -->
        <div class="header">
            <div>
                <div style="font-size: 1.5em; font-weight: bold;">{symbol.replace('USDT','')}</div>
                <div style="font-size: 0.8em; color: #888;">${price:,.2f}</div>
            </div>
            <div style="text-align: right;">
                <div style="color: {signal_color}; font-weight: bold; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px;">{signal_title}</div>
                <div style="font-size: 0.7em; color: #666;">{signal_desc}</div>
            </div>
        </div>

        <!-- KEY METRICS -->
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px; background: #111; padding: 10px; border-radius: 6px;">
            <div style="text-align: center;">
                <div class="label">Price 24h</div>
                <div style="color: {'#00ff9d' if price_ch_24h >=0 else '#ff4d4d'}">{price_ch_24h:+.2f}%</div>
            </div>
            <div style="text-align: center;">
                <div class="label">OI 24h</div>
                <div style="color: {'#00ff9d' if oi_change >=0 else '#ff4d4d'}">{oi_change:+.2f}%</div>
            </div>
            <div style="text-align: center;">
                <div class="label">90d Trend</div>
                <div style="color: {'#00ff9d' if ch_90d >=0 else '#ff4d4d'}">{ch_90d:+.1f}%</div>
            </div>
        </div>

        <!-- TIMELINES (Mini Visuals) -->
        <div style="margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.7em; color: #666; margin-bottom: 2px;">
                <span>LAST 24 HOURS (Hourly)</span>
                <span>NOW</span>
            </div>
            {render_mini_grid(hourly, 24)}
        </div>

        <div>
            <div style="display: flex; justify-content: space-between; font-size: 0.7em; color: #666; margin-bottom: 2px;">
                <span>LAST 14 DAYS (Daily)</span>
                <span>TODAY</span>
            </div>
            {render_mini_grid(daily, 14)}
        </div>
        
        <div style="margin-top: 10px; font-size: 0.8em; color: #444; text-align: center;">
            Move mouse over bars to see values
        </div>
    </div>
    """

BASE_HTML = """
<html>
<head>
    <title>Mode 7: Smart Signals</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
        .card { background: #161616; border: 1px solid #2a2a2a; padding: 15px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #222; }
        .label { font-size: 0.7em; color: #666; text-transform: uppercase; margin-bottom: 2px; }
        .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
    </style>
</head>
<body>
    <h1 style="color: #fff; margin-bottom: 30px; font-weight: 300;">🎯 Mode 7 <span style="font-weight: bold; color: #00ccff;">Smart Signals</span></h1>
    <div class="grid-container">
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
    clean_symbol = symbol.upper()
    if "USDT" not in clean_symbol: clean_symbol += "USDT"
    async with aiohttp.ClientSession() as session:
        html_card = await fetch_coin_data(session, clean_symbol)
    html = BASE_HTML + html_card + "</div></body></html>"
    return html

async def fetch_coin_data(session, symbol):
    spot_task = fetch_url(session, f"{BASE_URL_SPOT}/ticker/24hr?symbol={symbol}")
    oi_task = get_oi_data(session, symbol)
    c90_task = get_90d_change(session, symbol)
    # Vi trenger nok data for grid
    day_task = get_kline_changes(session, symbol, "1d", 14)
    hor_task = get_kline_changes(session, symbol, "1h", 24)

    results = await asyncio.gather(spot_task, oi_task, c90_task, day_task, hor_task)
    # Vi skipper monthly/weekly lister for renere UI, men beholder dataen hvis vi vil ha den senere
    # Sender dummy lister for nå for å matche funksjonssignatur
    return generate_html_card(symbol, results[0], results[1][0], results[1][1], results[2], [], [], results[3], results[4])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
