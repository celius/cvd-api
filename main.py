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
    """
    Henter alle aggregerte trades for de siste X minuttene ved å loope.
    Bytter til /aggTrades endepunktet som støtter startTime/endTime.
    """
    base_url = "https://api.binance.com/api/v3/aggTrades"
    
    # Beregn tidsvindu i millisekunder
    end_time = int(time.time() * 1000)
    start_time = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    
    all_trades = []
    current_start = start_time
    
    print(f"Henter data for {symbol} siste {minutes} minutter...")

    while True:
        # Hent batch på 1000 trades fra current_start
        params = {
            "symbol": symbol,
            "startTime": current_start,
            "endTime": end_time,
            "limit": 1000
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
            
            if not batch:
                break
                
            all_trades.extend(batch)
            
            # Hvis vi fikk færre enn 1000, har vi nådd slutten av dataene for nåtid
            if len(batch) < 1000:
                break
                
            # Oppdater start-tid til siste trade + 1ms for neste loop
            last_trade_time = batch[-1]['T']
            current_start = last_trade_time + 1
            
            # Sikkerhetsmekanisme: Hvis vi har passert nåtid (skal ikke skje med endTime satt, men greit å ha)
            if current_start >= end_time:
                break
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching batch: {e}")
            break

    return all_trades

def calculate_cvd_pro(symbol: str, minutes: int = 15):
    trades = fetch_trades_time_window(symbol, minutes)
    
    if not trades:
        raise HTTPException(status_code=404, detail=f"No trades found for {symbol}")

    # Merk: aggTrades bruker andre nøkler enn raw trades:
    # 'p' = price, 'q' = quantity, 'm' = isBuyerMaker (True = Sell, False = Buy)
    
    buy_volume = sum(float(t['q']) * float(t['p']) for t in trades if not t['m'])
    sell_volume = sum(float(t['q']) * float(t['p']) for t in trades if t['m'])
    
    cvd = buy_volume - sell_volume
    total_volume = buy_volume + sell_volume
    buy_pct = (buy_volume / total_volume * 100) if total_volume > 0 else 0

    # Tolkning (Samme logikk som før)
    if buy_pct >= 60:
        signal = "STRONG BULLISH"
        interpretation = "🟢 STRONG BULLISH - Heavy accumulation"
    elif buy_pct >= 52:
        signal = "BULLISH"
        interpretation = "🟢 BULLISH - Accumulation detected"
    elif buy_pct >= 48:
        signal = "NEUTRAL"
        interpretation = "⚪ NEUTRAL - Balanced flow"
    elif buy_pct >= 40:
        signal = "BEARISH"
        interpretation = "🔴 BEARISH - Distribution detected"
    else:
        signal = "STRONG BEARISH"
        interpretation = "🔴 STRONG BEARISH - Heavy distribution"

    return {
        "symbol": symbol,
        "minutes_analyzed": minutes,
        "trades_count": len(trades),
        "cvd_usd": round(cvd, 2),
        "buy_volume_usd": round(buy_volume, 2),
        "sell_volume_usd": round(sell_volume, 2),
        "buy_percentage": round(buy_pct, 1),
        "signal": signal,
        "interpretation": interpretation,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/cvd/{symbol}")
def get_cvd(symbol: str, minutes: int = 15):
    """JSON endpoint med tidsvariabel"""
    return calculate_cvd_pro(symbol.upper(), minutes)

@app.get("/html/{symbol}", response_class=HTMLResponse)
def get_cvd_html(symbol: str, minutes: int = 15):
    data = calculate_cvd_pro(symbol.upper(), minutes)
    
    emoji = "🟢" if "BULLISH" in data['signal'] else ("🔴" if "BEARISH" in data['signal'] else "⚪")
    color = "green" if data['cvd_usd'] > 0 else "red"
    
    # Enkelt HTML output (du kan bruke din forrige template her)
    html = f"""
    <html>
    <body style="font-family: Arial; padding: 20px; background: #f5f5f5;">
        <div style="background: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: auto;">
            <h1>{emoji} {data['symbol']} ({minutes}m)</h1>
            <div style="font-size: 1.2em; margin-bottom: 20px;"><strong>{data['interpretation']}</strong></div>
            
            <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
                <div>
                    <div style="color: #888;">CVD (Net Flow)</div>
                    <div style="font-size: 24px; color: {color}; font-weight: bold;">${data['cvd_usd']:,.2f}</div>
                </div>
                <div>
                    <div style="color: #888;">Buy Pressure</div>
                    <div style="font-size: 24px;">{data['buy_percentage']}%</div>
                </div>
            </div>
            
            <div style="color: #999; font-size: 12px;">
                Analyzed {data['trades_count']} aggregated trades over last {minutes} minutes.<br>
                Updated: {data['timestamp']}
            </div>
        </div>
    </body>
    </html>
    """
    return html
