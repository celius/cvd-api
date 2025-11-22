from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
import pandas as pd
from datetime import datetime, timezone

app = FastAPI(title="CVD API v8.1 - Multi-Timeframe", version="8.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- CONFIG ---
DOMAIN_SPOT = "https://api.binance.com"
DOMAIN_FUTURES = "https://fapi.binance.com"

# --- HJELPEFUNKSJONER ---

async def fetch_url(session, url, params=None):
    try:
        async with session.get(url, params=params) as response:
            if response.status != 200: return None
            return await response.json()
    except: return None

def format_number(num):
    if abs(num) >= 1_000_000_000: return f"{num / 1_000_000_000:.2f}B"
    if abs(num) >= 1_000_000: return f"{num / 1_000_000:.2f}M"
    if abs(num) >= 1_000: return f"{num / 1_000:.2f}k"
    return f"{num:.2f}"

def get_css():
    return '''
    body { font-family: sans-serif; background: #191919; color: #e0e0e0; padding: 20px; }
    h2, h3 { border-bottom: 1px solid #333; padding-bottom: 5px; margin-top: 30px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.9em; }
    th { text-align: left; color: #888; border-bottom: 1px solid #444; padding: 5px; }
    td { padding: 5px; border-bottom: 1px solid #2a2a2a; }
    .bull { color: #4caf50; }
    .bear { color: #ff5252; }
    .card { background: #252525; padding: 15px; border-radius: 8px; border: 1px solid #333; }
    .row-bull { background: rgba(76, 175, 80, 0.05); }
    .row-bear { background: rgba(255, 82, 82, 0.05); }
    '''

def interpret_sentiment(g_ratio, t_pos):
    signals = []
    if g_ratio > 1.5: signals.append("Retail: FOMO Longs")
    elif g_ratio < 0.6: signals.append("Retail: Panikk Shorts")
    
    if g_ratio > 1.2 and t_pos < 0.9: signals.append("⚠️ DIVERGENS: Retail kjøper, Whales selger")
    elif g_ratio < 0.8 and t_pos > 1.1: signals.append("💎 DIVERGENS: Retail selger, Whales kjøper")
    
    return " + ".join(signals) if signals else "Nøytralt / Ingen ekstrem divergens"

def process_klines(klines, interval_name):
    if not klines: return pd.DataFrame()
    # Binance Kline: 0=Time, 1=Open, 4=Close, 5=Vol, 9=TakerBuyBaseVol
    df = pd.DataFrame(klines, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CloseTime', 'QuoteVol', 'Trades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'])
    df['Time'] = pd.to_datetime(df['Time'], unit='ms')
    df['Close'] = df['Close'].astype(float)
    df['Vol'] = df['Vol'].astype(float) # Total Volume
    df['TakerBuyBase'] = df['TakerBuyBase'].astype(float) # Buy Volume
    
    # CVD Calculation: Buy - (Total - Buy) = Buy - Sell
    df['SellVol'] = df['Vol'] - df['TakerBuyBase']
    df['CVD'] = df['TakerBuyBase'] - df['SellVol']
    
    return df[['Time', 'Close', 'CVD']]

def render_table(df, title, time_format='%H:%M'):
    if df.empty: return f"<h3>{title}</h3><p>Ingen data.</p>"
    
    html = f"<h3>{title}</h3><table><tr><th>Tid</th><th>Pris</th><th>Net CVD</th><th>Signal</th></tr>"
    # Snu rekkefølge slik at nyeste er øverst
    for _, row in df.sort_values('Time', ascending=False).iterrows():
        time_str = row['Time'].strftime(time_format)
        cvd_val = row['CVD']
        price = row['Close']
        
        cls = "row-bull" if cvd_val > 0 else "row-bear"
        sig = "🟢 Kjøp" if cvd_val > 0 else "🔴 Salg"
        val_str = f"{'+' if cvd_val > 0 else ''}{format_number(cvd_val)}"
        
        html += f'<tr class="{cls}"><td>{time_str}</td><td>${price:.4f}</td><td class="{cls}">{val_str}</td><td>{sig}</td></tr>'
    html += "</table>"
    return html

# --- ENDPOINTS ---

@app.get("/html/{ticker}")
async def get_analysis(ticker: str):
    symbol = ticker.upper() + "USDT"
    async with aiohttp.ClientSession() as session:
        # 1. SENTIMENT (X-RAY)
        s_params = {"symbol": symbol, "period": "15m", "limit": 1}
        t_g = fetch_url(session, f"{DOMAIN_FUTURES}/futures/data/globalLongShortAccountRatio", s_params)
        t_p = fetch_url(session, f"{DOMAIN_FUTURES}/futures/data/topLongShortPositionRatio", s_params)
        
        # 2. KLINES FOR TIME TABLES
        # 15m (Siste 4 timer = 16 candles)
        t_15m = fetch_url(session, f"{DOMAIN_SPOT}/api/v3/klines", {"symbol": symbol, "interval": "15m", "limit": 16})
        # 1h (Siste 24 timer = 24 candles)
        t_1h = fetch_url(session, f"{DOMAIN_SPOT}/api/v3/klines", {"symbol": symbol, "interval": "1h", "limit": 24})
        # 1d (Siste 180 dager)
        t_1d = fetch_url(session, f"{DOMAIN_SPOT}/api/v3/klines", {"symbol": symbol, "interval": "1d", "limit": 180})
        
        res = await asyncio.gather(t_g, t_p, t_15m, t_1h, t_1d)
        g_data, p_data, k_15m, k_1h, k_1d = res

        # --- PROSESSERING ---
        
        # Sentiment
        g_val = float(g_data[0]['longShortRatio']) if g_data else 1.0
        p_val = float(p_data[0]['longShortRatio']) if p_data else 1.0
        sentiment_txt = interpret_sentiment(g_val, p_val)
        
        # DataFrames
        df_15m = process_klines(k_15m, '15m')
        df_1h = process_klines(k_1h, '1h')
        df_1d = process_klines(k_1d, '1d')
        
        # Aggregations
        # Siste 14 dager
        df_last14 = df_1d.tail(14).copy()
        
        # Weekly (Resample 180 days)
        df_weekly = df_1d.set_index('Time').resample('W-MON').agg({'Close': 'last', 'CVD': 'sum'}).reset_index()
        
        # Monthly
        df_monthly = df_1d.set_index('Time').resample('ME').agg({'Close': 'last', 'CVD': 'sum'}).reset_index()

        # --- HTML GENERATION ---
        html = f'''
        <html><head><style>{get_css()}</style></head><body>
            <h2>🔭 Mode 7: {symbol} (v8.1 Full Report)</h2>
            
            <div class="card">
                <div style="font-size: 1.1em; color: #ffd700; margin-bottom: 10px;">{sentiment_txt}</div>
                <div>Retail L/S: <b class="{ 'bull' if g_val > 1 else 'bear' }">{g_val}</b> | 
                     Whale Pos: <b class="{ 'bull' if p_val > 1 else 'bear' }">{p_val}</b></div>
            </div>

            {render_table(df_15m, "⚡ Siste 4 Timer (15m)", "%H:%M")}
            {render_table(df_1h, "🕐 Siste Døgn (1h)", "%H:%M")}
            {render_table(df_last14, "📅 Siste 14 Dager (Daily)", "%d-%m")}
            {render_table(df_weekly.tail(26), "🗓️ Ukentlig (Siste 6 mnd)", "Uke %W")}
            {render_table(df_monthly.tail(6), "🌙 Månedlig (Siste 6 mnd)", "%B %Y")}
            
            <p style="color: #555; font-size: 0.8em;">Generated by Mode 7 v8.1</p>
        </body></html>
        '''
        return HTMLResponse(content=html)

@app.get("/")
def read_root():
    return {"Status": "Online", "Version": "v8.1"}
