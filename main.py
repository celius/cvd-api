from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v7.0 - Smart Money Triad", version="7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL_SPOT = "https://api.binance.com/api/v3/klines"
BASE_URL_FUTURES = "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"

async def fetch_spot_candles(session, symbol, interval, limit):
    """Henter Spot data (Pris + Net Flow)."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        async with session.get(f"{BASE_URL_SPOT}/api/v3/klines", params=params, timeout=10) as resp:
            if resp.status != 200: return []
            data = await resp.json()
            processed = []
            for k in data:
                total_vol = float(k[7])
                buy_vol = float(k[10])
                net_flow = buy_vol - (total_vol - buy_vol)
                processed.append({"time": k[0], "price": float(k[4]), "spot_cvd": net_flow})
            return processed
    except: return []

async def fetch_futures_oi(session, symbol, period, limit):
    """Henter Open Interest Historikk."""
    params = {"symbol": symbol, "period": period, "limit": limit}
    try:
        async with session.get(f"{BASE_URL_FUTURES}/fapi/v1/openInterestHist", params=params, timeout=10) as resp:
            if resp.status != 200: return []
            data = await resp.json()
            return [{"time": d["timestamp"], "oi": float(d["sumOpenInterestValue"])} for d in data]
    except: return []

async def fetch_funding(session, symbol):
    """Henter nåværende funding rate."""
    try:
        async with session.get(f"{BASE_URL_FUTURES}/fapi/v1/premiumIndex", params={"symbol": symbol}, timeout=10) as resp:
            if resp.status != 200: return 0
            data = await resp.json()
            return float(data["lastFundingRate"])
    except: return 0

def analyze_period(spot_data, oi_data, chunk_size, label_func):
    """Grupperer data i perioder (Uker/Dager/Timer) og analyserer Triad."""
    if not spot_data: return []
    
    # Synkroniser lengder (bruk korteste)
    min_len = min(len(spot_data), len(oi_data))
    spot_data = spot_data[-min_len:]
    oi_data = oi_data[-min_len:]
    
    chunks = [spot_data[i:i + chunk_size] for i in range(0, len(spot_data), chunk_size)]
    oi_chunks = [oi_data[i:i + chunk_size] for i in range(0, len(oi_data), chunk_size)]
    
    analysis = []
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        
        # Spot Data
        start_price = chunk[0]['price']
        end_price = chunk[-1]['price']
        price_change = ((end_price - start_price) / start_price) * 100
        net_cvd = sum(d['spot_cvd'] for d in chunk)
        
        # OI Data
        start_oi = oi_chunks[i][0]['oi'] if i < len(oi_chunks) and oi_chunks[i] else 0
        end_oi = oi_chunks[i][-1]['oi'] if i < len(oi_chunks) and oi_chunks[i] else 0
        oi_change = ((end_oi - start_oi) / start_oi) * 100 if start_oi else 0
        
        # Signal Logic (Triad)
        signal = "Neutral"
        color = "gray"
        
        # 1. Squeeze Setup (Pris opp + CVD opp + OI opp)
        if price_change > 0 and net_cvd > 0 and oi_change > 0:
            signal = "🚀 STRONG TREND"
            color = "#4caf50"
        # 2. Absorption (Pris ned + CVD opp)
        elif price_change < 0 and net_cvd > 0:
            signal = "🦅 ABSORPTION (Buy Dip)"
            color = "#1b5e20"
        # 3. Fake Pump (Pris opp + CVD ned + OI opp) -> Leverage driven
        elif price_change > 0 and net_cvd < 0 and oi_change > 0:
            signal = "⚠️ FAKE PUMP (Trap)"
            color = "#ff9800"
        # 4. Capitulation (Pris ned + CVD ned + OI ned) -> Longs puking
        elif price_change < 0 and net_cvd < 0 and oi_change < 0:
            signal = "🩸 CAPITULATION (Flush)"
            color = "#f44336"
            
        analysis.append({
            "label": label_func(i, len(chunks)),
            "price_change": price_change,
            "cvd": net_cvd,
            "oi_change": oi_change,
            "signal": signal,
            "color": color
        })
        
    return list(reversed(analysis))

async def analyze_market(ticker):
    async with aiohttp.ClientSession() as session:
        # 1. Fetch Macro Data (90 dager -> 4h candles)
        # 90 dager * 6 candles/dag = 540 candles
        spot_4h_task = fetch_spot_candles(session, f"{ticker}USDT", "4h", 600)
        oi_4h_task = fetch_futures_oi(session, f"{ticker}USDT", "4h", 600)
        
        # 2. Fetch Micro Data (7 dager -> 1h candles)
        # 7 dager * 24 candles/dag = 168 candles
        spot_1h_task = fetch_spot_candles(session, f"{ticker}USDT", "1h", 200)
        oi_1h_task = fetch_futures_oi(session, f"{ticker}USDT", "1h", 200)
        
        funding_task = fetch_funding(session, f"{ticker}USDT")
        
        results = await asyncio.gather(spot_4h_task, oi_4h_task, spot_1h_task, oi_1h_task, funding_task)
        
    spot_4h, oi_4h, spot_1h, oi_1h, funding = results
    
    # --- ANALYSE 1: Macro Rhythm (90 Dager -> Uker) ---
    # 4h candles per uke = 6 * 7 = 42
    macro_rhythm = analyze_period(spot_4h, oi_4h, 42, lambda i, n: f"{n-i-1} weeks ago" if n-i-1 > 0 else "Current Week")
    
    # --- ANALYSE 2: Swing Rhythm (7 Dager -> Dager) ---
    # 1h candles per dag = 24
    swing_rhythm = analyze_period(spot_1h, oi_1h, 24, lambda i, n: f"{n-i-1} days ago" if n-i-1 > 0 else "Last 24h")
    
    # --- ANALYSE 3: Sniper Rhythm (24 Timer -> Timer) ---
    # 1h candles per time = 1. Vi tar de siste 24 av spot_1h.
    sniper_rhythm = analyze_period(spot_1h[-24:], oi_1h[-24:], 1, lambda i, n: f"{n-i-1}h ago" if n-i-1 > 0 else "Now")
    
    return {
        "ticker": ticker, 
        "macro": macro_rhythm[:12], # Siste 12 uker
        "swing": swing_rhythm,      # Siste 7 dager
        "sniper": sniper_rhythm,    # Siste 24 timer
        "funding": funding
    }

@app.get("/html/{ticker}", response_class=HTMLResponse)
async def get_dashboard(ticker: str):
    data = await analyze_market(ticker.upper())
    
    def render_table(title, rows):
        html = f"""
        <div style="margin-bottom:30px;">
            <h3 style="margin:0 0 10px 0; color:#444; border-bottom:2px solid #eee; padding-bottom:5px;">{title}</h3>
            <table style="width:100%; border-collapse: collapse; font-size:13px;">
                <tr style="background:#fafafa; color:#888; text-align:left;">
                    <th style="padding:8px;">Time</th>
                    <th style="padding:8px;">Signal</th>
                    <th style="padding:8px;">Spot CVD (Demand)</th>
                    <th style="padding:8px;">OI (Fuel)</th>
                    <th style="padding:8px;">Price</th>
                </tr>"""
        
        for r in rows:
            cvd_col = "green" if r['cvd'] > 0 else "red"
            oi_col = "green" if r['oi_change'] > 0 else "red"
            p_col = "green" if r['price_change'] > 0 else "red"
            
            html += f"""
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px; color:#666;">{r['label']}</td>
                <td style="padding:8px; font-weight:bold; color:{r['color']};">{r['signal']}</td>
                <td style="padding:8px; color:{cvd_col};">${r['cvd']/1_000_000:.1f}M</td>
                <td style="padding:8px; color:{oi_col};">{r['oi_change']:.1f}%</td>
                <td style="padding:8px; color:{p_col};">{r['price_change']:.1f}%</td>
            </tr>"""
        
        html += "</table></div>"
        return html

    funding_color = "red" if data['funding'] > 0.01 else "green"
    
    html = f"""
    <html><body style="font-family: sans-serif; background: #f0f2f5; padding: 20px;">
        <div style="background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); max-width: 900px; margin: auto;">
            
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:30px;">
                <div>
                    <h1 style="margin:0; font-size:28px;">🐋 {data['ticker']} Smart Money Triad</h1>
                    <p style="color:#888; margin:5px 0;">Spot CVD • Open Interest • Funding Rate</p>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:12px; color:#888;">Current Funding</div>
                    <div style="font-size:20px; font-weight:bold; color:{funding_color};">{data['funding']:.4f}%</div>
                </div>
            </div>

            {render_table("🦅 Swing Rhythm (Last 7 Days)", data['swing'])}
            {render_table("⚡ Sniper Rhythm (Last 24 Hours)", data['sniper'])}
            {render_table("🐋 Macro Rhythm (Last 12 Weeks)", data['macro'])}
            
            <div style="margin-top:20px; padding:15px; background:#e3f2fd; border-radius:8px; font-size:13px; color:#1565c0;">
                <strong>💡 Pro Tip:</strong> Look for <b>ABSORPTION</b> (Green Signal) in the <i>Sniper Rhythm</i> to time your entry perfectly after a dump.
            </div>
        </div>
    </body></html>
    """
    return html
