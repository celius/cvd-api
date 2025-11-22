from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v7.12 - Explicit Analysis", version="7.12")

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
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

# --- EXPLICIT SIGNAL LOGIC ---
def get_signal(price_ch, cvd_val, oi_ch=0):
    # Returnerer (Overskrift, Forklaring, Farge)
    
    # PRICE UP (> 0.5%)
    if price_ch > 0.5:
        if cvd_val > 0: 
            if oi_ch > 0:
                return "🚀 STERK OPPGANG", "Spot kjøper + Nye penger inn (OI opp). Trenden er sunn.", "#00ff9d"
            else:
                return "⚠️ SVAK OPPGANG", "Spot kjøper, men OI faller (Shorts dekkes inn).", "#ccffcc"
        else: 
            if oi_ch > 0:
                return "🩸 DISTRIBUSJON (FOMO)", "Pris opp, men Spot selger til nye Longs (Topp-signal).", "#ff4d4d"
            else:
                return "💸 DISTRIBUSJON (EXIT)", "Pris opp, men Spot selger seg ut mens Shorters dekker.", "#ffa500"

    # PRICE DOWN (< -0.5%)
    elif price_ch < -0.5:
        if cvd_val > 0: 
            if oi_ch > 0:
                return "🛡️ ABSORBERING (SQUEEZE)", "Pris faller, men Spot kjøper mot nye Shorts.", "#00ccff"
            else:
                return "🦅 AKKUMULERING (DIP)", "Pris faller, Spot plukker bunnen mens Longs gir opp.", "#0099ff"
        else: 
            if oi_ch > 0:
                return "📉 AGGRESSIVT SALG", "Spot selger + Nye penger shorter. Trenden er ned.", "#ff0000"
            else:
                return "🔥 KAPITULASJON", "Spot selger + Longs blir tvangssolgt (OI ned).", "#ffcccc"
    
    # CHOP / NEUTRAL
    else:
        if cvd_val > 0: return "🌱 PASSIV KJØPING", "Sidelengs marked, men Spot samler opp.", "#ccffcc"
        elif cvd_val < 0: return "🍂 PASSIVT SALG", "Sidelengs marked, Spot reduserer.", "#ffcccc"
        else: return "⚖️ NØYTRAL", "Ingen klar retning.", "#888"

async def get_oi_history_map(session, symbol, period, limit):
    oi_period = period
    req_limit = limit
    # Binance limitations mapping
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
            if interval == '15m': label = dt_obj.strftime("%H:%M")
            elif interval == '1h': label = dt_obj.strftime("%H:00")
            elif interval == '1d': label = dt_obj.strftime("%Y-%m-%d")
            elif interval == '1w': label = f"Uke {dt_obj.strftime('%W')}"
            elif interval == '1M': label = dt_obj.strftime("%B %Y")
            else: label = str(ts)

            sig_head, sig_desc, sig_col = get_signal(price_ch, cvd, oi_ch_percent)
            
            processed_rows.append({
                "label": label, "price_ch": price_ch, "cvd": cvd,
                "oi": oi_val, "oi_ch": oi_ch_percent,
                "s_head": sig_head, "s_desc": sig_desc, "color": sig_col
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
            <td style="padding: 8px; color: #aaa; font-size: 0.9em; white-space: nowrap;">{r['label']}</td>
            <td style="padding: 8px; color: {p_col}; font-weight: bold;">{r['price_ch']:+.2f}%</td>
            <td style="padding: 8px; color: {cvd_col}; font-family: monospace;">{cvd_fmt}</td>
            <td style="padding: 8px; font-family: monospace;">
                <span style="color: #eee;">{oi_fmt}</span> 
                <span style="color: {oi_col}; font-size: 0.8em;">{oi_ch_fmt}</span>
            </td>
            <td style="padding: 8px;">
                <div style="color: {r['color']}; font-weight: bold; font-size: 0.8em; text-transform: uppercase;">{r['s_head']}</div>
                <div style="color: #888; font-size: 0.7em;">{r['s_desc']}</div>
            </td>
        </tr>
        """
    return html

def generate_html_page(symbol, monthly, weekly, daily, hourly, min15):
    return f"""
    <div class="coin-container" style="margin-bottom: 60px; background: #111; padding: 20px; border-radius: 8px; border: 1px solid #333;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 2em;">{symbol.replace('USDT','')} Analysis</h1>
            <div style="font-size: 0.8em; color: #666;">v7.12 Data Beast</div>
        </div>
        <style>table  width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 30px;  th  text-align: left; padding: 8px; border-bottom: 2px solid #444; color: #aaa; text-transform: uppercase; font-size: 0.7em; </style>
        
        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⚡ Siste 4 Timer (15-min Sniper)</h3>
        <table><tr><th width="10%">Tid</th><th width="10%">Pris %</th><th width="15%">Spot CVD</th><th width="20%">Open Interest</th><th width="45%">Analyse</th></tr>{render_table_rows(min15)}</table>

        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⏱️ Siste 24 Timer (Hourly)</h3>
        <table><tr><th>Tid</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Analyse</th></tr>{render_table_rows(hourly)}</table>

        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">📅 Siste 14 Dager (Daily)</h3>
        <table><tr><th>Dato</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Analyse</th></tr>{render_table_rows(daily)}</table>

        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">📆 Siste 24 Uker (6 mnd Weekly)</h3>
        <table><tr><th>Uke</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Analyse</th></tr>{render_table_rows(weekly)}</table>

        <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">🌕 Siste 6 Måneder (Monthly)</h3>
        <table><tr><th>Måned</th><th>Pris %</th><th>Spot CVD</th><th>Open Interest</th><th>Analyse</th></tr>{render_table_rows(monthly)}</table>
    </div>
    """

BASE_HTML = """<html><head><title>Mode 7: Data Beast</title><style>body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #050505; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }</style></head><body>"""

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
    # 1. Monthly (6 mnd)
    t_mon = get_kline_analysis(session, sym, "1M", 6)
    # 2. Weekly (24 uker ~ 6 mnd)
    t_wek = get_kline_analysis(session, sym, "1w", 24)
    # 3. Daily (14 dager)
    t_day = get_kline_analysis(session, sym, "1d", 14)
    # 4. Hourly (24 timer)
    t_hor = get_kline_analysis(session, sym, "1h", 24)
    # 5. 15-Min (16 perioder = 4 timer)
    t_min15 = get_kline_analysis(session, sym, "15m", 16)
    
    mon, wek, day, hor, min15 = await asyncio.gather(t_mon, t_wek, t_day, t_hor, t_min15)
    return generate_html_page(sym, mon, wek, day, hor, min15)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
