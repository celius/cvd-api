from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timezone

app = FastAPI(title="CVD API v8.1 - Whale vs Retail (Improved)", version="8.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

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

# --- WHALE & RETAIL ANALYSIS ENGINE (v8.1 IMPROVED) ---
def get_signal(price_ch, cvd_val, whale_ls, retail_ls):
    """
    v8.1 IMPROVED LOGIC:
    - Fix 1: Ekstrem Retail FOMO detection (>3.0 threshold)
    - Fix 2: Parabolic move detection (>20%)
    - Bevarer HTML/CSS presentasjon
    """
    
    # Default
    head = "⚖️ NØYTRAL"; desc = "Ingen klare avvik."; col = "#888"
    
    # EDGE CASE: Parabolic moves (Fix 2)
    if abs(price_ch) > 20:
        if price_ch > 0:
            head = "🚀 PARABOLIC PUMP"
            desc = "Ekstrem oppgang (+20%+) - Ofte FOMO-topp, vurder take profit."
            col = "#ff00ff"
        else:
            head = "💥 PARABOLIC DUMP"
            desc = "Ekstrem nedgang (-20%+) - Ekstremt salgspress, vurder capitulation-kjøp."
            col = "#8B0000"
        return head, desc, col
    
    # PRIORITY 1: Ekstrem Retail FOMO (Fix 1 - ny threshold 3.0)
    if retail_ls > 3.0:
        if cvd_val < -50_000_000:  # Fake pump intensity
            head = "🚨 FAKE PUMP + RETAIL FOMO PEAK"
            desc = f"Retail ekstremt FOMO (L/S {retail_ls:.2f}), men Spot CVD svært negativ. Advarsel-topp!"
            col = "#ff0000"
        elif cvd_val < 0:
            head = "🚨 RETAIL FOMO PEAK"
            desc = f"Retail ekstremt overleveraged Long (L/S {retail_ls:.2f}) + Spot CVD negativ. Sannsynlig topp."
            col = "#ff4d4d"
        else:
            head = "⚠️ RETAIL FOMO EKSTREMT"
            desc = f"Retail L/S {retail_ls:.2f} (>3.0) - Vær varsom, crowd er overleveraged Long."
            col = "#ffa500"
        return head, desc, col
    
    # PRIORITY 2: Retail FOMO warning (2.0-3.0 range)
    if retail_ls > 2.0:
        if cvd_val < 0:
            head = "⚠️ RETAIL FOMO + CVD NEGATIV"
            desc = f"Retail overleveraged (L/S {retail_ls:.2f}), Spot CVD negativ - Mulig topp."
            col = "#ff6b6b"
        else:
            head = "⚠️ RETAIL FOMO"
            desc = f"Retail L/S {retail_ls:.2f} - Crowd er overleveraged, vær forsiktig."
            col = "#ffa500"
        return head, desc, col
    
    # PRIORITY 3: WHALE DIVERGENCE (Most Powerful)
    # Scenario 1: Whale Accumulation
    if price_ch < -0.5 and whale_ls > 1.2:
        head = "🐋 WHALE ACCUMULATION"
        desc = "Pris faller, men Whales laster opp Longs. Bullish divergens."
        col = "#00ccff"
        if cvd_val > 0:
            desc += " Spot CVD positiv (sterk)."
            col = "#00ff9d"  # Super Bullish
        else:
            desc += " Men Spot CVD negativ (svekkelse, vær forsiktig)."
            col = "#0099ff"
        if retail_ls < 0.8:
            desc += " Retail har panikk (Capitulation)."
            col = "#00ff9d"  # Super Bullish
        return head, desc, col
    
    # Scenario 2: Whale Distribution
    elif price_ch > 0.5 and whale_ls < 0.8:
        head = "🐋 WHALE DISTRIBUTION"
        desc = "Pris stiger, men Whales shorter. Bearish divergens."
        col = "#ff4d4d"
        if cvd_val < 0:
            desc += " Spot CVD negativ (sterk)."
            col = "#ff0000"  # Super Bearish
        else:
            desc += " Men Spot CVD positiv (motsetning)."
            col = "#ff6b6b"
        if retail_ls > 2.0:
            desc += " Retail fomo-kjøper toppen."
            col = "#ff0000"  # Super Bearish
        return head, desc, col
    
    # PRIORITY 4: RETAIL CONTRARIAN
    # Retail Capitulation
    if retail_ls < 0.8 and price_ch < -0.5:
        if cvd_val > 0:
            head = "✅ RETAIL CAPITULATION + SPOT SUPPORT"
            desc = f"Retail panikk (L/S {retail_ls:.2f}), men Spot CVD positiv - Mulig bunn."
            col = "#00ff9d"
        else:
            head = "⚠️ RETAIL CAPITULATION"
            desc = f"Retail panikk (L/S {retail_ls:.2f}), men Spot CVD negativ - Fortsatt salgspress."
            col = "#ffa500"
        return head, desc, col
    
    # PRIORITY 5: SPOT CVD CONFIRMATION (Hvis ingen stor whale/retail divergens)
    if price_ch > 2.0 and cvd_val > 50_000_000:
        head = "✅ SPOT DRIVER"
        desc = "Sterk oppgang med stor Spot CVD - Sunn trend."
        col = "#00ff9d"
        return head, desc, col
    
    if price_ch < -2.0 and cvd_val < -50_000_000:
        head = "❌ SPOT DUMP"
        desc = "Sterk nedgang med stor Spot CVD utstrømming."
        col = "#ff4d4d"
        return head, desc, col
    
    # Spot absorption (reversal setup)
    if price_ch < -1.0 and cvd_val > 10_000_000:
        head = "🛡️ SPOT ABSORBERING"
        desc = "Pris ned men CVD opp - Mulig reversal."
        col = "#0099ff"
        return head, desc, col
    
    if price_ch > 1.0 and cvd_val < -10_000_000:
        head = "⚠️ SVAK OPPGANG"
        desc = "Pris opp men CVD negativ - Mangler kjøpere, mulig felle."
        col = "#ffa500"
        return head, desc, col
    
    # Standard classifications for moderate moves
    if price_ch > 0.5:
        if cvd_val > 0:
            head = "🚀 SUNN OPPGANG"
            desc = "Pris opp støttet av Spot-kjøp."
            col = "#00ff9d"
        else:
            head = "⚠️ SVAK OPPGANG"
            desc = "Pris opp, men Spot selger (mulig felle)."
            col = "#ffa500"
        return head, desc, col
    
    if price_ch < -0.5:
        if cvd_val > 0:
            head = "🛡️ SPOT ABSORBERING"
            desc = "Pris ned, men Spot kjøper imot."
            col = "#0099ff"
        else:
            head = "📉 AGGRESSIVT SALG"
            desc = "Pris ned støttet av Spot-salg."
            col = "#ffcccc"
        return head, desc, col
    
    # NEUTRAL: Ingen klare signaler
    return head, desc, col

async def get_sentiment_history(session, symbol, period, limit, endpoint):
    # Mapping limits
    req_limit = limit
    if period == '1w': period = '1d'; req_limit = limit * 7
    if period == '1M': period = '1d'; req_limit = limit * 30
    if req_limit > 499: req_limit = 499
    
    url = f"{DOMAIN_FUTURES}/futures/data/{endpoint}?symbol={symbol}&period={period}&limit={req_limit}"
    data = await fetch_url(session, url)
    
    res_map = {}
    if data:
        for item in data:
            val = float(item['longShortRatio'])
            res_map[int(item['timestamp'])] = val
    return res_map

def get_closest(ts, data_map):
    if not data_map: return 0.0
    if ts in data_map: return data_map[ts]
    keys = list(data_map.keys())
    if not keys: return 0.0
    closest_ts = min(keys, key=lambda k: abs(k - ts))
    return data_map[closest_ts]

async def get_kline_analysis(session, symbol, interval, limit):
    # 1. Spot Price & CVD
    kline_url = f"{DOMAIN_SPOT}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    klines = await fetch_url(session, kline_url)
    
    # 2. Whale Sentiment (Top Trader Positions)
    whale_task = get_sentiment_history(session, symbol, interval, limit, "topLongShortPositionRatio")
    # 3. Retail Sentiment (Global Accounts)
    retail_task = get_sentiment_history(session, symbol, interval, limit, "globalLongShortAccountRatio")
    
    whale_map, retail_map = await asyncio.gather(whale_task, retail_task)
    
    rows = []
    if klines:
        for k in klines:
            ts = int(k[0])
            dt_obj = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            
            open_p = float(k[1]); close_p = float(k[4])
            buy_vol = float(k[10]); sell_vol = float(k[7]) - buy_vol
            
            price_ch = ((close_p - open_p) / open_p) * 100
            cvd = buy_vol - sell_vol
            
            # Sentiment Lookup
            w_ls = get_closest(ts, whale_map)
            r_ls = get_closest(ts, retail_map)
            
            # Labels
            if interval == '15m': label = dt_obj.strftime("%d/%m %H:%M")
            elif interval == '1h': label = dt_obj.strftime("%d/%m %H:00")
            elif interval == '1d': label = dt_obj.strftime("%Y-%m-%d")
            elif interval == '1w': label = f"Uke {dt_obj.strftime('%W')}"
            elif interval == '1M': label = dt_obj.strftime("%B")
            else: label = str(ts)
            
            head, desc, col = get_signal(price_ch, cvd, w_ls, r_ls)
            
            rows.append({
                "label": label, "price_ch": price_ch, "cvd": cvd,
                "w_ls": w_ls, "r_ls": r_ls,
                "head": head, "desc": desc, "col": col
            })
    
    return list(reversed(rows))

def render_table_rows(rows):
    html = ""
    for r in rows:
        p_col = "#00ff9d" if r['price_ch'] >= 0 else "#ff4d4d"
        
        if abs(r['cvd']) > 1_000_000: cvd_fmt = f"${r['cvd']/1_000_000:+.1f}M"
        else: cvd_fmt = f"${r['cvd']/1_000:+.0f}k"
        cvd_col = "#00ff9d" if r['cvd'] >= 0 else "#ff4d4d"
        
        # Whale Color: Green if Long Bias (>1.2), Red if Short Bias (<0.8)
        w_col = "#00ff9d" if r['w_ls'] > 1.2 else ("#ff4d4d" if r['w_ls'] < 0.8 else "#aaa")
        
        # Retail Color: Red if overly Long (>2.0 - contrarian), Green if Fearful (<0.8)
        r_col = "#ff4d4d" if r['r_ls'] > 2.0 else ("#00ff9d" if r['r_ls'] < 0.8 else "#aaa")
        
        html += f"""
        <tr style="border-bottom: 1px solid #222;">
        <td style="padding: 8px; color: #aaa; font-size: 0.9em; white-space: nowrap;">{r['label']}</td>
        <td style="padding: 8px; color: {p_col}; font-weight: bold;">{r['price_ch']:+.2f}%</td>
        <td style="padding: 8px; color: {cvd_col}; font-family: monospace;">{cvd_fmt}</td>
        <td style="padding: 8px; color: {w_col}; font-weight: bold;">{r['w_ls']:.2f}</td>
        <td style="padding: 8px; color: {r_col};">{r['r_ls']:.2f}</td>
        <td style="padding: 8px;">
        <div style="color: {r['col']}; font-weight: bold; font-size: 0.8em;">{r['head']}</div>
        <div style="color: #666; font-size: 0.7em;">{r['desc']}</div>
        </td>
        </tr>
        """
    return html

def generate_html_page(symbol, monthly, weekly, daily, hourly, min15):
    return f"""
    <div class="coin-container" style="margin-bottom: 60px; background: #111; padding: 20px; border-radius: 8px; border: 1px solid #333;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 20px;">
    <h1 style="margin: 0; font-size: 2em;">{symbol.replace('USDT','')} Analysis</h1>
    <div style="font-size: 0.8em; color: #666;">v8.1 Extended</div>
    </div>
    <style>
    table  width: 100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 30px; 
    th  text-align: left; padding: 8px; border-bottom: 2px solid #444; color: #aaa; text-transform: uppercase; font-size: 0.7em; 
    </style>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⚡ Siste 48 Timer - Kvarter (Sniper)</h3>
    <table><tr><th width="10%">Tid</th><th width="10%">Pris %</th><th width="15%">Spot CVD</th><th width="10%">🐋 Whale L/S</th><th width="10%">🐟 Retail L/S</th><th width="45%">Mode 7 Analyse</th></tr>{render_table_rows(min15)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">⏱️ Siste 7 Dager - Time (Hourly)</h3>
    <table><tr><th>Tid</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(hourly)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">📅 Siste 30 Dager - Dag (Daily)</h3>
    <table><tr><th>Dato</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(daily)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">📆 Siste 24 Uker (Weekly)</h3>
    <table><tr><th>Uke</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(weekly)}</table>
    
    <h3 style="color: #00ccff; border-bottom: 1px solid #00ccff; padding-bottom: 5px;">🌕 Siste 6 Måneder (Monthly)</h3>
    <table><tr><th>Måned</th><th>Pris %</th><th>Spot CVD</th><th>🐋 Whale</th><th>🐟 Retail</th><th>Analyse</th></tr>{render_table_rows(monthly)}</table>
    </div>
    """

BASE_HTML = """<html><head><title>Mode 7: Whale Watch</title><style>body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #050505; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }</style></head><body>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_coin_data(session, sym) for sym in symbols]
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
    # 2. Weekly (24 uker)
    t_wek = get_kline_analysis(session, sym, "1w", 24)
    # 3. Daily (30 dager)
    t_day = get_kline_analysis(session, sym, "1d", 30)
    # 4. Hourly (168 timer = 7 dager)
    t_hor = get_kline_analysis(session, sym, "1h", 168)
    # 5. 15-Min (192 intervaller = 48 timer)
    t_min15 = get_kline_analysis(session, sym, "15m", 192)
    
    mon, wek, day, hor, min15 = await asyncio.gather(t_mon, t_wek, t_day, t_hor, t_min15)
    return generate_html_page(sym, mon, wek, day, hor, min15)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
