from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests
from datetime import datetime, timedelta, timezone
import time

app = FastAPI(title="CVD API Pro", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def fetch_trades_time_window(symbol: str, minutes: int = 15):
    """Henter alle aggregerte trades for de siste X minuttene ved å loope."""
    base_url = "https://api.binance.com/api/v3/aggTrades"
    end_time = int(time.time() * 1000)
    start_time = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    
    all_trades = []
    current_start = start_time

    while True:
        params = {"symbol": symbol, "startTime": current_start, "endTime": end_time, "limit": 1000}
        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
            if not batch: break
            all_trades.extend(batch)
            if len(batch) < 1000: break
            current_start = batch[-1]['T'] + 1
            if current_start >= end_time: break
        except: break

    return all_trades

def calculate_cvd_pro(symbol: str, minutes: int = 15):
    trades = fetch_trades_time_window(symbol, minutes)
    if not trades: raise HTTPException(status_code=404, detail=f"No trades found for {symbol}")

    buy_volume = sum(float(t['q']) * float(t['p']) for t in trades if not t['m'])
    sell_volume = sum(float(t['q']) * float(t['p']) for t in trades if t['m'])
    
    cvd = buy_volume - sell_volume
    total_volume = buy_volume + sell_volume
    buy_pct = (buy_volume / total_volume * 100) if total_volume > 0 else 0

    if buy_pct >= 60: interpretation = "🟢 STRONG BULLISH - Heavy accumulation"
    elif buy_pct >= 52: interpretation = "🟢 BULLISH - Accumulation detected"
    elif buy_pct >= 48: interpretation = "⚪ NEUTRAL - Balanced flow"
    elif buy_pct >= 40: interpretation = "🔴 BEARISH - Distribution detected"
    else: interpretation = "🔴 STRONG BEARISH - Heavy distribution"

    return {
        "symbol": symbol, "cvd_usd": round(cvd, 2),
        "buy_percentage": round(buy_pct, 1),
        "signal": "BULLISH" if buy_pct >= 52 else ("BEARISH" if buy_pct < 48 else "NEUTRAL"),
        "interpretation": interpretation,
        "trades_analyzed": len(trades),
        "minutes": minutes,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/cvd/{symbol}")
def get_cvd(symbol: str, minutes: int = 15):
    return calculate_cvd_pro(symbol.upper(), minutes)

@app.get("/html/{symbol}", response_class=HTMLResponse)
def get_cvd_html(symbol: str, minutes: int = 15):
    data = calculate_cvd_pro(symbol.upper(), minutes)
    color = "green" if data['cvd_usd'] > 0 else "red"
    emoji = "🟢" if "BULLISH" in data['signal'] else ("🔴" if "BEARISH" in data['signal'] else "⚪")
    
    return f"""<html><body style="font-family: sans-serif; padding: 20px;">
    <div style="background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
        <h1>{emoji} {data['symbol']} ({minutes}m)</h1>
        <h3>{data['interpretation']}</h3>
        <p>CVD: <strong style="color: {color}">${data['cvd_usd']:,.2f}</strong></p>
        <p>Buy Pressure: <strong>{data['buy_percentage']}%</strong></p>
        <small>Based on {data['trades_analyzed']} trades over {minutes} minutes.</small>
    </div></body></html>"""
