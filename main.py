from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v7.8 - Table of Truth", version="7.8")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL_SPOT = "https://api.binance.com/api/v3"

async def fetch_url(session, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

# --- CORE LOGIC ---
def get_signal(price_ch, cvd_val):
    # Enkel heuristikk for CVD Divergens
    if cvd_val > 0:
        if price_ch > 0.5: return "🚀 Bullish", "#00ff9d"
        elif price_ch < -0.5: return "🦅 Accumulation", "#00ccff" # Pris ned, Kjøp opp
        else: return "🌱 Buying", "#ccffcc"
    elif cvd_val < 0:
        if price_ch < -0.5: return "🐻 Bearish", "#ff4d4d"
        elif price_ch > 0.5: return "🩸 Distribution", "#ffa500" # Pris opp, Salg opp
        else: return "🔻 Selling", "#ffcccc"
    return "⚖️ Neutral", "#888"

async def get_kline_analysis(session, symbol, interval, limit):
    url = f"{BASE_URL_SPOT}/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = await fetch_url(session, url)
    rows = []
    
    if data:
        # Behandle nyeste først
        for k in reversed(data):
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
            
            # Format Date Label
            if interval == '1h':
                label = dt_obj.strftime("%H:00")
            elif interval == '1d':
                label = dt_obj.strftime("%Y-%m-%d")
            elif interval == '1w':
                label = f"Week {dt_obj.strftime('%W')}"
            elif interval == '1M':
                label = dt_obj.strftime("%B %Y")
            else:
                label = str(ts)

            signal_txt, signal_col = get_signal(price_ch, cvd)
            
            rows.append({
                "label": label,
                "price_ch": price_ch,
                "cvd": cvd,
                "signal": signal_txt,
                "color": signal_col
            })
    return rows

def render_table_rows(rows):
    html = ""
    for r in rows:
        p_col = "#00ff9d" if r['price_ch'] >= 0 else "#ff4d4d"
        cvd_fmt = f"${r['cvd']/1_000_000:+.1f}M" if abs(r['cvd']) > 1_000_000 else f"${r['cvd']/1_000:+.0f}k"
        cvd_col = "#00ff9d" if r['cvd'] >= 0 else "#ff4d4d"
        
        html += f"""
        <tr style="border-bottom: 1px solid #222;">
            <td style="padding: 8px; color: #888;">{r['label']}</td>
            <td style="padding: 8px; color: {p_col};">{r['price_ch']:+.2f}%</td>
            <td style="padding: 8px; color: {cvd_col}; font-family: monospace;">{cvd_fmt}</td>
            <td style="padding: 8px; color: {r['color']}; font-weight: bold;">{r['signal']}</td>
        </tr>
        """
    return html

def generate_html_page(symbol, monthly, weekly, daily, hourly, total_90d):
    # Beregn total 90d (summerer weekly grovt eller bruker egen logikk)
    # For enkelhets skyld, lager vi en 'Total' rad øverst basert på dataene vi har
    
    return f"""
    <div class="coin-container" style="margin-bottom: 60px; background: #111; padding: 20px; border-radius: 8px; border: 1px solid #333;">
        <h1 style="margin: 0 0 20px 0; font-size: 2em;">{symbol.replace('USDT','')} Analysis</h1>
        
        <style>
            table  width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 30px; 
            th  text-align: left; padding: 8px; border-bottom: 2px solid #444; color: #aaa; text-transform: uppercase; font-size: 0.8em; 
        </style>

        <!-- TIMES (24H) -->
        <h3 style="color: #00ccff;">⏱️ Siste 24 Timer (Hourly)</h3>
        <table>
            <tr><th>Tid</th><th>Pris %</th><th>Spot CVD ($)</th><th>Signal</th></tr>
            {render_table_rows(hourly)}
        </table>

        <!-- DAGLIG (14D) -->
        <h3 style="color: #00ccff;">📅 Siste 14 Dager (Daily)</h3>
        <table>
            <tr><th>Dato</th><th>Pris %</th><th>Spot CVD ($)</th><th>Signal</th></tr>
            {render_table_rows(daily)}
        </table>

        <!-- UKENTLIG (12W) -->
        <h3 style="color: #00ccff;">📆 Siste 12 Uker (Weekly)</h3>
        <table>
            <tr><th>Uke</th><th>Pris %</th><th>Spot CVD ($)</th><th>Signal</th></tr>
            {render_table_rows(weekly)}
        </table>

        <!-- MÅNEDLIG (3M) -->
        <h3 style="color: #00ccff;">🌕 Siste 3 Måneder (Monthly)</h3>
        <table>
            <tr><th>Måned</th><th>Pris %</th><th>Spot CVD ($)</th><th>Signal</th></tr>
            {render_table_rows(monthly)}
        </table>
    </div>
    """

BASE_HTML = """
<html>
<head>
    <title>Mode 7: Table of Truth</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #050505; color: #e0e0e0; padding: 40px; max-width: 1000px; margin: 0 auto; }
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
    
    # Total 90d logic could be added here, but summing weeks gives good enough proxy for now
    return generate_html_page(sym, mon, wek, day, hor, None)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
