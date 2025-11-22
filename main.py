from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone

app = FastAPI(title="CVD API v6.0 - Whale Rhythm", version="6.0")

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
            # Format: [time, open, high, low, close, vol, close_time, quote_vol, trades, taker_buy_base, taker_buy_quote]
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

def analyze_rhythm(data, weeks=12):
    """Analyserer uke-for-uke rytme og markedsfase."""
    if not data: return []
    
    # Grupper data i uker (ca 42 candles av 4h per uke)
    rhythm = []
    chunk_size = 42 
    # Snu listen for å starte med nyeste uke, men vi vil iterere kronologisk for trend
    # Vi tar de siste weeks * chunk_size
    recent_data = data[-(weeks*chunk_size):]
    
    # Del opp i chunks på 42 (1 uke)
    chunks = [recent_data[i:i + chunk_size] for i in range(0, len(recent_data), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        if not chunk: continue
        start_price = chunk[0]['price']
        end_price = chunk[-1]['price']
        price_change_pct = ((end_price - start_price) / start_price) * 100
        
        net_flow = sum(d['net_flow'] for d in chunk)
        
        # Phase Detection Logic
        phase = "Neutral"
        phase_color = "gray"
        
        if net_flow > 0 and price_change_pct < -2:
            phase = "🦅 ABSORPTION (Bullish Div)" # Buying into dump
            phase_color = "#1b5e20" # Dark Green
        elif net_flow > 0 and price_change_pct > 0:
            phase = "🚀 MARKUP (Strong)"
            phase_color = "#4caf50" # Green
        elif net_flow < 0 and price_change_pct > 2:
            phase = "⚠️ DISTRIBUTION (Bearish Div)" # Selling into pump
            phase_color = "#b71c1c" # Dark Red
        elif net_flow < 0 and price_change_pct < 0:
            phase = "🩸 CAPITULATION" 
            phase_color = "#f44336" # Red
        elif net_flow > 0:
             phase = "🌱 ACCUMULATION"
             phase_color = "#81c784"
            
        rhythm.append({
            "week_num": i + 1 - len(chunks), # Relativ uke (0 = current, -1 = last)
            "net_flow": net_flow,
            "price_change": price_change_pct,
            "phase": phase,
            "color": phase_color,
            "price_end": end_price
        })
        
    return rhythm

def detect_divergence(rhythm):
    """Sjekker de siste 4 ukene for divergens."""
    if len(rhythm) < 4: return "Insufficent Data"
    
    recent = rhythm[-4:]
    cumulative_flow = sum(w['net_flow'] for w in recent)
    price_change = sum(w['price_change'] for w in recent)
    
    if cumulative_flow > 0 and price_change < -5:
        return "🔥 MAJOR BULLISH DIVERGENCE (Price Down, Whales Buying)"
    elif cumulative_flow < 0 and price_change > 5:
        return "🚨 MAJOR BEARISH DIVERGENCE (Price Up, Whales Selling)"
    elif cumulative_flow > 0:
        return "✅ Healthy Accumulation"
    else:
        return "❌ Weakness / Distribution"

async def analyze_market(ticker):
    async with aiohttp.ClientSession() as session:
        # Hent 90 dager (600 * 4h candles)
        usdc_task = fetch_candles(session, f"{ticker}USDC", "4h", 600)
        usdt_task = fetch_candles(session, f"{ticker}USDT", "4h", 600)
        
        res = await asyncio.gather(usdc_task, usdt_task)
        usdc_data, usdt_data = res[0], res[1]
        
    # Analyser rytmen for Smart Money (USDC)
    rhythm = analyze_rhythm(usdc_data)
    divergence = detect_divergence(rhythm)
    
    return {
        "ticker": ticker,
        "rhythm": rhythm,
        "divergence": divergence,
        "current_price": usdc_data[-1]['price'] if usdc_data else 0
    }

@app.get("/html/{ticker}", response_class=HTMLResponse)
async def get_dashboard(ticker: str):
    data = await analyze_market(ticker.upper())
    r = data["rhythm"]
    
    # HTML Generator
    rows = ""
    # Reverser for å vise nyeste øverst
    for w in reversed(r):
        week_label = "Current Week" if w['week_num'] == 0 else f"{abs(w['week_num'])} weeks ago"
        flow_fmt = f"${w['net_flow']/1_000_000:.1f}M"
        p_fmt = f"{w['price_change']:.1f}%"
        p_col = "green" if w['price_change'] > 0 else "red"
        
        rows += f"""
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px; color:#666;">{week_label}</td>
            <td style="padding:10px; font-weight:bold; color:{w['color']};">{w['phase']}</td>
            <td style="padding:10px;">{flow_fmt}</td>
            <td style="padding:10px; color:{p_col};">{p_fmt}</td>
        </tr>
        """

    html = f"""
    <html><body style="font-family: sans-serif; background: #f0f2f5; padding: 20px;">
        <div style="background: white; padding: 25px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); max-width: 700px; margin: auto;">
            
            <div style="text-align:center; margin-bottom:20px;">
                <h1 style="margin:0; font-size:24px;">🐋 {data['ticker']} Whale Rhythm</h1>
                <p style="color:#888; margin:5px 0;">Smart Money (USDC) Cycle Analysis • 90 Days</p>
                <div style="background:#e3f2fd; color:#1565c0; padding:10px; border-radius:8px; display:inline-block; margin-top:10px; font-weight:bold;">
                    {data['divergence']}
                </div>
            </div>

            <h3 style="margin-bottom:10px; color:#444;">Weekly Flow Rhythm (Last 12 Weeks)</h3>
            <table style="width:100%; border-collapse: collapse; font-size:14px;">
                <tr style="background:#fafafa; text-align:left; color:#888;">
                    <th style="padding:10px;">Periode</th>
                    <th style="padding:10px;">Market Phase</th>
                    <th style="padding:10px;">Net Flow (USDC)</th>
                    <th style="padding:10px;">Price Action</th>
                </tr>
                {rows}
            </table>
            
            <div style="margin-top:20px; padding:15px; background:#fafafa; border-radius:8px; font-size:13px; color:#666; line-height:1.5;">
                <strong>Hvordan lese dette?</strong><br>
                • <b>ABSORPTION:</b> Hvaler kjøper mens prisen faller. Dette er ofte bunnen. (Bullish)<br>
                • <b>MARKUP:</b> Hvaler kjøper og prisen stiger. Trenden er sterk.<br>
                • <b>DISTRIBUTION:</b> Hvaler selger mens prisen stiger. Toppen er nær. (Bearish)<br>
                • <b>CAPITULATION:</b> Alle selger i panikk. Ofte slutten på en nedtur.
            </div>
        </div>
    </body></html>
    """
    return html
