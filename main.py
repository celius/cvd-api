from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests
from datetime import datetime

app = FastAPI(title="CVD API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def calculate_cvd(symbol: str, limit: int = 1000):
    """Henter trades fra Binance og beregner CVD."""
    url = f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit={limit}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        trades = response.json()
        
        if not trades:
            raise HTTPException(status_code=404, detail=f"No trades found for {symbol}")
        
        buy_volume = sum(float(t['qty']) * float(t['price']) for t in trades if not t['isBuyerMaker'])
        sell_volume = sum(float(t['qty']) * float(t['price']) for t in trades if t['isBuyerMaker'])
        cvd = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        buy_pct = (buy_volume / total_volume * 100) if total_volume > 0 else 0
        
        if buy_pct >= 60:
            signal = "STRONG BULLISH"
            interpretation = "🟢 STRONG BULLISH - Strong accumulation detected"
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
            interpretation = "🔴 STRONG BEARISH - Strong distribution detected"
        
        return {
            "symbol": symbol,
            "cvd_usd": round(cvd, 2),
            "buy_volume_usd": round(buy_volume, 2),
            "sell_volume_usd": round(sell_volume, 2),
            "buy_percentage": round(buy_pct, 1),
            "signal": signal,
            "trades_analyzed": len(trades),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "interpretation": interpretation
        }
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Binance API error: {str(e)}")

@app.get("/")
def root():
    return {
        "service": "Crypto CVD API for Mode 7",
        "usage": "GET /cvd/{symbol} for JSON or /html/{symbol} for HTML",
        "status": "operational"
    }

@app.get("/cvd/{symbol}")
def get_cvd(symbol: str):
    """JSON endpoint - samme som før"""
    return calculate_cvd(symbol.upper())

@app.get("/html/{symbol}", response_class=HTMLResponse)
def get_cvd_html(symbol: str):
    """HTML endpoint - for Mode 7 crawler"""
    data = calculate_cvd(symbol.upper())
    
    # Velg emoji basert på signal
    emoji_map = {
        "STRONG BULLISH": "🟢",
        "BULLISH": "🟢",
        "NEUTRAL": "⚪",
        "BEARISH": "🔴",
        "STRONG BEARISH": "🔴"
    }
    emoji = emoji_map.get(data['signal'], "⚪")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{data['symbol']} - CVD Analysis</title>
        <meta charset="utf-8">
        <style>
            body 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background: #f5f5f5;
            
            .container 
                background: white;
                border-radius: 8px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            
            h1 
                color: #333;
                margin-bottom: 10px;
            
            .metric 
                margin: 20px 0;
                padding: 15px;
                background: #f9f9f9;
                border-radius: 6px;
                border-left: 4px solid #4CAF50;
            
            .metric.bearish 
                border-left-color: #f44336;
            
            .metric.neutral 
                border-left-color: #9E9E9E;
            
            .label 
                font-size: 14px;
                color: #666;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            
            .value 
                font-size: 24px;
                color: #333;
                margin-top: 5px;
                font-weight: bold;
            
            .signal 
                font-size: 32px;
                padding: 20px;
                text-align: center;
                background: #f0f0f0;
                border-radius: 8px;
                margin: 20px 0;
            
            .timestamp 
                text-align: center;
                color: #999;
                font-size: 12px;
                margin-top: 20px;
            
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{emoji} {data['symbol']} - Spot CVD Analysis</h1>
            
            <div class="signal">
                {data['interpretation']}
            </div>
            
            <div class="metric {'bearish' if data['cvd_usd'] < 0 else ''}">
                <div class="label">Cumulative Volume Delta (CVD)</div>
                <div class="value">${data['cvd_usd']:,.2f}</div>
            </div>
            
            <div class="metric">
                <div class="label">Buy Volume</div>
                <div class="value">${data['buy_volume_usd']:,.2f} ({data['buy_percentage']}%)</div>
            </div>
            
            <div class="metric">
                <div class="label">Sell Volume</div>
                <div class="value">${data['sell_volume_usd']:,.2f} ({100 - data['buy_percentage']:.1f}%)</div>
            </div>
            
            <div class="metric neutral">
                <div class="label">Data Window</div>
                <div class="value">{data['trades_analyzed']} trades analyzed</div>
            </div>
            
            <div class="timestamp">
                Last updated: {data['timestamp']}<br>
                Source: Binance Spot REST API
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content
