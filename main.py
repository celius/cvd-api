from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
import time

app = FastAPI(title="CVD API v4.0", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL = "https://api.binance.com/api/v3/aggTrades"

async def fetch_candle_volume(session, symbol, start_ts, end_ts):
    """Henter aggregert volum for et tidsvindu."""
    params = {
        "symbol": symbol,
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 1000
    }
    try:
        async with session.get(BASE_URL, params=params, timeout=5) as resp:
            if resp.status != 200: return 0.0, 0.0
            data = await resp.json()
            if not data: return 0.0, 0.0
            
            buy_vol = 0.0
            sell_vol = 0.0
            for t in data:
                vol = float(t['q']) * float(t['p'])
                if t['m']: sell_vol += vol
                else: buy_vol += vol
            return buy_vol, sell_vol
    except: return 0.0, 0.0

async def analyze_trend_segment(ticker):
    now = datetime.now(timezone.utc)
    segments = []
    
    # Definer tidsvinduer (Weighted Sampling)
    # 1. High Res (Siste 4t, annenhvert kvarter)
    for i in range(0, 240, 30): 
        segments.append({"offset": i, "type": "HighRes"})
        
    # 2. Low Res (4-8t siden, ett kvarter per time)
    for i in range(240, 480, 60):
        segments.append({"offset": i, "type": "LowRes"})
        
    tasks = []
    async with aiohttp.ClientSession() as session:
        for seg in segments:
            # Beregn start/slutt for dette 15min vinduet
            start_time = now - timedelta(minutes=seg["offset"] + 15)
            end_time = now - timedelta(minutes=seg["offset"])
            
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            # Sjekk både USDT og USDC
            tasks.append(fetch_candle_volume(session, f"{ticker}USDT", start_ts, end_ts))
            tasks.append(fetch_candle_volume(session, f"{ticker}USDC", start_ts, end_ts))
            
        results = await asyncio.gather(*tasks)
        
    # Aggreger resultatene
    trend_data = []
    total_cvd_now = 0
    total_cvd_prev = 0
    
    # Results kommer i par (USDT, USDC) for hvert segment
    for i, seg in enumerate(segments):
        usdt_res = results[i*2]
        usdc_res = results[i*2+1]
        
        net_flow = (usdt_res[0] - usdt_res[1]) + (usdc_res[0] - usdc_res[1])
        
        trend_data.append({
            "time_ago_min": seg["offset"],
            "flow": net_flow,
            "type": seg["type"]
        })
        
        # Enkel trend-sjekk (Siste 2t vs Forrige 2t av samplet data)
        if seg["offset"] < 120: total_cvd_now += net_flow
        elif seg["offset"] < 240: total_cvd_prev += net_flow

    # Analyser trend
    trend_change = "STABLE"
    if total_cvd_now > 0 and total_cvd_prev < 0: trend_change = "BULLISH REVERSAL"
    elif total_cvd_now > total_cvd_prev * 1.5 and total_cvd_now > 0: trend_change = "ACCELERATING UPTREND"
    elif total_cvd_now < 0 and total_cvd_prev > 0: trend_change = "BEARISH REVERSAL"
    elif total_cvd_now < total_cvd_prev * 1.5 and total_cvd_now < 0: trend_change = "ACCELERATING DOWNTREND"

    return {
        "ticker": ticker,
        "trend_signal": trend_change,
        "recent_flow": round(total_cvd_now, 2),
        "prev_flow": round(total_cvd_prev, 2),
        "data_points": len(trend_data),
        "segments": trend_data,
        "timestamp": now.isoformat()
    }

@app.get("/trend/{ticker}")
async def get_trend(ticker: str):
    return await analyze_trend_segment(ticker.upper())

@app.get("/html/{ticker}", response_class=HTMLResponse)
async def get_html(ticker: str):
    data = await analyze_trend_segment(ticker.upper())
    
    rows = ""
    for seg in data["segments"]:
        color = "green" if seg["flow"] > 0 else "red"
        rows += f"<tr><td>{seg['time_ago_min']}m ago</td><td style='color:{color}'>${seg['flow']:,.0f}</td><td>{seg['type']}</td></tr>"
        
    c_sig = "green" if "BULL" in data["trend_signal"] or "UP" in data["trend_signal"] else "red"
    if "STABLE" in data["trend_signal"]: c_sig = "gray"

    return f"""<html><body style="font-family: sans-serif; padding: 20px; background: #f5f5f5;">
    <div style="background: #fff; padding: 30px; border-radius: 12px; max-width: 600px; margin: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <h1>📊 {data['ticker']} Trend (8H)</h1>
        <h2 style="color:{c_sig}">{data['trend_signal']}</h2>
        <div style="display:flex; gap:20px; margin-bottom:20px;">
            <div><strong>Recent Flow (0-2h):</strong> ${data['recent_flow']:,.0f}</div>
            <div><strong>Prev Flow (2-4h):</strong> ${data['prev_flow']:,.0f}</div>
        </div>
        <table style="width:100%; text-align:left; border-collapse:collapse;">
            <tr style="border-bottom:1px solid #eee;"><th>Time</th><th>Net Flow</th><th>Type</th></tr>
            {rows}
        </table>
    </div></body></html>"""
