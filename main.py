from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v6.2 - Full Spectrum", version="6.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL = "https://api.binance.com/api/v3/klines"

async def fetch_candles(session, symbol, interval, limit):
    """Henter candles med pris og volum data."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        async with session.get(BASE_URL, params=params, timeout=10) as resp:
            if resp.status != 200: return []
            data = await resp.json()
            processed = []
            for k in data:
                close_price = float(k[4])
                total_vol = float(k[7]) # Quote volume
                buy_vol = float(k[10])  # Taker buy quote
                sell_vol = total_vol - buy_vol
                net_flow = buy_vol - sell_vol
                processed.append({
                    "time": k[0], 
                    "price": close_price,
                    "net_flow": net_flow
                })
            return processed
    except: return []

def analyze_rhythm(usdt_data, usdc_data, weeks=12):
    """Analyserer uke-for-uke rytme for USDT, USDC og NET."""
    if not usdt_data: return []
    
    rhythm = []
    chunk_size = 42 # Ca 1 uke med 4h candles
    
    recent_usdt = usdt_data[-(weeks*chunk_size):]
    recent_usdc = usdc_data[-(weeks*chunk_size):] if usdc_data else []
    
    usdt_chunks = [recent_usdt[i:i + chunk_size] for i in range(0, len(recent_usdt), chunk_size)]
    
    for i, chunk in enumerate(usdt_chunks):
        if not chunk: continue
        
        start_price = chunk[0]['price']
        end_price = chunk[-1]['price']
        price_change_pct = ((end_price - start_price) / start_price) * 100
        
        flow_usdt = sum(d['net_flow'] for d in chunk)
        
        flow_usdc = 0
        if recent_usdc:
            start_idx = i * chunk_size
            end_idx = start_idx + len(chunk)
            if start_idx < len(recent_usdc):
                usdc_chunk = recent_usdc[start_idx:end_idx]
                flow_usdc = sum(d['net_flow'] for d in usdc_chunk)
        
        flow_net = flow_usdt + flow_usdc
        
        # Phase Detection Logic (Basert på NET flow)
        phase = "Neutral"
        phase_color = "gray"
        
        if flow_net > 0 and price_change_pct < -2:
            phase = "🦅 ABSORPTION"
            phase_color = "#1b5e20" # Dark Green
        elif flow_net > 0 and price_change_pct > 0:
            phase = "🚀 MARKUP"
            phase_color = "#4caf50" # Green
        elif flow_net < 0 and price_change_pct > 2:
            phase = "⚠️ DISTRIBUTION"
            phase_color = "#b71c1c" # Dark Red
        elif flow_net < 0 and price_change_pct < 0:
            phase = "🩸 CAPITULATION" 
            phase_color = "#f44336" # Red
        elif flow_net > 0:
             phase = "🌱 ACCUMULATION"
             phase_color = "#81c784"
            
        rhythm.append({
            "week_num": i + 1 - len(usdt_chunks),
            "usdt": flow_usdt,
            "usdc": flow_usdc,
            "net": flow_net,
            "price_change": price_change_pct,
            "phase": phase,
            "color": phase_color
        })
        
    return rhythm

def detect_signal(rhythm):
    if len(rhythm) < 4: return "Waiting for data..."
    recent = rhythm[-4:]
    
    for w in recent:
        if "ABSORPTION" in w['phase']:
            return "🔥 STRONG BUY: Absorption Detected (Whales Buying Dips)"
        if "DISTRIBUTION" in w['phase']:
            return "🛑 WARNING: Distribution Detected (Whales Selling Rips)"
            
    cum_net = sum(w['net'] for w in recent)
    if cum_net > 0: return "✅ BULLISH FLOW: Net Buying Last 30 Days"
    return "❌ BEARISH FLOW: Net Selling Last 30 Days"

async def analyze_market(ticker):
    async with aiohttp.ClientSession() as session:
        usdt_task = fetch_candles(session, f"{ticker}USDT", "4h", 600)
        usdc_task = fetch_candles(session, f"{ticker}USDC", "4h", 600)
        res = await asyncio.gather(usdt_task, usdc_task)
        
    rhythm = analyze_rhythm(res[0], res[1])
    signal = detect_signal(rhythm)
    
    return {"ticker": ticker, "rhythm": rhythm, "signal": signal}

@app.get("/html/{ticker}", response_class=HTMLResponse)
async def get_dashboard(ticker: str):
    data = await analyze_market(ticker.upper())
    r = data["rhythm"]
    
    def fmt(val):
        color = "green" if val > 0 else "red"
        return f"<span style='color:{color};'>${val/1_000_000:.1f}M</span>"
    
    rows = ""
    for w in reversed(r):
        week_label = "Current Week" if w['week_num'] == 0 else f"{abs(w['week_num'])} weeks ago"
        p_col = "green" if w['price_change'] > 0 else "red"
        
        rows += f"""
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px; color:#666;">{week_label}</td>
            <td style="padding:10px; font-weight:bold; color:{w['color']};">{w['phase']}</td>
            <td style="padding:10px;">{fmt(w['usdt'])}</td>
            <td style="padding:10px;">{fmt(w['usdc'])}</td>
            <td style="padding:10px; font-weight:bold;">{fmt(w['net'])}</td>
            <td style="padding:10px; color:{p_col};">{w['price_change']:.1f}%</td>
        </tr>
        """

    html = f"""
    <html><body style="font-family: sans-serif; background: #f0f2f5; padding: 20px;">
        <div style="background: white; padding: 25px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); max-width: 800px; margin: auto;">
            <div style="text-align:center; margin-bottom:20px;">
                <h1 style="margin:0; font-size:24px;">🐋 {data['ticker']} Full Spectrum</h1>
                <p style="color:#888; margin:5px 0;">USDT + USDC + Net Flow Analysis • 90 Days</p>
                <div style="background:#e3f2fd; color:#1565c0; padding:10px; border-radius:8px; display:inline-block; margin-top:10px; font-weight:bold;">
                    {data['signal']}
                </div>
            </div>
            <table style="width:100%; border-collapse: collapse; font-size:13px;">
                <tr style="background:#fafafa; text-align:left; color:#888;">
                    <th style="padding:10px;">Periode</th>
                    <th style="padding:10px;">Phase</th>
                    <th style="padding:10px;">USDT (Retail)</th>
                    <th style="padding:10px;">USDC (Whale)</th>
                    <th style="padding:10px;">NET (Total)</th>
                    <th style="padding:10px;">Price</th>
                </tr>
                {rows}
            </table>
        </div>
    </body></html>
    """
    return html
