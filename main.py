from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
import time

app = FastAPI(title="CVD API v4.1", version="4.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL = "https://api.binance.com/api/v3/aggTrades"

async def fetch_flow(session, symbol, start_ts, end_ts):
    """Henter kjøp/salg volum for et par."""
    params = {"symbol": symbol, "startTime": start_ts, "endTime": end_ts, "limit": 1000}
    try:
        async with session.get(BASE_URL, params=params, timeout=5) as resp:
            if resp.status != 200: return 0.0
            data = await resp.json()
            if not data: return 0.0
            
            buy = sum(float(t['q']) * float(t['p']) for t in data if not t['m'])
            sell = sum(float(t['q']) * float(t['p']) for t in data if t['m'])
            return buy - sell # Returner Net Flow (CVD)
    except: return 0.0

async def analyze_xray_trend(ticker):
    now = datetime.now(timezone.utc)
    segments = []
    
    # Sampling Strategi:
    # 0-2t: Hvert 15 min (Super High Res)
    # 2-8t: Hvert 60 min (Trend Context)
    
    offsets = [0, 15, 30, 45, 60, 90, 120, 180, 240, 300, 360, 420]
    
    tasks = []
    async with aiohttp.ClientSession() as session:
        for offset in offsets:
            start_time = now - timedelta(minutes=offset + 15)
            end_time = now - timedelta(minutes=offset)
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            # Vi henter USDT og USDC separat for å sammenligne dem
            tasks.append(fetch_flow(session, f"{ticker}USDT", start_ts, end_ts))
            tasks.append(fetch_flow(session, f"{ticker}USDC", start_ts, end_ts))
            
        results = await asyncio.gather(*tasks)
        
    # Strukturering av data
    data_points = []
    retail_sum_2h = 0
    insti_sum_2h = 0
    
    for i, offset in enumerate(offsets):
        retail_flow = results[i*2]      # USDT
        insti_flow = results[i*2+1]     # USDC
        
        if offset < 120: # Siste 2 timer
            retail_sum_2h += retail_flow
            insti_sum_2h += insti_flow
            
        data_points.append({
            "time": f"{offset}m ago",
            "retail": retail_flow,
            "insti": insti_flow
        })

    # Tolkning av Divergens (Siste 2 timer)
    signal = "NEUTRAL FLOW"
    sig_color = "gray"
    
    if insti_sum_2h > 0 and retail_sum_2h < 0:
        signal = "🐋 SMART ACCUMULATION (Insti Buy / Retail Sell)"
        sig_color = "#2e7d32" # Strong Green
    elif insti_sum_2h < 0 and retail_sum_2h > 0:
        signal = "⚠️ SMART DISTRIBUTION (Insti Sell / Retail Buy)"
        sig_color = "#c62828" # Strong Red
    elif insti_sum_2h > 0 and retail_sum_2h > 0:
        signal = "🚀 STRONG MOMENTUM (All Buying)"
        sig_color = "#1b5e20"
    elif insti_sum_2h < 0 and retail_sum_2h < 0:
        signal = "🩸 HEAVY DUMP (All Selling)"
        sig_color = "#b71c1c"

    return {
        "ticker": ticker,
        "signal": signal,
        "sig_color": sig_color,
        "retail_2h": retail_sum_2h,
        "insti_2h": insti_sum_2h,
        "segments": data_points,
        "timestamp": now.strftime("%H:%M UTC")
    }

@app.get("/html/{ticker}", response_class=HTMLResponse)
async def get_xray_html(ticker: str):
    data = await analyze_xray_trend(ticker.upper())
    
    rows = ""
    for p in data["segments"]:
        r_col = "red" if p["retail"] < 0 else "green"
        i_col = "red" if p["insti"] < 0 else "green"
        # Uthev Smart Money flow hvis den er stor og motsatt av retail
        bg = ""
        if (p["insti"] > 0 and p["retail"] < 0) or (p["insti"] < 0 and p["retail"] > 0):
            bg = "background: #fffde7;" # Highlight divergence
            
        rows += f"""<tr style='{bg} border-bottom:1px solid #eee;'>
            <td style='padding:8px; color:#888;'>{p['time']}</td>
            <td style='padding:8px; font-weight:bold; color:{r_col};'>${p['retail']:,.0f}</td>
            <td style='padding:8px; font-weight:bold; color:{i_col};'>${p['insti']:,.0f}</td>
        </tr>"""

    return f"""<html><body style="font-family: sans-serif; padding: 20px; background: #f5f5f5;">
    <div style="background: #fff; padding: 25px; border-radius: 12px; max-width: 600px; margin: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h1 style="margin:0;">🔍 {data['ticker']} X-Ray</h1>
            <span style="color:#aaa; font-size:12px;">{data['timestamp']}</span>
        </div>
        
        <div style="margin:20px 0; padding:15px; background:{data['sig_color']}15; border-left:5px solid {data['sig_color']};">
            <h3 style="margin:0; color:{data['sig_color']};">{data['signal']}</h3>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px; margin-bottom:25px;">
            <div style="text-align:center; padding:10px; background:#fafafa; border-radius:8px;">
                <div style="font-size:12px; color:#666;">🛒 RETAIL (USDT) 2H</div>
                <div style="font-size:18px; font-weight:bold; color:{'green' if data['retail_2h']>0 else 'red'}">${data['retail_2h']:,.0f}</div>
            </div>
            <div style="text-align:center; padding:10px; background:#fff8e1; border:1px solid #ffecb3; border-radius:8px;">
                <div style="font-size:12px; color:#f57f17; font-weight:bold;">🏦 SMART MONEY (USDC) 2H</div>
                <div style="font-size:18px; font-weight:bold; color:{'green' if data['insti_2h']>0 else 'red'}">${data['insti_2h']:,.0f}</div>
            </div>
        </div>

        <table style="width:100%; text-align:right; border-collapse:collapse; font-size:14px;">
            <tr style="background:#fafafa; color:#666;">
                <th style="padding:10px; text-align:left;">Time</th>
                <th style="padding:10px;">🛒 Retail Flow</th>
                <th style="padding:10px;">🏦 Smart Flow</th>
            </tr>
            {rows}
        </table>
        <div style="margin-top:15px; font-size:11px; color:#999; text-align:center;">
            Divergence (Yellow Rows) = High Value Signal
        </div>
    </div></body></html>"""
