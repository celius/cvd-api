from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests
from datetime import datetime, timedelta, timezone
import time

app = FastAPI(title="CVD API v3.1", version="3.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_URL = "https://api.binance.com/api/v3/aggTrades"

def fetch_pair_history(symbol: str, start_time: int, end_time: int):
    trades = []
    current_start = start_time
    try:
        check = requests.get(BASE_URL, params={"symbol": symbol, "limit": 1}, timeout=5)
        if check.status_code != 200: return []
    except: return []

    while True:
        params = {"symbol": symbol, "startTime": current_start, "endTime": end_time, "limit": 1000}
        try:
            response = requests.get(BASE_URL, params=params, timeout=5)
            if response.status_code != 200: break
            batch = response.json()
            if not batch: break
            trades.extend(batch)
            if len(batch) < 1000: break
            current_start = batch[-1]['T'] + 1
            if current_start >= end_time: break
        except: break
    return trades

def calc_metrics(trades):
    if not trades: return 0.0, 0.0, 0.0
    buy_vol = sum(float(t['q']) * float(t['p']) for t in trades if not t['m'])
    sell_vol = sum(float(t['q']) * float(t['p']) for t in trades if t['m'])
    return buy_vol - sell_vol, buy_vol, sell_vol

def analyze_flow(ticker: str, minutes: int = 15):
    end_time = int(time.time() * 1000)
    start_time = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    
    # 1. Hent data separat
    usdt_trades = fetch_pair_history(f"{ticker}USDT", start_time, end_time)
    usdc_trades = fetch_pair_history(f"{ticker}USDC", start_time, end_time)
    
    if not usdt_trades and not usdc_trades:
        raise HTTPException(status_code=404, detail=f"No trades found for {ticker}")

    # 2. Beregn CVD separat
    cvd_usdt, buy_usdt, sell_usdt = calc_metrics(usdt_trades)
    cvd_usdc, buy_usdc, sell_usdc = calc_metrics(usdc_trades)
    
    # 3. Aggregert
    total_cvd = cvd_usdt + cvd_usdc
    total_buy = buy_usdt + buy_usdc
    total_sell = sell_usdt + sell_usdc
    total_vol = total_buy + total_sell
    buy_pct = (total_buy / total_vol * 100) if total_vol > 0 else 0

    # 4. Smart Money Logic
    divergence = "NONE"
    if cvd_usdc > 0 and cvd_usdt < 0: divergence = "BULLISH DIVERGENCE (Insti Buy / Retail Sell)"
    elif cvd_usdc < 0 and cvd_usdt > 0: divergence = "BEARISH DIVERGENCE (Insti Sell / Retail Buy)"
    
    interpretation = "NEUTRAL"
    if buy_pct >= 55: interpretation = "BULLISH"
    elif buy_pct <= 45: interpretation = "BEARISH"
    
    if "BULLISH DIVERGENCE" in divergence: interpretation = "🐋 SMART MONEY ACCUMULATION"
    if "BEARISH DIVERGENCE" in divergence: interpretation = "⚠️ SMART MONEY DISTRIBUTION"

    return {
        "ticker": ticker,
        "minutes": minutes,
        "total_cvd": round(total_cvd, 2),
        "usdt_cvd": round(cvd_usdt, 2),
        "usdc_cvd": round(cvd_usdc, 2),
        "divergence": divergence,
        "signal": interpretation,
        "buy_pct": round(buy_pct, 1),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/cvd/{ticker}")
def get_cvd(ticker: str, minutes: int = 15):
    return analyze_flow(ticker.upper(), minutes)

@app.get("/html/{ticker}", response_class=HTMLResponse)
def get_html(ticker: str, minutes: int = 15):
    data = analyze_flow(ticker.upper(), minutes)
    
    # Farger
    c_total = "green" if data['total_cvd'] > 0 else "red"
    c_usdt = "green" if data['usdt_cvd'] > 0 else "red"
    c_usdc = "green" if data['usdc_cvd'] > 0 else "red"
    
    div_html = ""
    if data['divergence'] != "NONE":
        div_color = "#e8f5e9" if "BULLISH" in data['divergence'] else "#ffebee"
        div_text = "#2e7d32" if "BULLISH" in data['divergence'] else "#c62828"
        div_html = f"<div style='margin:15px 0; padding:10px; background:{div_color}; color:{div_text}; border-radius:4px; font-weight:bold;'>⚡ {data['divergence']}</div>"

    return f"""<html><body style="font-family: sans-serif; padding: 20px; background: #f5f5f5;">
    <div style="background: #fff; padding: 30px; border-radius: 12px; max-width: 600px; margin: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h1 style="margin:0;">{data['ticker']} Flow</h1>
            <span style="background:#eee; padding:5px 10px; border-radius:15px; font-size:12px;">{minutes}m</span>
        </div>
        
        <h2 style="margin:10px 0 20px 0; color:#333;">{data['signal']}</h2>
        {div_html}
        
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px; margin-bottom:20px;">
            <div style="background:#fafafa; padding:15px; border-radius:8px; border-left: 4px solid {c_usdt};">
                <div style="font-size:12px; color:#666;">USDT (Retail/Offshore)</div>
                <div style="font-size:20px; font-weight:bold; color:{c_usdt};">${data['usdt_cvd']:,.0f}</div>
            </div>
            <div style="background:#fafafa; padding:15px; border-radius:8px; border-left: 4px solid {c_usdc};">
                <div style="font-size:12px; color:#666;">USDC (Insti/Onshore)</div>
                <div style="font-size:20px; font-weight:bold; color:{c_usdc};">${data['usdc_cvd']:,.0f}</div>
            </div>
        </div>
        
        <div style="text-align:center; padding-top:15px; border-top:1px solid #eee;">
            <div style="font-size:12px; color:#888;">Total Net Flow</div>
            <div style="font-size:32px; font-weight:bold; color:{c_total};">${data['total_cvd']:,.0f}</div>
            <div style="font-size:14px; color:#666;">Buy Pressure: {data['buy_pct']}%</div>
        </div>
        
        <div style="margin-top:20px; font-size:10px; color:#aaa; text-align:center;">
            Updated: {data['timestamp']}
        </div>
    </div></body></html>"""
